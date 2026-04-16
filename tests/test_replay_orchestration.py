import unittest
import tempfile
import json
import os
import subprocess
from pathlib import Path

from scripts.common import codex_exec_environment
from scripts.common import load_runtime_env_file
from scripts.replay_latest_release import codex_exec_runtime_config_args
from scripts.replay_latest_release import next_private_generation
from scripts.replay_latest_release import refuse_when_replay_active
from scripts.replay_latest_release import render_agentic_replay_prompt
from scripts.replay_latest_release import replay_plan
from scripts.replay_latest_release import replay_branch_name
from scripts.replay_latest_release import sync_patch_repo_metadata


class ReplayBranchTests(unittest.TestCase):
    def test_runtime_env_file_parses_simple_key_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "codex-exec.env"
            env_file.write_text(
                (
                    "# comment\n"
                    "OPENAI_API_KEY=test-token\n"
                    "OPENAI_ORG=org-example\n"
                    "EMPTY_VALUE=\n"
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_runtime_env_file(env_file),
                {
                    "OPENAI_API_KEY": "test-token",
                    "OPENAI_ORG": "org-example",
                    "EMPTY_VALUE": "",
                },
            )

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
            self.assertEqual(plan["metadata_source_ref"], "patch/main")
            self.assertIn(
                ".github/workflows/release-matrix.yml",
                plan["metadata_touchpoints"],
            )
            self.assertEqual(plan["display_version"], "0.119.0-p2")
            self.assertEqual(plan["private_git_tag"], "codex-patch-rust-v0.119.0-p2")
            self.assertTrue(plan["agentic_replay"]["global_config_isolated"])
            self.assertTrue(plan["agentic_replay"]["global_skills_isolated"])
            self.assertEqual(plan["agentic_replay"]["provider"], "openai")
            self.assertEqual(
                plan["agentic_replay"]["runtime_home"],
                ".codex-runtime/home",
            )
            self.assertEqual(
                plan["agentic_replay"]["repo_codex_source"],
                ".codex",
            )
            self.assertEqual(
                plan["agentic_replay"]["runtime_auth_source"],
                "~/.codex/auth.json",
            )
            self.assertEqual(
                plan["agentic_replay"]["runtime_codex_home"],
                ".codex-runtime/codex-home",
            )
            self.assertEqual(
                plan["agentic_replay"]["runtime_env_file"],
                ".codex-runtime/codex-exec.env",
            )
            self.assertTrue(plan["agentic_replay"]["runtime_auth_source_optional"])
            self.assertEqual(plan["agentic_replay"]["command"][3:5], ["--config", 'model_provider="openai"'])
            self.assertEqual(plan["agentic_replay"]["runtime_sqlite_home"], ".codex-runtime/sqlite-home")

    def test_refuses_when_any_replay_lock_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "state" / "replays").mkdir(parents=True)
            (repo_root / "state" / "replays" / "rust-v0.119.0.lock").write_text(
                "2026-04-07T00:00:00Z\n",
                encoding="utf-8",
            )

            self.assertTrue(refuse_when_replay_active(repo_root))

    def test_codex_exec_environment_uses_runtime_home_and_runtime_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".codex").mkdir(parents=True)
            (repo_root / ".codex" / "config.toml").write_text(
                'model_provider = "openai"\n',
                encoding="utf-8",
            )
            env = codex_exec_environment(repo_root)

            self.assertEqual(env["HOME"], str(repo_root / ".codex-runtime" / "home"))
            self.assertEqual(
                env["CODEX_HOME"],
                str(repo_root / ".codex-runtime" / "codex-home"),
            )
            self.assertEqual(
                env["CODEX_SQLITE_HOME"],
                str(repo_root / ".codex-runtime" / "sqlite-home"),
            )

    def test_codex_exec_environment_loads_repo_runtime_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".codex").mkdir(parents=True)
            (repo_root / ".codex" / "config.toml").write_text(
                'model_provider = "openai"\n',
                encoding="utf-8",
            )
            runtime_env_file = repo_root / ".codex-runtime" / "codex-exec.env"
            runtime_env_file.parent.mkdir(parents=True)
            runtime_env_file.write_text(
                (
                    "OPENAI_API_KEY=runtime-token\n"
                    "OPENAI_ORG=org-example\n"
                ),
                encoding="utf-8",
            )

            original_token = os.environ.pop("OPENAI_API_KEY", None)
            original_org = os.environ.pop("OPENAI_ORG", None)
            try:
                env = codex_exec_environment(repo_root)
            finally:
                if original_token is not None:
                    os.environ["OPENAI_API_KEY"] = original_token
                if original_org is not None:
                    os.environ["OPENAI_ORG"] = original_org

            self.assertEqual(env["OPENAI_API_KEY"], "runtime-token")
            self.assertEqual(env["OPENAI_ORG"], "org-example")

    def test_codex_exec_environment_copies_repo_codex_inputs_into_runtime_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".codex" / "prompts").mkdir(parents=True)
            (repo_root / ".codex" / "skills" / "custom-skill").mkdir(parents=True)
            (repo_root / ".codex" / "config.toml").write_text(
                'model_provider = "openai"\n',
                encoding="utf-8",
            )
            (repo_root / ".codex" / "prompts" / "replay-latest-release.md").write_text(
                "prompt body\n",
                encoding="utf-8",
            )
            (repo_root / ".codex" / "skills" / "custom-skill" / "SKILL.md").write_text(
                "skill body\n",
                encoding="utf-8",
            )

            codex_exec_environment(repo_root)

            runtime_codex_home = repo_root / ".codex-runtime" / "codex-home"
            self.assertEqual(
                (runtime_codex_home / "config.toml").read_text(encoding="utf-8"),
                'model_provider = "openai"\n',
            )
            self.assertEqual(
                (
                    runtime_codex_home
                    / "prompts"
                    / "replay-latest-release.md"
                ).read_text(encoding="utf-8"),
                "prompt body\n",
            )
            self.assertEqual(
                (
                    runtime_codex_home
                    / "skills"
                    / "custom-skill"
                    / "SKILL.md"
                ).read_text(encoding="utf-8"),
                "skill body\n",
            )

    def test_codex_exec_environment_bridges_host_auth_json_into_runtime_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            host_home = Path(tmpdir) / "home"
            repo_root.mkdir(parents=True)
            (repo_root / ".codex").mkdir(parents=True)
            (repo_root / ".codex" / "config.toml").write_text(
                'model_provider = "openai"\n',
                encoding="utf-8",
            )
            (host_home / ".codex").mkdir(parents=True)
            (host_home / ".codex" / "auth.json").write_text(
                '{"provider":"openai"}\n',
                encoding="utf-8",
            )

            original_home = os.environ.get("HOME")
            try:
                os.environ["HOME"] = str(host_home)
                codex_exec_environment(repo_root)
            finally:
                if original_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = original_home

            self.assertEqual(
                (
                    repo_root
                    / ".codex-runtime"
                    / "codex-home"
                    / "auth.json"
                ).read_text(encoding="utf-8"),
                '{"provider":"openai"}\n',
            )

    def test_codex_exec_runtime_config_args_force_openai_provider(self) -> None:
        args = codex_exec_runtime_config_args()

        self.assertEqual(
            args,
            [
                "--config",
                'model_provider="openai"',
            ],
        )

    def test_agentic_prompt_mentions_isolated_replay_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".codex" / "prompts").mkdir(parents=True)
            (repo_root / "patches").mkdir(parents=True)
            (repo_root / "release").mkdir(parents=True)
            (repo_root / "state" / "replays").mkdir(parents=True)
            (repo_root / ".codex" / "prompts" / "replay-latest-release.md").write_text(
                "release={release_tag}\nbranch={replay_branch}\nversion={display_version}\nlauncher=launcher handles version + validation\nvalidations={validation_commands}\npatches={patch_groups}\n",
                encoding="utf-8",
            )
            (repo_root / "patches" / "private-patch-manifest.json").write_text(
                json.dumps(
                    {
                        "groups": [
                            {"name": "what-why-shnote", "source_repo": str(repo_root), "source_commits": ["a"]},
                            {"name": "cross-provider-defaults", "source_repo": str(repo_root), "source_commits": ["b"]},
                            {"name": "private-version-injection", "source_repo": str(repo_root), "source_commits": []},
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (repo_root / "release" / "release-manifest.json").write_text(
                json.dumps(
                    {
                        "display_version": "0.118.0-p2",
                        "private_git_tag": "codex-patch-rust-v0.118.0-p2",
                        "private_patch_generation": 1,
                        "upstream_tag": "rust-v0.118.0",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            plan = replay_plan(repo_root, "rust-v0.118.0")
            prompt = render_agentic_replay_prompt(repo_root, "rust-v0.118.0", plan)

            self.assertIn("release=rust-v0.118.0", prompt)
            self.assertIn("branch=replay/rust-v0.118.0", prompt)
            self.assertIn("version=0.118.0-p2", prompt)
            self.assertIn("cargo test -p codex-core", prompt)
            self.assertIn("launcher", prompt.lower())

    def test_sync_patch_repo_metadata_commits_files_from_patch_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            subprocess.run(["git", "init"], check=True, cwd=repo_root)
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                check=True,
                cwd=repo_root,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                check=True,
                cwd=repo_root,
            )
            subprocess.run(
                ["git", "checkout", "-b", "patch/main"],
                check=True,
                cwd=repo_root,
            )

            for relative_path, content in {
                "README.md": "metadata from patch main\n",
                ".github/workflows/release-matrix.yml": "name: release-matrix\n",
                "scripts/replay_latest_release.py": "print('launcher')\n",
            }.items():
                path = repo_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            subprocess.run(["git", "add", "."], check=True, cwd=repo_root)
            subprocess.run(
                ["git", "commit", "-m", "seed patch metadata"],
                check=True,
                cwd=repo_root,
            )

            subprocess.run(
                ["git", "checkout", "-b", "replay/rust-v0.119.0"],
                check=True,
                cwd=repo_root,
            )
            (repo_root / "README.md").write_text("replay branch content\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], check=True, cwd=repo_root)
            subprocess.run(
                ["git", "commit", "-m", "seed replay branch"],
                check=True,
                cwd=repo_root,
            )

            synced = sync_patch_repo_metadata(
                repo_root,
                metadata_touchpoints=(
                    "README.md",
                    ".github/workflows/release-matrix.yml",
                    "scripts/replay_latest_release.py",
                ),
            )

            self.assertTrue(synced)
            self.assertEqual(
                (repo_root / "README.md").read_text(encoding="utf-8"),
                "metadata from patch main\n",
            )
            self.assertEqual(
                (repo_root / ".github/workflows/release-matrix.yml").read_text(
                    encoding="utf-8"
                ),
                "name: release-matrix\n",
            )
            self.assertEqual(
                (repo_root / "scripts/replay_latest_release.py").read_text(
                    encoding="utf-8"
                ),
                "print('launcher')\n",
            )

            latest_subject = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                check=True,
                cwd=repo_root,
                text=True,
                capture_output=True,
            ).stdout.strip()
            self.assertEqual(latest_subject, "chore(replay): sync patch repo metadata")
