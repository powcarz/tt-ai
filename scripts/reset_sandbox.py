#!/usr/bin/env python3
"""Reset sandbox to clean state for demo purposes.

Usage:
    python scripts/reset_sandbox.py

This script clears all applied actions from the sandbox:
- applied_invoices.json
- applied_credit_memos.json
- applied_amendments.json
- audit_log.json
"""

import json
from pathlib import Path


def reset_sandbox():
    """Reset all sandbox files to empty state."""
    # Find project root (script is in scripts/ folder)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    sandbox_dir = project_root / "data" / "sandbox"
    
    files_to_reset = [
        "applied_invoices.json",
        "applied_credit_memos.json",
        "applied_amendments.json",
        "audit_log.json",
    ]
    
    print("=" * 50)
    print("Sandbox Reset Script")
    print("=" * 50)
    print(f"Sandbox directory: {sandbox_dir}")
    print()
    
    for filename in files_to_reset:
        filepath = sandbox_dir / filename
        
        # Check current state
        if filepath.exists():
            with open(filepath, "r") as f:
                try:
                    data = json.load(f)
                    item_count = len(data) if isinstance(data, list) else "N/A"
                except json.JSONDecodeError:
                    item_count = "invalid JSON"
        else:
            item_count = "file missing"
        
        # Reset to empty array
        with open(filepath, "w") as f:
            json.dump([], f, indent=2)
        
        print(f"✓ Reset {filename} (was: {item_count} items)")
    
    print()
    print("=" * 50)
    print("Sandbox reset complete!")
    print("=" * 50)


if __name__ == "__main__":
    reset_sandbox()
