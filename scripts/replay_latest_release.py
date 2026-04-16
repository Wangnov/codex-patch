from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_latest_release import fetch_latest_release_info
from scripts.check_latest_release import should_start_replay
from scripts.common import JSONDict
from scripts.common import REPO_ROOT
from scripts.common import codex_exec_environment
from scripts.common import ensure_repo_runtime_dirs
from scripts.common import load_patch_manifest
from scripts.common import load_release_manifest
from scripts.common import load_state
from scripts.common import replay_result_payload
from scripts.common import repo_runtime_paths
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
PROMPT_TEMPLATE = ".codex/prompts/replay-latest-release.md"
PATCH_REPO_METADATA_SOURCE_REF = "patch/main"
PATCH_REPO_METADATA_TOUCHPOINTS = (
    ".codex",
    ".github/workflows/release-draft.yml",
    ".github/workflows/release-matrix.yml",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "patches/private-patch-manifest.json",
    "scripts",
    "tests",
)
PATCH_REPO_METADATA_COMMIT_MESSAGE = "chore(replay): sync patch repo metadata"


def replay_branch_name(release_tag: str) -> str:
    return f"replay/{release_tag}"


def replay_lock_paths(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "state" / "replays").glob("*.lock"))


def refuse_when_replay_active(repo_root: Path) -> bool:
    return bool(replay_lock_paths(repo_root))


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


def codex_last_message_path(repo_root: Path, release_tag: str) -> Path:
    runtime_paths = repo_runtime_paths(repo_root)
    return Path(runtime_paths["last_message_dir"]) / f"{release_tag}.md"


def format_patch_groups_for_prompt(manifest: JSONDict) -> str:
    lines: list[str] = []
    for group in ordered_patch_groups(manifest):
        if group["name"] == "private-version-injection":
            continue
        commits = ", ".join(group.get("source_commits", [])) or "version-injection-only"
        lines.append(f"- {group['name']}: {commits}")
    return "\n".join(lines)


def format_validation_commands_for_prompt(plan: JSONDict) -> str:
    lines: list[str] = []
    for group_name in plan["patch_groups"]:
        commands = plan["validation_commands"].get(group_name, [])
        if not commands:
            continue
        lines.append(f"- {group_name}:")
        for command in commands:
            lines.append(f"  - {' '.join(command)}")
    return "\n".join(lines) or "- No validation commands configured."


def render_agentic_replay_prompt(repo_root: Path, release_tag: str, plan: JSONDict) -> str:
    manifest = load_patch_manifest(repo_root / "patches" / "private-patch-manifest.json")
    template_path = repo_root / PROMPT_TEMPLATE
    template = template_path.read_text(encoding="utf-8")
    return template.format(
        display_version=plan["display_version"],
        patch_groups=format_patch_groups_for_prompt(manifest),
        patch_manifest_path=repo_root / "patches" / "private-patch-manifest.json",
        private_git_tag=plan["private_git_tag"],
        private_patch_generation=plan["private_patch_generation"],
        release_manifest_path=repo_root / "release" / "release-manifest.json",
        release_tag=release_tag,
        replay_branch=plan["replay_branch"],
        repo_root=repo_root,
        validation_commands=format_validation_commands_for_prompt(plan),
    )


def codex_exec_runtime_config_args(env: dict[str, str] | None = None) -> list[str]:
    del env
    # Keep the provider explicit so replay runs stay on the official OpenAI path
    # even after Codex writes project trust state into the runtime config copy.
    return [
        "--config",
        'model_provider="openai"',
    ]


def codex_exec_command(
    repo_root: Path,
    release_tag: str,
    runtime_config_args: list[str] | None = None,
) -> list[str]:
    if runtime_config_args is None:
        runtime_config_args = codex_exec_runtime_config_args()
    return [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        *runtime_config_args,
        "--output-last-message",
        str(codex_last_message_path(repo_root, release_tag)),
        "-C",
        str(repo_root),
        "-",
    ]


def launch_agentic_replay(repo_root: Path, release_tag: str, plan: JSONDict) -> None:
    ensure_repo_runtime_dirs(repo_root)
    prompt = render_agentic_replay_prompt(repo_root, release_tag, plan)
    env = codex_exec_environment(repo_root)
    subprocess.run(
        codex_exec_command(
            repo_root,
            release_tag,
            codex_exec_runtime_config_args(env),
        ),
        check=True,
        cwd=repo_root,
        env=env,
        input=prompt,
        text=True,
    )


def ensure_replay_branch_checked_out(repo_root: Path, branch_name: str) -> None:
    completed = run_command(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        capture_output=True,
    )
    current_branch = completed.stdout.strip()
    if current_branch != branch_name:
        raise RuntimeError(
            f"Agentic replay finished on {current_branch!r}, expected {branch_name!r}"
        )


def inject_private_version(repo_root: Path, plan: JSONDict) -> None:
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


def repo_paths_differ_from_head(repo_root: Path, paths: Sequence[str]) -> bool:
    completed = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", *paths],
        check=False,
        cwd=repo_root,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            f"git diff returned unexpected exit code {completed.returncode}"
        )
    return completed.returncode == 1


def sync_patch_repo_metadata(
    repo_root: Path,
    source_ref: str = PATCH_REPO_METADATA_SOURCE_REF,
    metadata_touchpoints: Sequence[str] = PATCH_REPO_METADATA_TOUCHPOINTS,
) -> bool:
    run_command(
        ["git", "checkout", source_ref, "--", *metadata_touchpoints],
        cwd=repo_root,
    )
    if not repo_paths_differ_from_head(repo_root, metadata_touchpoints):
        return False
    run_command(
        ["git", "commit", "-m", PATCH_REPO_METADATA_COMMIT_MESSAGE],
        cwd=repo_root,
    )
    return True


def replay_plan(repo_root: Path, release_tag: str) -> JSONDict:
    manifest = load_patch_manifest(repo_root / "patches" / "private-patch-manifest.json")
    release_manifest = load_release_manifest(repo_root / "release" / "release-manifest.json")
    generation = next_private_generation(release_manifest, release_tag)
    display_version = private_display_version(release_tag, generation)
    private_tag = private_release_tag(release_tag, generation)
    result_path = replay_result_path(repo_root, release_tag)
    ordered_groups = ordered_patch_groups(manifest)
    runtime_paths = repo_runtime_paths(repo_root)
    return {
        "agentic_replay": {
            "codex_config": ".codex/config.toml",
            "command": codex_exec_command(repo_root, release_tag),
            "global_config_isolated": True,
            "global_skills_isolated": True,
            "last_message_file": str(codex_last_message_path(repo_root, release_tag).relative_to(repo_root)),
            "prompt_template": PROMPT_TEMPLATE,
            "provider": "openai",
            "repo_codex_source": str(Path(runtime_paths["repo_codex_source"]).relative_to(repo_root)),
            "runtime_auth_source": "~/.codex/auth.json",
            "runtime_auth_source_optional": True,
            "runtime_codex_home": str(Path(runtime_paths["codex_home"]).relative_to(repo_root)),
            "runtime_env_file": str(Path(runtime_paths["env_file"]).relative_to(repo_root)),
            "runtime_home": str(Path(runtime_paths["home"]).relative_to(repo_root)),
            "runtime_sqlite_home": str(Path(runtime_paths["sqlite_home"]).relative_to(repo_root)),
        },
        "display_version": display_version,
        "origin_remote_configured": origin_remote_exists(repo_root),
        "patch_groups": [group["name"] for group in ordered_groups],
        "metadata_source_ref": PATCH_REPO_METADATA_SOURCE_REF,
        "metadata_touchpoints": list(PATCH_REPO_METADATA_TOUCHPOINTS),
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
    plan = replay_plan(repo_root, release_tag)
    if dry_run:
        return plan
    if refuse_when_replay_active(repo_root):
        raise RuntimeError("Refusing replay because another replay lock already exists.")

    branch_name = plan["replay_branch"]
    lock_path = replay_lock_path(repo_root, release_tag)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(f"{utc_now_iso()}\n", encoding="utf-8")

    try:
        ensure_release_tag(repo_root, release_tag)
        ensure_private_tag_absent(repo_root, plan["private_git_tag"])
        launch_agentic_replay(repo_root, release_tag, plan)
        ensure_replay_branch_checked_out(repo_root, branch_name)
        inject_private_version(repo_root, plan)
        run_validation(list(plan["patch_groups"]), repo_root)
        sync_patch_repo_metadata(repo_root)
        applied_groups = list(plan["patch_groups"])
        validations_run: list[list[str]] = []
        for group_name in plan["patch_groups"]:
            validations_run.extend(plan["validation_commands"].get(group_name, []))

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
