"""Mock of the S01 API contract (T08). Run from backend/: uv run uvicorn mock.app:app"""

import sys
from pathlib import Path

# api.py lives in docs/contracts/; make it importable as `api`.
_CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts"
if str(_CONTRACTS) not in sys.path:
    sys.path.insert(0, str(_CONTRACTS))
