"""
Improved calibration webapp with file system monitoring.

This version:
1. Watches module-data/ directory for new passes
2. Uses sentinel files to know when a pass is complete
3. Can auto-upload to cloud when complete
4. Provides both web UI and automatic processing
"""

from flask import Flask, request, render_template_string, send_file, jsonify
import os
import threading
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Tuple, Sequence
import logging

from typing_extensions import ClassVar
from viam.resource.types import Model, ModelFamily
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import ResourceName
from viam.resource.base import ResourceBase
from typing_extensions import Self, Mapping
from viam.utils import struct_to_dict
from viam.services.generic import Generic
from viam.resource.easy_resource import EasyResource
from werkzeug.serving import make_server
logger = logging.getLogger(__name__)


WEB_APP_OPTIONS_ATTR = "web_app_options"


def _default_module_data_root() -> Path:
    env_root = os.getenv("VIAM_MODULE_DATA")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return (Path.cwd() / "module-data").resolve()


DEFAULT_MODULE_DATA_ROOT = (_default_module_data_root() / "calibration-passes").resolve()

DEFAULT_WEB_APP_OPTIONS = {
    "assets_dir": str(DEFAULT_MODULE_DATA_ROOT),
    "port": 5000,
    "watch_for_complete": True
}


class CalibrationPassWatcher:
    """
    Watches the calibration-passes directory for new/completed passes.
    Uses sentinel files to determine when a pass is complete.
    """
    
    def __init__(
        self, 
        watch_dir: Path,
        check_interval: float = 2.0,
        on_pass_complete: Optional[Callable] = None
    ):
        self.watch_dir = watch_dir
        self.check_interval = check_interval
        self.on_pass_complete = on_pass_complete
        self._stop_flag = threading.Event()
        self._watcher_thread: Optional[threading.Thread] = None
        self._known_passes = set()
        
    def start(self):
        """Start watching for new passes"""
        if self._watcher_thread and self._watcher_thread.is_alive():
            logger.warning("Watcher already running")
            return
        
        self._stop_flag.clear()
        self._watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher_thread.start()
        logger.info(f"Started watching {self.watch_dir}")
    
    def stop(self):
        """Stop watching"""
        self._stop_flag.set()
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5)
        logger.info("Stopped watching")
    
    def _watch_loop(self):
        """Main watch loop"""
        while not self._stop_flag.is_set():
            try:
                self._check_for_complete_passes()
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
            
            self._stop_flag.wait(self.check_interval)
    
    def _check_for_complete_passes(self):
        """Check for passes with sentinel files"""
        if not self.watch_dir.exists():
            return
        
        for pass_dir in self.watch_dir.iterdir():
            if not pass_dir.is_dir():
                continue
            
            pass_id = pass_dir.name
            
            # Skip if we've already processed this pass
            if pass_id in self._known_passes:
                continue
            
            # Check for sentinel file indicating completion
            sentinel_file = pass_dir / ".complete"
            if sentinel_file.exists():
                logger.info(f"Found completed pass: {pass_id}")
                self._known_passes.add(pass_id)
                
                # Call the callback if provided
                if self.on_pass_complete:
                    try:
                        self.on_pass_complete(pass_id, pass_dir)
                    except Exception as e:
                        logger.error(f"Error in on_pass_complete callback: {e}")


class CalibrationWebAppWithWatcher(Generic, EasyResource):
    """
    Flask webapp with file system monitoring.
    Automatically detects completed calibration passes.
    """
    # To enable debug-level logging, either run viam-server with the --debug option,
    # or configure your resource/machine to display debug logs.
    MODEL: ClassVar[Model] = Model(
        ModelFamily("viam", "opencv-webapp"), "webapp"
    )

    @classmethod
    def new(
        cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> Self:
        """This method creates a new instance of this Generic service.
        The default implementation sets the name from the `config` parameter and then calls `reconfigure`.

        Args:
            config (ComponentConfig): The configuration for this resource
            dependencies (Mapping[ResourceName, ResourceBase]): The dependencies (both required and optional)

        Returns:
            Self: The resource
        """
        return super().new(config, dependencies)


    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        """This method allows you to validate the configuration object received from the machine,
        as well as to return any required dependencies or optional dependencies based on that `config`.

        Args:
            config (ComponentConfig): The configuration for this resource

        Returns:
            Tuple[Sequence[str], Sequence[str]]: A tuple where the
                first element is a list of required dependencies and the
                second element is a list of optional dependencies
        """
        attrs = struct_to_dict(config.attributes)

        web_app_options = attrs.get(WEB_APP_OPTIONS_ATTR)
        if web_app_options is not None:
            if not isinstance(web_app_options, dict):
                raise Exception(f"'{WEB_APP_OPTIONS_ATTR}' must be a dictionary, got {type(web_app_options)}")
            if "assets_dir" not in web_app_options:
                web_app_options["assets_dir"] = DEFAULT_MODULE_DATA_ROOT
            if "port" not in web_app_options:
                web_app_options["port"] = DEFAULT_WEB_APP_OPTIONS["port"]

        return [], []

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        """This method allows you to dynamically update your service when it receives a new `config` object.

        Args:
            config (ComponentConfig): The new configuration
            dependencies (Mapping[ResourceName, ResourceBase]): Any dependencies (both required and optional)
        """
        attrs = struct_to_dict(config.attributes)
        new_options = attrs.get(WEB_APP_OPTIONS_ATTR, {}) or {}
        if not isinstance(new_options, dict):
            raise Exception(f"'{WEB_APP_OPTIONS_ATTR}' must be a dictionary, got {type(new_options)}")

        merged_options = DEFAULT_WEB_APP_OPTIONS.copy()
        merged_options.update(new_options)

        if self.web_app_options != merged_options:
            self._apply_options(merged_options)
        return super().reconfigure(config, dependencies)

    
    def __init__(
        self,
        base_dir: str = str(DEFAULT_MODULE_DATA_ROOT),
        port: int = 5001,
        watch_for_complete: bool = True
    ):
        self.web_app_options = None

        self.base_dir: Path = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.port = int(port)

        self.watcher: Optional[CalibrationPassWatcher] = None
        if watch_for_complete:
            self.watcher = CalibrationPassWatcher(
                watch_dir=self.base_dir,
                on_pass_complete=self._on_pass_complete
            )

        self.app: Flask = self._create_app()

        self._server = None
        self._server_thread: Optional[threading.Thread] = None

        # Initialize options state
        self._apply_options({
            "assets_dir": str(self.base_dir),
            "port": self.port,
            "watch_for_complete": watch_for_complete
        })
    
    def _apply_options(self, options: dict):
        """Apply web app options, restarting services when already running."""
        restart_required = self.web_app_options is not None
        if restart_required:
            self.stop()

        self.web_app_options = options

        assets_dir = Path(self.web_app_options["assets_dir"]).expanduser().resolve()
        assets_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir = assets_dir
        self.port = int(self.web_app_options.get("port", DEFAULT_WEB_APP_OPTIONS["port"]))

        watch_for_complete = bool(self.web_app_options.get("watch_for_complete", True))
        if self.watcher:
            self.watcher.stop()
        self.watcher = CalibrationPassWatcher(
            watch_dir=self.base_dir,
            on_pass_complete=self._on_pass_complete
        ) if watch_for_complete else None

        self.app = self._create_app()

        if restart_required:
            self.start()

    def _on_pass_complete(self, pass_id: str, pass_dir: Path):
        """Called when a pass is marked as complete"""
        logger.info(f"✅ Pass complete: {pass_id}")
        
        # Read metadata if available
        metadata_file = pass_dir / "metadata.json"
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
            logger.info(f"   Metadata: {metadata}")
        
        # Count files
        files = list(pass_dir.glob("*"))
        logger.info(f"   Files: {len(files)}")
        
        # Here you could:
        # - Upload to cloud storage
        # - Send notification
        # - Generate report
        # - Trigger analysis
        
        # Example: Create a summary file
        summary = {
            "pass_id": pass_id,
            "completed_at": datetime.now().isoformat(),
            "num_files": len(files),
            "files": [f.name for f in files if f.is_file()]
        }
        summary_file = pass_dir / "summary.json"
        summary_file.write_text(json.dumps(summary, indent=2))
        logger.info(f"   Created summary: {summary_file}")
    
    def _extract_timestamp_from_pass_id(self, pass_id: str):
        """
        Extract timestamp from pass ID and return human-readable format.
        Tries multiple common formats, falls back to None.
        """
        import re
        
        # Try format: pass-20241109-143022 or 20241109-143022
        match = re.search(r'(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})', pass_id)
        if match:
            year, month, day, hour, minute, second = match.groups()
            return f"{year}-{month}-{day} {hour}:{minute}:{second}"
        
        # Try format: pass-2024-11-09-14-30-22
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', pass_id)
        if match:
            year, month, day, hour, minute, second = match.groups()
            return f"{year}-{month}-{day} {hour}:{minute}:{second}"
        
        # Try Unix timestamp: pass-1699545022
        match = re.search(r'(\d{10})', pass_id)
        if match:
            try:
                timestamp = int(match.group(1))
                return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
        
        return None
    
    def _create_app(self) -> Flask:
        app = Flask(__name__)
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        self._setup_routes(app)
        return app

    def _setup_routes(self, app: Flask):
        """Setup Flask routes"""
        
        HTML_TEMPLATE = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Hand-Eye Calibration Data</title>
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #f5f5f5;
                }
                .container { max-width: 1200px; margin: 0 auto; }
                h1 { color: #333; }
                .pass { 
                    background: white;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    margin: 15px 0;
                    overflow: hidden;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .pass.complete { border-left: 4px solid #4CAF50; }
                .pass.incomplete { border-left: 4px solid #FFC107; }
                .pass-header {
                    padding: 15px 20px;
                    background: #f9f9f9;
                    cursor: pointer;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    user-select: none;
                }
                .pass-header:hover {
                    background: #f0f0f0;
                }
                .pass-info {
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                    flex: 1;
                }
                .timestamp {
                    font-size: 0.85em;
                    color: #666;
                    font-weight: 500;
                }
                .pass-name-row {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                .pass-name {
                    font-size: 1.1em;
                    font-weight: 600;
                    color: #333;
                }
                .pass-meta {
                    display: flex;
                    align-items: center;
                    gap: 15px;
                }
                .toggle-icon {
                    font-size: 1.2em;
                    transition: transform 0.3s ease;
                    color: #666;
                }
                .toggle-icon.expanded {
                    transform: rotate(90deg);
                }
                .pass-content {
                    max-height: 0;
                    overflow: hidden;
                    transition: max-height 0.3s ease;
                }
                .pass-content.expanded {
                    max-height: 2000px;
                    padding: 15px 20px;
                    border-top: 1px solid #eee;
                }
                .status-badge {
                    display: inline-block;
                    padding: 4px 12px;
                    border-radius: 12px;
                    font-size: 0.85em;
                    font-weight: 500;
                }
                .status-complete { background: #4CAF50; color: white; }
                .status-incomplete { background: #FFC107; color: #333; }
                .file-count {
                    color: #666;
                    font-size: 0.9em;
                    font-weight: normal;
                }
                .file-list {
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }
                .file-item {
                    padding: 10px;
                    margin: 5px 0;
                    background: #f9f9f9;
                    border-radius: 4px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .file-item a {
                    color: #2196F3;
                    text-decoration: none;
                    font-weight: 500;
                }
                .file-item a:hover { text-decoration: underline; }
                .file-meta {
                    color: #666;
                    font-size: 0.9em;
                }
                button {
                    background: #4CAF50;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 14px;
                    margin-right: 5px;
                }
                button:hover { background: #45a049; }
                button.secondary {
                    background: #757575;
                }
                button.secondary:hover {
                    background: #616161;
                }
                .info-box {
                    background: #E3F2FD;
                    border-left: 4px solid #2196F3;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }
                .empty-state {
                    text-align: center;
                    padding: 40px;
                    color: #999;
                    background: white;
                    border-radius: 8px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎯 Hand-Eye Calibration Data Viewer</h1>
                
                {% if watcher_enabled %}
                <div class="info-box">
                    <strong>Auto-monitoring enabled</strong><br>
                    Watching for completed passes (marked with .complete file)
                </div>
                {% endif %}

                <h2>Calibration Passes</h2>
                <button onclick="location.reload()">Refresh</button>
                <button onclick="expandAll()">Expand All</button>
                <button onclick="collapseAll()" class="secondary">Collapse All</button>
                
                <div id="passes">
                    {% if passes %}
                        {% for pass_id in passes|sort(reverse=True) %}
                        <div class="pass {{ 'complete' if passes[pass_id]['complete'] else 'incomplete' }}">
                            <div class="pass-header" onclick="togglePass(this)">
                                <div class="pass-info">
                                    <div class="timestamp">🕐 {{ passes[pass_id]['timestamp'] }}</div>
                                    <div class="pass-name-row">
                                        <span class="pass-name">📁 {{ pass_id }}</span>
                                        <span class="status-badge {{ 'status-complete' if passes[pass_id]['complete'] else 'status-incomplete' }}">
                                            {{ 'Complete' if passes[pass_id]['complete'] else 'In Progress' }}
                                        </span>
                                    </div>
                                </div>
                                <div class="pass-meta">
                                    <span class="file-count">({{ passes[pass_id]['files']|length }} files)</span>
                                    <span class="toggle-icon">▶</span>
                                </div>
                            </div>
                            <div class="pass-content">
                                <ul class="file-list">
                                    {% for file in passes[pass_id]['files']|sort %}
                                    {% if not file.startswith('.') %}
                                    <li class="file-item">
                                        <a href="/download/{{ pass_id }}/{{ file }}" target="_blank">{{ file }}</a>
                                        <span class="file-meta">
                                            {{ passes[pass_id]['files'][file]['size'] }} bytes | 
                                            {{ passes[pass_id]['files'][file]['modified'] }}
                                        </span>
                                    </li>
                                    {% endif %}
                                    {% endfor %}
                                </ul>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="empty-state">
                            <p>No calibration passes yet.</p>
                        </div>
                    {% endif %}
                </div>
            </div>

            <script>
                function togglePass(header) {
                    const content = header.nextElementSibling;
                    const icon = header.querySelector('.toggle-icon');
                    
                    content.classList.toggle('expanded');
                    icon.classList.toggle('expanded');
                }
                
                function expandAll() {
                    document.querySelectorAll('.pass-content').forEach(content => {
                        content.classList.add('expanded');
                    });
                    document.querySelectorAll('.toggle-icon').forEach(icon => {
                        icon.classList.add('expanded');
                    });
                }
                
                function collapseAll() {
                    document.querySelectorAll('.pass-content').forEach(content => {
                        content.classList.remove('expanded');
                    });
                    document.querySelectorAll('.toggle-icon').forEach(icon => {
                        icon.classList.remove('expanded');
                    });
                }
                
                // Auto-expand first pass on load
                window.addEventListener('DOMContentLoaded', () => {
                    const firstHeader = document.querySelector('.pass-header');
                    if (firstHeader) {
                        togglePass(firstHeader);
                    }
                });
            </script>
        </body>
        </html>
        """

        
        @app.route("/")
        def index():
            """Main page - list all passes and files"""
            passes = {}
            
            if self.base_dir.exists():
                for pass_dir in self.base_dir.iterdir():
                    if pass_dir.is_dir():
                        pass_id = pass_dir.name
                        
                        # Extract or determine timestamp
                        timestamp = self._extract_timestamp_from_pass_id(pass_id)
                        if not timestamp:
                            # Fall back to directory creation time
                            stat = pass_dir.stat()
                            timestamp = datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Check if pass is complete
                        is_complete = (pass_dir / ".complete").exists()
                        
                        passes[pass_id] = {
                            'complete': is_complete,
                            'timestamp': timestamp,
                            'files': {}
                        }
                        
                        for file_path in pass_dir.iterdir():
                            if file_path.is_file():
                                stat = file_path.stat()
                                passes[pass_id]['files'][file_path.name] = {
                                    'size': stat.st_size,
                                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                                }
            
            return render_template_string(
                HTML_TEMPLATE, 
                passes=passes,
                watcher_enabled=(self.watcher is not None)
            )

        @app.route("/download/<pass_id>/<filename>")
        def download(pass_id, filename):
            """Download a specific file"""
            file_path = (self.base_dir / pass_id / filename).resolve()
            try:
                file_path.relative_to(self.base_dir)
            except ValueError:
                return "File not found", 404
            if not file_path.exists() or not file_path.is_file():
                return "File not found", 404
            return send_file(file_path)
        
        @app.route("/api/passes")
        def api_passes():
            """API endpoint to list all passes"""
            passes = {}
            if self.base_dir.exists():
                for pass_dir in self.base_dir.iterdir():
                    if pass_dir.is_dir():
                        pass_id = pass_dir.name
                        is_complete = (pass_dir / ".complete").exists()
                        passes[pass_id] = {
                            "files": [f.name for f in pass_dir.iterdir() if f.is_file()],
                            "complete": is_complete
                        }
            return jsonify(passes)
        
        @app.route("/api/complete_pass/<pass_id>", methods=["POST"])
        def complete_pass(pass_id):
            """Mark a pass as complete"""
            pass_dir = (self.base_dir / pass_id).resolve()
            try:
                pass_dir.relative_to(self.base_dir)
            except ValueError:
                return jsonify({"error": "Pass not found"}), 404
            if not pass_dir.exists():
                return jsonify({"error": "Pass not found"}), 404
            
            sentinel = pass_dir / ".complete"
            sentinel.write_text(json.dumps({
                "completed_at": datetime.now().isoformat()
            }))
            
            logger.info(f"Marked pass as complete: {pass_id}")
            return jsonify({"status": "complete", "pass_id": pass_id})
    
    def start(self):
        """Start the Flask server and watcher"""
        # Start watcher if enabled
        if self.watcher:
            self.watcher.start()
        
        # Start Flask server
        if self._server_thread is not None and self._server_thread.is_alive():
            logger.warning("Server is already running")
            return
        
        logger.info(f"Starting calibration webapp on http://0.0.0.0:{self.port}")
        logger.info(f"Saving files to: {self.base_dir}")

        self._server = make_server("0.0.0.0", self.port, self.app)
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()
        logger.info("Calibration webapp started")
    
    def stop(self):
        """Stop the Flask server and watcher"""
        if self.watcher:
            self.watcher.stop()
        if self._server:
            try:
                self._server.shutdown()
            except Exception as err:
                logger.warning(f"Error shutting down web server: {err}")
        if self._server_thread:
            self._server_thread.join(timeout=5)
        self._server = None
        self._server_thread = None
        logger.info("Webapp stopped")
    
    def save_file(self, pass_id: str, filename: str, data: bytes) -> Path:
        """
        Save a file to a specific calibration pass.
        """
        try:
            pass_dir = (self.base_dir / pass_id).resolve()
            pass_dir.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError(f"Invalid pass_id '{pass_id}'") from exc
        pass_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            file_path = (pass_dir / filename).resolve()
            file_path.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError(f"Invalid filename '{filename}'") from exc
        file_path.write_bytes(data)
        
        logger.info(f"Saved file: {file_path}")
        return file_path
    
    def mark_pass_complete(self, pass_id: str, metadata: dict = None):
        """
        Mark a calibration pass as complete by creating sentinel file.
        """
        try:
            pass_dir = (self.base_dir / pass_id).resolve()
            pass_dir.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError(f"Invalid pass_id '{pass_id}'") from exc
        if not pass_dir.exists():
            raise ValueError(f"Pass directory does not exist: {pass_id}")
        
        sentinel_data = {
            "completed_at": datetime.now().isoformat(),
            **(metadata or {})
        }
        
        sentinel = pass_dir / ".complete"
        sentinel.write_text(json.dumps(sentinel_data, indent=2))
        
        logger.info(f"Marked pass as complete: {pass_id}")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    webapp = CalibrationWebAppWithWatcher(
        base_dir="module-data/calibration-passes",
        port=5000,
        watch_for_complete=True
    )
    
    webapp.start()
    
    print("=" * 60)
    print("Webapp running with file watcher enabled")
    print("Try this:")
    print("1. Create a pass: mkdir -p module-data/calibration-passes/test-pass")
    print("2. Add files: echo 'test' > module-data/calibration-passes/test-pass/data.txt")
    print("3. Mark complete: touch module-data/calibration-passes/test-pass/.complete")
    print("4. Watch the logs!")
    print("=" * 60)
    print("Press Ctrl+C to stop...")
    
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        webapp.stop()