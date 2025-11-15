#!/usr/bin/env python3
"""
Entry point for the pyMiceTracking Panel application.
"""

import sys
from pathlib import Path

# Add src directory to Python path to enable imports
src_dir = Path(__file__).parent
sys.path.insert(0, str(src_dir))

from pymicetracking_panel import main

if __name__ == "__main__":
    main()
