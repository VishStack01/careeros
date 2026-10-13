"""Where uploaded files live. A private local directory today; the interface is
small so an encrypted object store (S3, GCS, R2) can replace it for multi-node
deployments without touching the API."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

_KEY = re.compile(r"^[a-f0-9]{32}/[a-f0-9]{32}\.[a-z0-9]{1,8}$")


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError("bad storage key")
        return self.root / key

    def put(self, user_id: str, asset_id: str, ext: str, data: bytes) -> str:
        key = f"{user_id}/{asset_id}.{ext}"
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def delete_user(self, user_id: str) -> None:
        if re.fullmatch(r"[a-f0-9]{32}", user_id):
            shutil.rmtree(self.root / user_id, ignore_errors=True)
