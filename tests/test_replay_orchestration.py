import unittest
import tempfile
import json
from pathlib import Path

from scripts.replay_latest_release import next_private_generation
from scripts.replay_latest_release import replay_plan
from scripts.replay_latest_release import replay_branch_name


class ReplayBranchTests(unittest.TestCase):
    def test_formats_replay_branch_name(self) -> None:
        self.assertEqual(replay_branch_name("rust-v0.119.0"), "replay/rust-v0.119.0")

    def test_private_generation_increments_for_same_release(self) -> None:
        release_manifest = {
            "display_version": "0.119.0-p1",
            "private_git_tag": "codex-patch-rust-v0.119.0-p1",
            "private_patch_generation": 1,
            "upstream_tag": "rust-v0.119.0",
        }

        self.assertEqual(next_private_generation(release_manifest, "rust-v0.119.0"), 2)

    def test_replay_plan_uses_manifest_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "patches").mkdir(parents=True)
            (repo_root / "release").mkdir(parents=True)
            (repo_root / "state" / "replays").mkdir(parents=True)
            (repo_root / "patches" / "private-patch-manifest.json").write_text(
                json.dumps(
                    {
                        "groups": [
                            {"name": "private-version-injection", "source_repo": str(repo_root), "source_commits": []},
                            {"name": "cross-provider-defaults", "source_repo": str(repo_root), "source_commits": ["b"]},
                            {"name": "what-why-shnote", "source_repo": str(repo_root), "source_commits": ["a"]},
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (repo_root / "release" / "release-manifest.json").write_text(
                json.dumps(
                    {
                        "display_version": "0.119.0-p1",
                        "private_git_tag": "codex-patch-rust-v0.119.0-p1",
                        "private_patch_generation": 1,
                        "upstream_tag": "rust-v0.119.0",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            plan = replay_plan(repo_root, "rust-v0.119.0")

            self.assertEqual(
                plan["patch_groups"],
                ["what-why-shnote", "cross-provider-defaults", "private-version-injection"],
            )
            self.assertEqual(plan["display_version"], "0.119.0-p2")
            self.assertEqual(plan["private_git_tag"], "codex-patch-rust-v0.119.0-p2")
