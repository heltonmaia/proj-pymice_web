import sys
from pathlib import Path

# Put pymice/ (which contains run.py) on sys.path for `import run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
