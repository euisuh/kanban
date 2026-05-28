from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_fqdn_patch = patch("socket.getfqdn", return_value="localhost")
_fqdn_patch.start()
