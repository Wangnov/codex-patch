from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import RELEASE_MANIFEST_PATH
from scripts.common import REPO_ROOT
from scripts.common import load_release_manifest
from scripts.common import save_release_manifest


def upstream_version_from_tag(upstream_tag: str) -> str:
    if upstream_tag.startswith("rust-v"):
        return upstream_tag.removeprefix("rust-v")
    if upstream_tag.startswith("v"):
        return upstream_tag.removeprefix("v")
    return upstream_tag


def private_display_version(upstream_tag: str, generation: int) -> str:
    return f"{upstream_version_from_tag(upstream_tag)}-p{generation}"


def private_release_tag(upstream_tag: str, generation: int) -> str:
    return f"codex-patch-{upstream_tag}-p{generation}"


def update_workspace_version(cargo_toml_path: Path, version: str) -> None:
    text = cargo_toml_path.read_text()
    lines = text.splitlines()
    in_workspace_package = False
    replaced = False
    updated_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_workspace_package = stripped == "[workspace.package]"
        if in_workspace_package and stripped.startswith("version = "):
            line = re.sub(r'"[^"]+"', f'"{version}"', line, count=1)
            replaced = True
        updated_lines.append(line)

    if not replaced:
        raise RuntimeError(f"Could not update workspace version in {cargo_toml_path}")

    cargo_toml_path.write_text("\n".join(updated_lines) + "\n")


def update_default_nix_version(default_nix_path: Path, version: str) -> None:
    text = default_nix_path.read_text()
    updated_text, count = re.subn(
        r'(version \? ")[^"]+(")',
        rf"\g<1>{version}\2",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Could not update version default in {default_nix_path}")
    default_nix_path.write_text(updated_text)


def update_package_json_version(package_json_path: Path, version: str) -> None:
    payload = json.loads(package_json_path.read_text(encoding="utf-8"))
    payload["version"] = version
    package_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def update_private_version_files(
    repo_root: Path,
    upstream_tag: str,
    generation: int,
) -> dict[str, str]:
    display_version = private_display_version(upstream_tag, generation)
    private_tag = private_release_tag(upstream_tag, generation)

    update_workspace_version(repo_root / "codex-rs" / "Cargo.toml", display_version)
    update_default_nix_version(repo_root / "codex-rs" / "default.nix", display_version)
    update_package_json_version(repo_root / "codex-cli" / "package.json", display_version)
    update_package_json_version(
        repo_root / "sdk" / "typescript" / "package.json",
        display_version,
    )
    update_package_json_version(
        repo_root / "codex-rs" / "responses-api-proxy" / "npm" / "package.json",
        display_version,
    )

    release_manifest = load_release_manifest(repo_root / "release" / "release-manifest.json")
    release_manifest["display_version"] = display_version
    release_manifest["private_git_tag"] = private_tag
    release_manifest["private_patch_generation"] = generation
    release_manifest["upstream_tag"] = upstream_tag
    save_release_manifest(repo_root / "release" / "release-manifest.json", release_manifest)

    return {
        "display_version": display_version,
        "private_patch_generation": generation,
        "private_git_tag": private_tag,
        "upstream_tag": upstream_tag,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inject codex-patch private release versions.")
    parser.add_argument("--upstream-tag", required=True, help="Upstream release tag, e.g. rust-v0.119.0")
    parser.add_argument("--generation", required=True, type=int, help="Private patch generation number.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root that should be updated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = update_private_version_files(args.repo_root, args.upstream_tag, args.generation)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
