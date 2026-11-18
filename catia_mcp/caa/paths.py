from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BRIDGE_ROOT_ENV = "CATIA_MCP_CAA_BRIDGE_ROOT"
BRIDGE_ROOT_NAME = "jobs"


@dataclass(frozen=True)
class BridgePaths:
    root: Path
    pending: Path
    requests: Path
    responses: Path
    done: Path
    logs: Path

    @classmethod
    def from_root(cls, root: Path | str) -> BridgePaths:
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

    def ensure(self) -> None:
        for path in [self.root, self.pending, self.requests, self.responses, self.done, self.logs]:
            path.mkdir(parents=True, exist_ok=True)
