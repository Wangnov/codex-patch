import json
import tempfile
import unittest
from pathlib import Path

from scripts.common import replay_result_payload
from scripts.replay_latest_release import refuse_when_replay_active
from scripts.write_replay_result import replay_result_path
from scripts.write_replay_result import write_replay_result


class ReplayLoggingTests(unittest.TestCase):
    def test_success_payload_includes_outcome(self) -> None:
        payload = replay_result_payload("rust-v0.119.0", "success")
        self.assertEqual(payload["outcome"], "success")

    def test_writes_result_file_under_state_replays(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            payload = replay_result_payload("rust-v0.119.0", "success")
            path = write_replay_result(repo_root, "rust-v0.119.0", payload)

            self.assertEqual(path, replay_result_path(repo_root, "rust-v0.119.0"))
            self.assertEqual(json.loads(path.read_text())["outcome"], "success")


class ReplaySafetyTests(unittest.TestCase):
    def test_refuses_second_replay_when_one_is_active(self) -> None:
        self.assertTrue(refuse_when_replay_active({"active_replay_status": "running"}))
