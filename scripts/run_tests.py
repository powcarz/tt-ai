#!/usr/bin/env python3
"""Run tests using the correct Python interpreter.

Usage:
    python scripts/run_tests.py
    
Or from venv:
    python -m pytest -v
"""

import subprocess
import sys


def main():
    """Run pytest with the current Python interpreter."""
    print(f"Using Python: {sys.executable}")
    print(f"Python version: {sys.version}")
    print()
    
    # Run pytest as a module to ensure correct interpreter
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v"] + sys.argv[1:],
        cwd=None,  # Use current directory
    )
    
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
