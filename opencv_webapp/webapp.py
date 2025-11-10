"""
Minimal Viam Generic Service for Calibration File Management.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence, Tuple

import asyncio

from viam.module.module import Module
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import ResourceName
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.services.generic import Generic
from viam.utils import struct_to_dict

logger = logging.getLogger(__name__)


class WebApp(Generic, EasyResource):
    """
    Exposes calibration files through do_command API.

    Supported commands:
      - {"command": "list_passes"}
      - {"command": "get_file", "pass_id": "...", "filename": "..."}
    """

    MODEL = Model(ModelFamily("viam", "opencv-webapp"), "webapp")

    def __init__(self, name: str, base_dir: str = "./module-data/calibration-passes"):
        super().__init__(name)
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info("WebApp service '%s' initialized at %s", self.name, self.base_dir)

    @classmethod
    def new(
        cls,
        config: ComponentConfig,
        dependencies: Mapping[ResourceName, ResourceBase],
    ) -> "WebApp":
        return super().new(config, dependencies)

    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        attrs = struct_to_dict(config.attributes)
        assets_dir = attrs.get("assets_dir")
        if assets_dir is not None and not isinstance(assets_dir, str):
            raise Exception("'assets_dir' must be a string")
        return [], []

    def reconfigure(
        self,
        config: ComponentConfig,
        dependencies: Mapping[ResourceName, ResourceBase],
    ):
        attrs = struct_to_dict(config.attributes)
        new_dir = Path(attrs.get("assets_dir", self.base_dir)).expanduser().resolve()
        if new_dir != self.base_dir:
            self.base_dir = new_dir
            self.base_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Reconfigured to watch %s", self.base_dir)
        return super().reconfigure(config, dependencies)

    async def do_command(
        self,
        command: Mapping[str, Any],
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        cmd = command.get("command")
        logger.info("do_command received: %s", command)
        if cmd == "list_passes":
            return self._list_passes()
        if cmd == "get_file":
            pass_id = command.get("pass_id")
            filename = command.get("filename")
            return self._get_file(pass_id, filename)
        if cmd == "get_base_dir":
            return self._get_base_dir()
        raise ValueError(f"Unknown command: {cmd}")

    def _extract_timestamp(self, pass_id: str) -> str:
        match = re.search(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})", pass_id)
        if match:
            y, m, d, h, minute, second = match.groups()
            return f"{y}-{m}-{d} {h}:{minute}:{second}"

        match = re.search(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})", pass_id)
        if match:
            y, m, d, h, minute, second = match.groups()
            return f"{y}-{m}-{d} {h}:{minute}:{second}"

        match = re.search(r"(\d{10})", pass_id)
        if match:
            try:
                timestamp = int(match.group(1))
                return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        return "Unknown"

    def _list_passes(self) -> Mapping[str, Any]:
        passes: dict[str, Any] = {}
        if not self.base_dir.exists():
            return {"passes": passes}

        for pass_dir in self.base_dir.iterdir():
            if not pass_dir.is_dir():
                continue

            pass_id = pass_dir.name
            timestamp = self._extract_timestamp(pass_id)
            if timestamp == "Unknown":
                stat = pass_dir.stat()
                timestamp = datetime.fromtimestamp(stat.st_ctime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            is_complete = (pass_dir / ".complete").exists()

            passes[pass_id] = {
                "complete": is_complete,
                "timestamp": timestamp,
                "entries": [
                    self._describe_entry(child, pass_dir)
                    for child in sorted(pass_dir.iterdir(), key=lambda p: p.name.lower())
                    if not child.name.startswith(".")
                ],
            }

        logger.info("Listed %d passes", len(passes))
        return {"passes": passes}

    def _describe_entry(self, path: Path, root: Path) -> Mapping[str, Any]:
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        relative_path = path.relative_to(root).as_posix()
        if path.is_dir():
            return {
                "name": path.name,
                "kind": "directory",
                "modified": modified,
                "path": relative_path,
                "children": [
                    self._describe_entry(child, root)
                    for child in sorted(path.iterdir(), key=lambda p: p.name.lower())
                    if not child.name.startswith(".")
                ],
            }

        return {
            "name": path.name,
            "kind": "file",
            "modified": modified,
            "path": relative_path,
            "size": stat.st_size,
        }

    def _get_file(self, pass_id: str | None, filename: str | None) -> Mapping[str, Any]:
        if not pass_id or not filename:
            raise ValueError("pass_id and filename required")

        file_path = (self.base_dir / pass_id / filename).resolve()
        try:
            file_path.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError("Invalid path") from exc

        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"File not found: {pass_id}/{filename}")

        data = file_path.read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        logger.info("Serving file %s/%s (%d bytes)", pass_id, filename, len(data))
        return {"filename": filename, "data": encoded, "size": len(data)}

    def _get_base_dir(self) -> Mapping[str, Any]:
        return {"base_dir": str(self.base_dir)}


async def main() -> None:
    """Entrypoint used by run.sh to start the module host."""
    await Module.run_from_registry()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

