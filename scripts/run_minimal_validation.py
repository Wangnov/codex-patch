from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import REPO_ROOT
from scripts.common import run_command

MINIMAL_VALIDATION: dict[str, list[list[str]]] = {
    "what-why-shnote": [
        [
            "cargo",
            "test",
            "-p",
            "codex-core",
            "test_exec_command_rejects_blank_what_and_why",
            "--",
            "--nocapture",
        ],
        [
            "cargo",
            "test",
            "-p",
            "codex-core",
            "rejects_escalated_permissions_when_policy_not_on_request",
            "--",
            "--nocapture",
        ],
    ],
    "cross-provider-defaults": [
        [
            "cargo",
            "test",
            "-p",
            "codex-app-server",
            "thread_list_without_provider_filter_includes_all_providers",
            "--",
            "--nocapture",
        ],
        [
            "cargo",
            "test",
            "-p",
            "codex-tui",
            "remote_thread_list_params_omit_provider_filter",
            "--",
            "--nocapture",
        ],
    ],
    "private-version-injection": [],
}


def validation_commands_for_group(group_name: str) -> list[list[str]]:
    return [list(command) for command in MINIMAL_VALIDATION.get(group_name, [])]


def run_validation(group_names: list[str], repo_root: Path = REPO_ROOT, dry_run: bool = False) -> None:
    codex_rs_root = repo_root / "codex-rs"
    for group_name in group_names:
        for command in validation_commands_for_group(group_name):
            if dry_run:
                continue
            run_command(command, cwd=codex_rs_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted codex-patch validation only.")
    parser.add_argument(
        "--group",
        action="append",
        dest="groups",
        choices=sorted(MINIMAL_VALIDATION),
        help="Patch group to validate. Repeat to run multiple groups.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    groups = args.groups or list(MINIMAL_VALIDATION)
    payload = {
        "dry_run": args.dry_run,
        "groups": groups,
        "commands": {group: validation_commands_for_group(group) for group in groups},
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    run_validation(groups, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
