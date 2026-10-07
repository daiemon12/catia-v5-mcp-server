from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

DEFAULT_BRIDGE_DIR_NAME = "CatiaPyBridge"


@dataclass(frozen=True)
class BridgePaths:
    root: Path
    pending: Path
    requests: Path
    responses: Path
    done: Path
    logs: Path

    @classmethod
    def from_root(cls, root: Path | str | None = None) -> "BridgePaths":
        if root is None:
            root = Path(os.getenv("TEMP") or os.getenv("TMP") or ".") / DEFAULT_BRIDGE_DIR_NAME
        root = Path(root)
        return cls(
            root=root,
            pending=root / "pending",
            requests=root / "requests",
            responses=root / "responses",
            done=root / "done",
            logs=root / "logs",
        )

    @property
    def current_job_path(self) -> Path:
        return self.pending / "current_job.json"

    def request_path(self, job_id: str) -> Path:
        return self.requests / f"{job_id}.request.json"

    def response_path(self, job_id: str) -> Path:
        return self.responses / f"{job_id}.response.json"

    def job_path(self, job_id: str) -> Path:
        return self.pending / f"{job_id}.job.json"

    def ensure(self) -> None:
        for path in [self.root, self.pending, self.requests, self.responses, self.done, self.logs]:
            path.mkdir(parents=True, exist_ok=True)
