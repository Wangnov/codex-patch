from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_latest_release import fetch_latest_release_info
from scripts.check_latest_release import should_start_replay
from scripts.common import JSONDict
from scripts.common import REPO_ROOT
from scripts.common import load_patch_manifest
from scripts.common import load_release_manifest
from scripts.common import load_state
from scripts.common import replay_result_payload
from scripts.common import run_command
from scripts.common import save_state
from scripts.common import utc_now_iso
from scripts.run_minimal_validation import MINIMAL_VALIDATION
from scripts.run_minimal_validation import run_validation
from scripts.update_private_version import private_display_version
from scripts.update_private_version import private_release_tag
from scripts.update_private_version import update_private_version_files
from scripts.write_replay_result import replay_result_path
from scripts.write_replay_result import write_replay_result

PATCH_GROUP_ORDER = [
    "what-why-shnote",
    "cross-provider-defaults",
    "private-version-injection",
]

VERSION_TOUCHPOINTS = [
    "codex-cli/package.json",
    "codex-rs/Cargo.toml",
    "codex-rs/default.nix",
    "codex-rs/responses-api-proxy/npm/package.json",
    "release/release-manifest.json",
    "sdk/typescript/package.json",
]

STATE_FILE = "state/latest-release.json"


def replay_branch_name(release_tag: str) -> str:
    return f"replay/{release_tag}"


def refuse_when_replay_active(state: JSONDict) -> bool:
    return state.get("active_replay_status") == "running"


def next_private_generation(release_manifest: JSONDict, release_tag: str) -> int:
    if release_manifest.get("upstream_tag") == release_tag:
        generation = release_manifest.get("private_patch_generation")
        if isinstance(generation, int):
            return generation + 1
    return 1


def ordered_patch_groups(manifest: JSONDict) -> list[JSONDict]:
    groups_by_name = {group["name"]: group for group in manifest.get("groups", [])}
    return [groups_by_name[name] for name in PATCH_GROUP_ORDER if name in groups_by_name]


def replay_lock_path(repo_root: Path, release_tag: str) -> Path:
    return repo_root / "state" / "replays" / f"{release_tag}.lock"


def git_ref_exists(repo_root: Path, ref_name: str) -> bool:
    try:
        run_command(
            ["git", "rev-parse", "-q", "--verify", ref_name],
            cwd=repo_root,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    return True


def origin_remote_exists(repo_root: Path) -> bool:
    try:
        run_command(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_root,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    return True


def ensure_release_tag(repo_root: Path, release_tag: str) -> None:
    if git_ref_exists(repo_root, f"refs/tags/{release_tag}"):
        return

    run_command(
        ["git", "fetch", "upstream", f"refs/tags/{release_tag}:refs/tags/{release_tag}"],
        cwd=repo_root,
    )


def ensure_private_tag_absent(repo_root: Path, private_tag: str) -> None:
    if git_ref_exists(repo_root, f"refs/tags/{private_tag}"):
        raise RuntimeError(f"Private release tag already exists: {private_tag}")


def replay_plan(repo_root: Path, release_tag: str) -> JSONDict:
    manifest = load_patch_manifest(repo_root / "patches" / "private-patch-manifest.json")
    release_manifest = load_release_manifest(repo_root / "release" / "release-manifest.json")
    generation = next_private_generation(release_manifest, release_tag)
    display_version = private_display_version(release_tag, generation)
    private_tag = private_release_tag(release_tag, generation)
    result_path = replay_result_path(repo_root, release_tag)
    ordered_groups = ordered_patch_groups(manifest)
    return {
        "display_version": display_version,
        "origin_remote_configured": origin_remote_exists(repo_root),
        "patch_groups": [group["name"] for group in ordered_groups],
        "private_git_tag": private_tag,
        "private_patch_generation": generation,
        "replay_branch": replay_branch_name(release_tag),
        "replay_result_file": str(result_path.relative_to(repo_root)),
        "release_tag": release_tag,
        "state_touchpoints": [
            STATE_FILE,
            str(result_path.relative_to(repo_root)),
        ],
        "validation_commands": {
            group["name"]: MINIMAL_VALIDATION.get(group["name"], [])
            for group in ordered_groups
            if MINIMAL_VALIDATION.get(group["name"])
        },
        "version_touchpoints": list(VERSION_TOUCHPOINTS),
    }


def running_state(state: JSONDict, release_tag: str, branch_name: str) -> JSONDict:
    next_state = dict(state)
    next_state["active_replay_branch"] = branch_name
    next_state["active_replay_status"] = "running"
    next_state["last_failure_summary"] = None
    next_state["latest_release_seen"] = release_tag
    next_state["updated_at"] = utc_now_iso()
    return next_state


def success_state(state: JSONDict, release_tag: str, display_version: str) -> JSONDict:
    next_state = dict(state)
    next_state["active_private_version"] = display_version
    next_state["active_replay_branch"] = None
    next_state["active_replay_status"] = "idle"
    next_state["last_failure_summary"] = None
    next_state["latest_release_replayed"] = release_tag
    next_state["latest_release_seen"] = release_tag
    next_state["updated_at"] = utc_now_iso()
    return next_state


def failure_state(
    state: JSONDict,
    release_tag: str,
    branch_name: str,
    failure_summary: str,
) -> JSONDict:
    next_state = dict(state)
    next_state["active_replay_branch"] = branch_name
    next_state["active_replay_status"] = "failed"
    next_state["last_failure_summary"] = failure_summary
    next_state["latest_release_seen"] = release_tag
    next_state["updated_at"] = utc_now_iso()
    return next_state


def apply_patch_group(repo_root: Path, group: JSONDict, plan: JSONDict) -> None:
    group_name = group["name"]
    if group_name == "private-version-injection":
        update_private_version_files(
            repo_root,
            plan["release_tag"],
            int(plan["private_patch_generation"]),
        )
        run_command(["git", "add", *VERSION_TOUCHPOINTS], cwd=repo_root)
        run_command(
            [
                "git",
                "commit",
                "-m",
                f"chore(release): inject private version {plan['display_version']}",
            ],
            cwd=repo_root,
        )
        return

    source_repo = Path(group["source_repo"]).resolve()
    if source_repo != repo_root.resolve():
        raise RuntimeError(
            f"Patch group {group_name} points at {source_repo}, but replay expects {repo_root}"
        )

    for source_commit in group.get("source_commits", []):
        run_command(["git", "cherry-pick", "-x", source_commit], cwd=repo_root)


def record_success_state(
    repo_root: Path,
    release_tag: str,
    state: JSONDict,
    plan: JSONDict,
    applied_groups: list[str],
    validations_run: list[list[str]],
) -> JSONDict:
    state_path = repo_root / STATE_FILE
    final_state = success_state(state, release_tag, plan["display_version"])
    save_state(state_path, final_state)
    result_payload = replay_result_payload(
        release_tag,
        "success",
        applied_groups=applied_groups,
        display_version=plan["display_version"],
        origin_remote_configured=origin_remote_exists(repo_root),
        private_git_tag=plan["private_git_tag"],
        replay_branch=plan["replay_branch"],
        validations_run=validations_run,
    )
    result_path = write_replay_result(repo_root, release_tag, result_payload)
    run_command(
        [
            "git",
            "add",
            STATE_FILE,
            str(result_path.relative_to(repo_root)),
        ],
        cwd=repo_root,
    )
    run_command(
        [
            "git",
            "commit",
            "-m",
            f"chore(release): record replay state for {release_tag}",
        ],
        cwd=repo_root,
    )
    return result_payload


def perform_replay(repo_root: Path, release_tag: str, dry_run: bool) -> JSONDict:
    state_path = repo_root / STATE_FILE
    state = load_state(state_path)
    if refuse_when_replay_active(state):
        raise RuntimeError("Refusing replay because another replay is already marked as running.")

    plan = replay_plan(repo_root, release_tag)
    if dry_run:
        return plan

    branch_name = plan["replay_branch"]
    lock_path = replay_lock_path(repo_root, release_tag)
    save_state(state_path, running_state(state, release_tag, branch_name))
    lock_path.write_text(f"{utc_now_iso()}\n", encoding="utf-8")

    try:
        ensure_release_tag(repo_root, release_tag)
        ensure_private_tag_absent(repo_root, plan["private_git_tag"])
        run_command(["git", "checkout", "-B", branch_name, release_tag], cwd=repo_root)
        manifest = load_patch_manifest(repo_root / "patches" / "private-patch-manifest.json")
        applied_groups: list[str] = []
        validations_run: list[list[str]] = []
        for group in ordered_patch_groups(manifest):
            apply_patch_group(repo_root, group, plan)
            applied_groups.append(group["name"])
            validation_commands = MINIMAL_VALIDATION.get(group["name"], [])
            if validation_commands:
                run_validation([group["name"]], repo_root=repo_root)
                validations_run.extend(validation_commands)

        record_success_state(
            repo_root,
            release_tag,
            state,
            plan,
            applied_groups,
            validations_run,
        )
        run_command(["git", "tag", plan["private_git_tag"]], cwd=repo_root)
        run_command(["git", "branch", "-f", "patch/main", branch_name], cwd=repo_root)
        run_command(["git", "checkout", "patch/main"], cwd=repo_root)
        return plan
    except Exception as err:
        summary = str(err)
        save_state(state_path, failure_state(state, release_tag, branch_name, summary))
        result_payload = replay_result_payload(
            release_tag,
            "failure",
            failure_summary=summary,
            replay_branch=branch_name,
        )
        write_replay_result(repo_root, release_tag, result_payload)
        raise
    finally:
        if lock_path.exists():
            lock_path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay codex-patch onto an upstream release.")
    parser.add_argument("--dry-run", action="store_true", help="Print the replay plan only.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replay even when the state says the latest release is already replayed.",
    )
    parser.add_argument("--release-tag", help="Explicit upstream release tag to replay.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    state = load_state(repo_root / STATE_FILE)
    release_tag = args.release_tag
    if release_tag is None:
        release_tag = fetch_latest_release_info()["tag_name"]
        if not args.force and not should_start_replay(
            release_tag,
            state.get("latest_release_replayed"),
        ):
            print(
                json.dumps(
                    {
                        "reason": "latest release already replayed",
                        "release_tag": release_tag,
                        "result_file": str(replay_result_path(repo_root, release_tag)),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

    plan = perform_replay(repo_root, release_tag, args.dry_run)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
