from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLIENT_NAME = "catia_caa_bridge"
CLIENT_VERSION = "0.1.0"


def new_job_id() -> str:
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


@dataclass(frozen=True)
class BridgeRequest:
    id: str
    method: str
    params: dict[str, Any]
    client: dict[str, str]

    @classmethod
    def create(
        cls, method: str, params: dict[str, Any] | None = None, job_id: str | None = None
    ) -> BridgeRequest:
        return cls(
            id=job_id or new_job_id(),
            method=method,
            params=params or {},
            client={"name": CLIENT_NAME, "version": CLIENT_VERSION},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CurrentJob:
    job_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
