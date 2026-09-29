"""Tiny lakehouse: Parquet tables on disk + DuckDB as the SQL engine.

Why not a database server? The pipeline (writer) and the API (reader) run in
different processes. Parquet files replaced atomically (`os.replace`) give
lock-free snapshot reads, and DuckDB queries them in-process at columnar
speed — zero infrastructure to install on a laptop.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ..config import get_settings


class Lake:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or get_settings().lake_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, pd.DataFrame]] = {}

    # ---- tables -----------------------------------------------------------
    def path(self, name: str) -> Path:
        return self.root / f"{name}.parquet"

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def write(self, name: str, df: pd.DataFrame) -> Path:
        p = self.path(name)
        tmp = p.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=True)
        os.replace(tmp, p)
        self._cache.pop(name, None)
        return p

    def read(self, name: str) -> pd.DataFrame:
        """Read a table; memoised on file mtime so API reads are ~free."""
        p = self.path(name)
        if not p.exists():
            raise FileNotFoundError(f"lake table '{name}' not found — run the pipeline first")
        mtime = p.stat().st_mtime
        with self._lock:
            hit = self._cache.get(name)
            if hit and hit[0] == mtime:
                return hit[1]
        df = pd.read_parquet(p)
        with self._lock:
            self._cache[name] = (mtime, df)
        return df

    def mtime(self, name: str) -> float | None:
        p = self.path(name)
        return p.stat().st_mtime if p.exists() else None

    def sql(self, query: str, **params: Any) -> pd.DataFrame:
        """Run SQL where every lake table is available as a view."""
        con = duckdb.connect()
        try:
            for f in self.root.glob("*.parquet"):
                con.execute(
                    f"CREATE VIEW \"{f.stem}\" AS SELECT * FROM read_parquet('{f.as_posix()}')"
                )
            return con.execute(query, params or None).df()
        finally:
            con.close()

    # ---- json documents (small metadata) ----------------------------------
    def write_json(self, name: str, obj: Any) -> None:
        p = self.root / f"{name}.json"
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(obj, indent=2, default=str))
        os.replace(tmp, p)

    def read_json(self, name: str, default: Any = None) -> Any:
        p = self.root / f"{name}.json"
        if not p.exists():
            return default
        return json.loads(p.read_text())

    def append_jsonl(self, name: str, obj: Any) -> None:
        p = self.root / f"{name}.jsonl"
        with p.open("a") as fh:
            fh.write(json.dumps(obj, default=str) + "\n")

    def read_jsonl(self, name: str, last: int = 50) -> list[dict]:
        p = self.root / f"{name}.jsonl"
        if not p.exists():
            return []
        lines = p.read_text().strip().splitlines()
        return [json.loads(x) for x in lines[-last:]]


_LAKE: Lake | None = None


def get_lake() -> Lake:
    global _LAKE
    if _LAKE is None:
        _LAKE = Lake()
    return _LAKE
