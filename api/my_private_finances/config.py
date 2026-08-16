from __future__ import annotations

import os
from pathlib import Path


def get_data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data"))
