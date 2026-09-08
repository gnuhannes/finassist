"""Dump the FastAPI OpenAPI schema to ``api/openapi.json`` (issue #112).

The committed JSON is the contract the frontend's generated types
(``app/src/lib/api/schema.d.ts``) are built from. ``make check-openapi``
regenerates both and fails if they drift from what's committed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_API_ROOT))

from my_private_finances.main import create_app  # noqa: E402

_OUT = _API_ROOT / "openapi.json"


def main() -> None:
    schema = create_app().openapi()
    _OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {_OUT} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
