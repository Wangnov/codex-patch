from __future__ import annotations

import json
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
