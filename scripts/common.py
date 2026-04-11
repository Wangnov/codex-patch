from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Sequence

JSONDict = dict[str, Any]

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "state" / "latest-release.json"
PATCH_MANIFEST_PATH = REPO_ROOT / "patches" / "private-patch-manifest.json"
RELEASE_MANIFEST_PATH = REPO_ROOT / "release" / "release-manifest.json"
REPLAY_RESULTS_DIR = REPO_ROOT / "state" / "replays"
CODEX_CONFIG_DIR = REPO_ROOT / ".codex"
CODEX_RUNTIME_DIR = REPO_ROOT / ".codex-runtime"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def load_json(path: Path) -> JSONDict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: JSONDict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_state(path: Path = STATE_PATH) -> JSONDict:
    return load_json(path)


def save_state(path: Path, state: JSONDict) -> None:
    save_json(path, state)


def load_patch_manifest(path: Path = PATCH_MANIFEST_PATH) -> JSONDict:
    return load_json(path)


def load_release_manifest(path: Path = RELEASE_MANIFEST_PATH) -> JSONDict:
    return load_json(path)


def save_release_manifest(path: Path, manifest: JSONDict) -> None:
    save_json(path, manifest)


def replay_result_payload(upstream_tag: str, outcome: str, **extra: Any) -> JSONDict:
    payload: JSONDict = {
        "outcome": outcome,
        "recorded_at": utc_now_iso(),
        "upstream_release_tag": upstream_tag,
    }
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return payload


def repo_runtime_paths(repo_root: Path = REPO_ROOT) -> JSONDict:
    runtime_root = repo_root / ".codex-runtime"
    return {
        "runtime_root": runtime_root,
        "home": runtime_root / "home",
        "codex_home": repo_root / ".codex",
        "env_file": runtime_root / "codex-exec.env",
        "sqlite_home": runtime_root / "sqlite-home",
        "last_message_dir": runtime_root / "last-message",
    }


def ensure_repo_runtime_dirs(repo_root: Path = REPO_ROOT) -> JSONDict:
    paths = repo_runtime_paths(repo_root)
    for key in ("runtime_root", "home", "codex_home", "sqlite_home", "last_message_dir"):
        Path(paths[key]).mkdir(parents=True, exist_ok=True)
    (Path(paths["home"]) / ".agents" / "skills").mkdir(parents=True, exist_ok=True)
    return paths


def load_runtime_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    runtime_env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise RuntimeError(f"Invalid runtime env line in {path}: {raw_line!r}")
        runtime_env[key.strip()] = value
    return runtime_env


def codex_exec_environment(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    paths = ensure_repo_runtime_dirs(repo_root)
    env = dict(os.environ)
    for key, value in load_runtime_env_file(Path(paths["env_file"])).items():
        env.setdefault(key, value)
    env["HOME"] = str(paths["home"])
    env["CODEX_HOME"] = str(paths["codex_home"])
    env["CODEX_SQLITE_HOME"] = str(paths["sqlite_home"])
    return env


def run_command(
    command: Sequence[str],
    cwd: Path = REPO_ROOT,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        cwd=cwd,
        text=True,
        capture_output=capture_output,
    )
