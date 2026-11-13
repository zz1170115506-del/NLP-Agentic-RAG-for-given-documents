"""Evidence Lab: a skill-augmented search agent for COMP5423."""

import os
import sys
from pathlib import Path

# Optional workspace-local dependencies avoid changing the user's global Python.
# A normal requirements installation works without either directory.
_root = Path(__file__).resolve().parent.parent
_local_packages = _root / ".runtime-packages"
if _local_packages.is_dir() and str(_local_packages) not in sys.path:
    sys.path.insert(0, str(_local_packages))
if (_root / ".hf-cache").is_dir():
    os.environ.setdefault("HF_HOME", str(_root / ".hf-cache"))

__version__ = "0.1.0"
