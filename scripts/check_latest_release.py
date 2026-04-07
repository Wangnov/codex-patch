from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import JSONDict
from scripts.common import STATE_PATH
from scripts.common import load_state
from scripts.common import save_state
from scripts.common import utc_now_iso

LATEST_RELEASE_API = "https://api.github.com/repos/openai/codex/releases/latest"


def should_start_replay(latest_release: str | None, replayed_release: str | None) -> bool:
    return bool(latest_release and latest_release != replayed_release)


def github_token_from_env_or_gh() -> str | None:
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        return github_token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    token = result.stdout.strip()
    return token or None


def fetch_latest_release_info(api_url: str = LATEST_RELEASE_API) -> JSONDict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codex-patch-release-check",
    }
    github_token = github_token_from_env_or_gh()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    request = urllib.request.Request(api_url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        payload: dict[str, Any] = json.load(response)

    return {
        "html_url": payload.get("html_url"),
        "name": payload.get("name"),
        "published_at": payload.get("published_at"),
        "tag_name": payload.get("tag_name"),
    }


def updated_state_for_latest_release(state: JSONDict, latest_release: str | None) -> JSONDict:
    next_state = dict(state)
    next_state["latest_release_seen"] = latest_release
    next_state["updated_at"] = utc_now_iso()
    return next_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check openai/codex latest release state.")
    parser.add_argument("--dry-run", action="store_true", help="Do not update state files.")
    parser.add_argument(
        "--release-tag",
        help="Optional explicit release tag to use instead of querying GitHub.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=STATE_PATH,
        help="Path to latest-release state JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = load_state(args.state_file)
    latest_info = (
        {
            "html_url": None,
            "name": args.release_tag,
            "published_at": None,
            "tag_name": args.release_tag,
        }
        if args.release_tag
        else fetch_latest_release_info()
    )
    latest_tag = latest_info.get("tag_name")
    replayed_tag = state.get("latest_release_replayed")
    replay_needed = should_start_replay(latest_tag, replayed_tag)
    next_state = updated_state_for_latest_release(state, latest_tag)

    if not args.dry_run:
        save_state(args.state_file, next_state)

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "latest_release": latest_tag,
                "latest_release_replayed": replayed_tag,
                "release_url": latest_info.get("html_url"),
                "should_start_replay": replay_needed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
