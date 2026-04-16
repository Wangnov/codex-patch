import unittest
import os
import subprocess
from unittest.mock import patch

from scripts.check_latest_release import github_token_from_env_or_gh
from scripts.check_latest_release import should_start_replay
from scripts.check_latest_release import updated_state_for_latest_release


class ReleaseDetectionTests(unittest.TestCase):
    def test_starts_when_latest_release_changes(self) -> None:
        self.assertTrue(should_start_replay("rust-v0.119.0", "rust-v0.118.0"))

    def test_does_not_start_when_release_is_unchanged(self) -> None:
        self.assertFalse(should_start_replay("rust-v0.119.0", "rust-v0.119.0"))

    def test_updates_seen_release_in_state(self) -> None:
        state = {"latest_release_seen": None, "updated_at": None}
        next_state = updated_state_for_latest_release(state, "rust-v0.119.0")

        self.assertEqual(next_state["latest_release_seen"], "rust-v0.119.0")
        self.assertIsNotNone(next_state["updated_at"])

    @patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}, clear=True)
    def test_prefers_environment_token(self) -> None:
        self.assertEqual(github_token_from_env_or_gh(), "env-token")

    @patch.dict(os.environ, {}, clear=True)
    @patch("scripts.check_latest_release.subprocess.run")
    def test_uses_gh_auth_token_when_env_missing(self, mock_run: object) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["gh", "auth", "token"],
            returncode=0,
            stdout="gh-token\n",
        )

        self.assertEqual(github_token_from_env_or_gh(), "gh-token")
