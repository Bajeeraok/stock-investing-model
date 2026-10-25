"""Save today's FMP analyst consensus vintage into the PIT store (see signals/alpha/estimates_snapshot.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config_loader import load_config  # noqa: E402
from signals.alpha.estimates_snapshot import run  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(run(load_config())))
