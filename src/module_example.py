#!/usr/bin/env python3
"""
Example: How your calibration module would write files
for the webapp watcher to detect.

This demonstrates the "sentinel file" pattern that sanding-webapp
likely uses.
"""

import json
import time
from pathlib import Path
from datetime import datetime


class CalibrationModuleExample:
    """
    Example of how your hand-eye calibration module would save files.
    The webapp watches for the .complete sentinel file.
    """
    
    def __init__(self, data_dir: str = "module-data/calibration-passes"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def run_calibration(self, pass_id: str):
        """
        Run a calibration pass and save all data.
        Webapp will detect it when .complete file is written.
        """
        print(f"🎯 Starting calibration pass: {pass_id}")
        
        # 1. Create pass directory
        pass_dir = self.data_dir / pass_id
        pass_dir.mkdir(parents=True, exist_ok=True)
        print(f"   Created directory: {pass_dir}")
        
        # 2. Write metadata FIRST (tells webapp what to expect)
        metadata = {
            "pass_id": pass_id,
            "started_at": datetime.now().isoformat(),
            "robot": "UR20",
            "camera": "realsense-d435",
            "method": "CALIB_HAND_EYE_TSAI",
            "expected_images": 10
        }
        metadata_file = pass_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))
        print(f"   ✓ Wrote metadata.json")
        
        # 3. Simulate capturing images and transforms
        print(f"   Capturing calibration data...")
        for i in range(10):
            # Save image (simulated)
            image_data = f"Image {i} data".encode()
            image_file = pass_dir / f"calibration_image_{i:03d}.png"
            image_file.write_bytes(image_data)
            
            # Save corresponding transform
            transform = {
                "index": i,
                "position": {"x": 100 + i*10, "y": 200, "z": 300},
                "orientation": {"o_x": 0, "o_y": 0, "o_z": 1, "theta": i*15}
            }
            transform_file = pass_dir / f"transform_{i:03d}.json"
            transform_file.write_text(json.dumps(transform, indent=2))
            
            print(f"      {i+1}/10 captured")
            time.sleep(0.2)  # Simulate capture time
        
        # 4. Run calibration computation
        print(f"   Computing calibration...")
        time.sleep(1)
        
        result = {
            "camera_matrix": {
                "fx": 1234.56,
                "fy": 1235.67,
                "cx": 320.12,
                "cy": 240.34
            },
            "distortion": {
                "k1": -0.123,
                "k2": 0.045,
                "p1": -0.001,
                "p2": 0.002
            },
            "transformation": {
                "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "translation": [0.1, 0.2, 0.3]
            },
            "rms_error": 0.234,
            "method": "CALIB_HAND_EYE_TSAI",
            "num_poses": 10
        }
        
        # 5. Save calibration result
        result_file = pass_dir / "calibration_result.json"
        result_file.write_text(json.dumps(result, indent=2))
        print(f"   ✓ Saved calibration_result.json")
        
        # 6. CRITICAL: Write .complete sentinel file LAST
        # This tells the webapp the pass is ready for processing
        complete_data = {
            "completed_at": datetime.now().isoformat(),
            "num_files": len(list(pass_dir.iterdir())),
            "rms_error": result["rms_error"]
        }
        sentinel_file = pass_dir / ".complete"
        sentinel_file.write_text(json.dumps(complete_data, indent=2))
        print(f"   ✓ Marked as complete (.complete file written)")
        
        print(f"✅ Calibration pass complete: {pass_id}")
        print(f"   Directory: {pass_dir}")
        print(f"   Files: {len(list(pass_dir.iterdir()))}")
        print()
        print(f"   👀 Webapp should detect this pass now!")


def demonstrate_pattern():
    """Show how the module-webapp interaction works"""
    
    print("=" * 70)
    print("DEMONSTRATION: Module writes files, Webapp detects them")
    print("=" * 70)
    print()
    
    print("📝 Pattern:")
    print("  1. Module creates pass directory")
    print("  2. Module writes metadata.json")
    print("  3. Module writes all calibration files")
    print("  4. Module writes .complete sentinel file ← WEBAPP DETECTS THIS")
    print("  5. Webapp processes the completed pass")
    print()
    print("=" * 70)
    print()
    
    # Run a calibration pass
    module = CalibrationModuleExample()
    
    # Simulate running calibration
    module.run_calibration("pass-demo-001")
    
    print()
    print("=" * 70)
    print("Now check:")
    print("  1. Look in module-data/calibration-passes/pass-demo-001/")
    print("  2. You should see .complete file")
    print("  3. If webapp is running, it will detect and process this pass")
    print("=" * 70)


def demonstrate_incomplete_pass():
    """Show what happens if module crashes before completing"""
    
    print("\n" + "=" * 70)
    print("DEMONSTRATION: Incomplete pass (module crashed)")
    print("=" * 70)
    print()
    
    module = CalibrationModuleExample()
    pass_id = "pass-crashed-002"
    pass_dir = module.data_dir / pass_id
    pass_dir.mkdir(parents=True, exist_ok=True)
    
    # Write some files but DON'T write .complete
    (pass_dir / "metadata.json").write_text('{"status": "started"}')
    (pass_dir / "image_000.png").write_text("partial data")
    
    print(f"   Created incomplete pass: {pass_id}")
    print(f"   Files: {list(pass_dir.iterdir())}")
    print(f"   ❌ No .complete file")
    print()
    print(f"   👀 Webapp will NOT process this pass (incomplete)")
    print("=" * 70)


if __name__ == "__main__":
    # Demo 1: Complete pass
    demonstrate_pattern()
    
    # Demo 2: Incomplete pass
    demonstrate_incomplete_pass()
    
    print("\n" + "=" * 70)
    print("KEY TAKEAWAYS:")
    print("=" * 70)
    print("✓ Module writes files in pass directory")
    print("✓ Module writes .complete sentinel file when done")
    print("✓ Webapp watches for .complete files")
    print("✓ Webapp only processes complete passes")
    print("✓ Zero coupling - module doesn't need to know about webapp!")
    print("=" * 70)