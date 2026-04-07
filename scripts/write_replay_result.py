from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import REPO_ROOT
from scripts.common import replay_result_payload
from scripts.common import save_json


def replay_result_path(repo_root: Path, upstream_tag: str) -> Path:
    return repo_root / "state" / "replays" / f"{upstream_tag}.json"


def write_replay_result(repo_root: Path, upstream_tag: str, payload: dict[str, object]) -> Path:
    path = replay_result_path(repo_root, upstream_tag)
    save_json(path, payload)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a codex-patch replay result file.")
    parser.add_argument("--upstream-tag", required=True)
    parser.add_argument(
        "--outcome",
        required=True,
        choices=["success", "failure", "needs-human"],
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--replay-branch")
    parser.add_argument("--display-version")
    parser.add_argument("--private-git-tag")
    parser.add_argument("--failure-summary")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = replay_result_payload(
        args.upstream_tag,
        args.outcome,
        display_version=args.display_version,
        failure_summary=args.failure_summary,
        private_git_tag=args.private_git_tag,
        replay_branch=args.replay_branch,
    )
    path = write_replay_result(args.repo_root, args.upstream_tag, payload)
    print(json.dumps({"path": str(path), "payload": payload}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
