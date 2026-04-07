import tempfile
import unittest
from pathlib import Path

from scripts.common import load_state
from scripts.common import save_state


class ReleaseStateTests(unittest.TestCase):
    def test_round_trips_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tmp-state.json"
            state = {"active_replay_status": "idle"}
            save_state(path, state)
            self.assertEqual(load_state(path)["active_replay_status"], "idle")
