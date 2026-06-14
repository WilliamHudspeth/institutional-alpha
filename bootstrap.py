#!/usr/bin/env python3
import sys
from pathlib import Path

# Add src to path so we can import iam
sys.path.insert(0, str(Path(__file__).parent / "src"))

from iam.bootstrap import initialize_system

if __name__ == "__main__":
    if initialize_system():
        print("\nEnvironment is ready. Launch with: python launcher.py")
    else:
        sys.exit(1)
