#!/usr/bin/env python3
"""Fetch repo traffic stats from GitHub and merge them into versioned history files.

GitHub only exposes the last 14 days of clones/views data, so this script
is meant to be run on a schedule (see .github/workflows/traffic.yml) so the
history accumulates over time in `traffic/clones.json` and `traffic/views.json`.

For overlapping days already present in history, we keep the maximum value:
counts within the 14-day window can still grow as the day progresses, and
once the day rolls out of the window the stored value is the final tally.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = "https://api.github.com"
TRAFFIC_DIR = Path(__file__).resolve().parent.parent / "traffic"


def gh_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "catia-v5-mcp-server-traffic-collector",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def merge_daily(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_ts: dict[str, dict] = {row["timestamp"]: row for row in existing}
    for row in incoming:
        ts = row["timestamp"]
        prev = by_ts.get(ts)
        if prev is None:
            by_ts[ts] = {
                "timestamp": ts,
                "count": row["count"],
                "uniques": row["uniques"],
            }
        else:
            by_ts[ts] = {
                "timestamp": ts,
                "count": max(prev["count"], row["count"]),
                "uniques": max(prev["uniques"], row["uniques"]),
            }
    return sorted(by_ts.values(), key=lambda r: r["timestamp"])


def write_outputs(name: str, data: dict) -> None:
    TRAFFIC_DIR.mkdir(parents=True, exist_ok=True)
    json_path = TRAFFIC_DIR / f"{name}.json"
    csv_path = TRAFFIC_DIR / f"{name}.csv"

    existing = []
    if json_path.exists():
        existing = json.loads(json_path.read_text()).get("history", [])

    merged = merge_daily(existing, data.get(name, []))
    payload = {
        "totals": {
            "count": sum(r["count"] for r in merged),
            "uniques_last_seen": data.get("uniques", 0),
            "count_last_window": data.get("count", 0),
        },
        "history": merged,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n")

    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "count", "uniques"])
        for row in merged:
            writer.writerow([row["timestamp"], row["count"], row["uniques"]])


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY env vars are required", file=sys.stderr)
        return 1

    try:
        clones = gh_get(f"/repos/{repo}/traffic/clones", token)
        views = gh_get(f"/repos/{repo}/traffic/views", token)
    except urllib.error.HTTPError as e:
        print(f"GitHub API error {e.code}: {e.read().decode('utf-8', 'replace')}", file=sys.stderr)
        return 1

    write_outputs("clones", clones)
    write_outputs("views", views)
    print(f"Updated traffic history for {repo} in {TRAFFIC_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
