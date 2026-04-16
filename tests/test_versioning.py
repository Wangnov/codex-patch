import unittest
import json
import tempfile
from pathlib import Path

from scripts.update_private_version import private_display_version
from scripts.update_private_version import private_release_tag
from scripts.update_private_version import update_private_version_files


class VersioningTests(unittest.TestCase):
    def test_builds_private_patch_version(self) -> None:
        self.assertEqual(private_display_version("rust-v0.119.0", 1), "0.119.0-p1")

    def test_builds_private_release_tag(self) -> None:
        self.assertEqual(
            private_release_tag("rust-v0.119.0", 2),
            "codex-patch-rust-v0.119.0-p2",
        )

    def test_updates_version_touchpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "codex-rs").mkdir(parents=True)
            (repo_root / "codex-cli").mkdir(parents=True)
            (repo_root / "sdk" / "typescript").mkdir(parents=True)
            (repo_root / "codex-rs" / "responses-api-proxy" / "npm").mkdir(parents=True)
            (repo_root / "release").mkdir(parents=True)

            (repo_root / "codex-rs" / "Cargo.toml").write_text(
                '[workspace.package]\nversion = "0.0.0"\n',
                encoding="utf-8",
            )
            (repo_root / "codex-rs" / "default.nix").write_text(
                '{ version ? "0.0.0", ... }:\nversion ? "0.0.0"\n',
                encoding="utf-8",
            )
            (repo_root / "codex-cli" / "package.json").write_text(
                json.dumps({"version": "0.0.0-dev"}) + "\n",
                encoding="utf-8",
            )
            (repo_root / "sdk" / "typescript" / "package.json").write_text(
                json.dumps({"version": "0.0.0-dev"}) + "\n",
                encoding="utf-8",
            )
            (repo_root / "codex-rs" / "responses-api-proxy" / "npm" / "package.json").write_text(
                json.dumps({"version": "0.0.0-dev"}) + "\n",
                encoding="utf-8",
            )
            (repo_root / "release" / "release-manifest.json").write_text(
                json.dumps(
                    {
                        "upstream_tag": None,
                        "private_patch_generation": None,
                        "display_version": None,
                        "private_git_tag": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = update_private_version_files(repo_root, "rust-v0.119.0", 2)

            self.assertEqual(payload["display_version"], "0.119.0-p2")
            self.assertEqual(payload["private_git_tag"], "codex-patch-rust-v0.119.0-p2")
            self.assertIn('version = "0.119.0-p2"', (repo_root / "codex-rs" / "Cargo.toml").read_text(encoding="utf-8"))
            self.assertIn('version ? "0.119.0-p2"', (repo_root / "codex-rs" / "default.nix").read_text(encoding="utf-8"))
            self.assertEqual(
                json.loads((repo_root / "codex-cli" / "package.json").read_text(encoding="utf-8"))["version"],
                "0.119.0-p2",
            )
            self.assertEqual(
                json.loads((repo_root / "sdk" / "typescript" / "package.json").read_text(encoding="utf-8"))["version"],
                "0.119.0-p2",
            )

    def test_bootstraps_release_manifest_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "codex-rs").mkdir(parents=True)
            (repo_root / "codex-cli").mkdir(parents=True)
            (repo_root / "sdk" / "typescript").mkdir(parents=True)
            (repo_root / "codex-rs" / "responses-api-proxy" / "npm").mkdir(parents=True)

            (repo_root / "codex-rs" / "Cargo.toml").write_text(
                '[workspace.package]\nversion = "0.0.0"\n',
                encoding="utf-8",
            )
            (repo_root / "codex-rs" / "default.nix").write_text(
                '{ version ? "0.0.0", ... }:\nversion ? "0.0.0"\n',
                encoding="utf-8",
            )
            (repo_root / "codex-cli" / "package.json").write_text(
                json.dumps({"version": "0.0.0-dev"}) + "\n",
                encoding="utf-8",
            )
            (repo_root / "sdk" / "typescript" / "package.json").write_text(
                json.dumps({"version": "0.0.0-dev"}) + "\n",
                encoding="utf-8",
            )
            (repo_root / "codex-rs" / "responses-api-proxy" / "npm" / "package.json").write_text(
                json.dumps({"version": "0.0.0-dev"}) + "\n",
                encoding="utf-8",
            )

            payload = update_private_version_files(repo_root, "rust-v0.119.0", 1)

            self.assertEqual(payload["display_version"], "0.119.0-p1")
            self.assertEqual(
                json.loads((repo_root / "release" / "release-manifest.json").read_text(encoding="utf-8")),
                {
                    "display_version": "0.119.0-p1",
                    "private_git_tag": "codex-patch-rust-v0.119.0-p1",
                    "private_patch_generation": 1,
                    "upstream_tag": "rust-v0.119.0",
                },
            )
