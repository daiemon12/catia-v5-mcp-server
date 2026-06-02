#!/usr/bin/env python3
"""Fetch repo traffic stats from GitHub and merge them into versioned history files.

GitHub only exposes the last 14 days of clones/views data, so this script
is meant to be run on a schedule (see .github/workflows/traffic.yml) so the
history accumulates over time in `traffic/clones.json` and `traffic/views.json`.

For overlapping days already present in history, we keep the maximum value:
counts within the 14-day window can still grow as the day progresses, and
once the day rolls out of the window the stored value is the final tally.

Also writes:
  - traffic/badge-clones.json and traffic/badge-views.json — shields.io
    endpoint-format files consumed by the README badges.
  - traffic/chart.png — daily clones+views chart, regenerated each run
    (matplotlib only; the script silently skips it if matplotlib is missing).
"""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
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


def write_history(name: str, data: dict) -> list[dict]:
    """Merge incoming data into the JSON+CSV history files. Return the merged history."""
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

    return merged


def write_badge(name: str, label: str, value: int, color: str) -> None:
    badge = {
        "schemaVersion": 1,
        "label": label,
        "message": f"{value:,}".replace(",", " "),
        "color": color,
    }
    (TRAFFIC_DIR / f"badge-{name}.json").write_text(json.dumps(badge, indent=2) + "\n")


def render_chart(clones: list[dict], views: list[dict], repo: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping chart", file=sys.stderr)
        return

    def parse(rows: list[dict]) -> tuple[list, list]:
        dates = [datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in rows]
        vals = [r["count"] for r in rows]
        return dates, vals

    v_dates, v_vals = parse(views)
    c_dates, c_vals = parse(clones)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    fig.patch.set_facecolor("white")

    ax1.fill_between(v_dates, v_vals, alpha=0.25, color="#2563eb")
    ax1.plot(v_dates, v_vals, color="#2563eb", linewidth=2, marker="o", markersize=4)
    ax1.set_ylabel("Views / day", fontsize=11)
    ax1.set_title(
        f"Repository traffic — {repo}    (total: {sum(v_vals):,} views • {sum(c_vals):,} clones)".replace(",", " "),
        fontsize=12,
        fontweight="bold",
    )

    ax2.fill_between(c_dates, c_vals, alpha=0.25, color="#16a34a")
    ax2.plot(c_dates, c_vals, color="#16a34a", linewidth=2, marker="o", markersize=4)
    ax2.set_ylabel("Clones / day", fontsize=11)
    ax2.set_xlabel("Date")

    for ax in (ax1, ax2):
        ax.grid(alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(TRAFFIC_DIR / "chart.png", dpi=120, bbox_inches="tight")
    plt.close(fig)


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

    clones_history = write_history("clones", clones)
    views_history = write_history("views", views)

    clones_total = sum(r["count"] for r in clones_history)
    views_total = sum(r["count"] for r in views_history)

    write_badge("clones", "clones", clones_total, "16a34a")
    write_badge("views", "views", views_total, "2563eb")

    render_chart(clones_history, views_history, repo)

    print(f"Updated traffic history for {repo} in {TRAFFIC_DIR}")
    print(f"  cumulative clones: {clones_total} | cumulative views: {views_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
