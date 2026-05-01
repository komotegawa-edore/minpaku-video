from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        )
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.close()
        Path(tmp.name).replace(path)
    except BaseException:
        if tmp is not None:
            Path(tmp.name).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        )
        tmp.write(text)
        tmp.close()
        Path(tmp.name).replace(path)
    except BaseException:
        if tmp is not None:
            Path(tmp.name).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
