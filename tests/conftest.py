from __future__ import annotations

import sys
from pathlib import Path

# Make the src/ package importable when running tests without an install.
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
