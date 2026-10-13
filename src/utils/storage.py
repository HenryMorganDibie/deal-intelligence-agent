"""
JSON file storage shared by every on-disk store under data/.

Writes are atomic (temp file + os.replace), so a crash mid-write cannot leave
a truncated file. A file that cannot be parsed is moved aside, never silently
treated as empty and then overwritten by the next save.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def load_json(path: Path, default: Callable[[], Any]) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return default()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        backup = path.with_name(f"{path.name}.unreadable-{datetime.utcnow():%Y%m%d%H%M%S}")
        path.rename(backup)
        print(f"warning: {path} could not be read; moved to {backup.name} and starting empty",
              file=sys.stderr)
        return default()


def save_json(path: Path, data: Any, **dumps_kwargs: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dumps_kwargs.setdefault("indent", 2)
    dumps_kwargs.setdefault("default", str)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, **dumps_kwargs), encoding="utf-8")
    os.replace(tmp, path)
