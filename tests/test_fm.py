import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runner"))
from fm import read_fm, set_fm  # noqa: E402


class FrontmatterRoundTrip(unittest.TestCase):
    def write(self, text):
        path = os.path.join(self.dir.name, "p.md")
        with open(path, "w") as f:
            f.write(text)
        return path

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_value_with_colon_and_hash_round_trips(self):
        p = self.write("---\nstatus: proposed\n---\n\nbody\n")
        set_fm(p, "note", "ratio 3:1 — see #4")
        meta, _ = read_fm(p)
        self.assertEqual(meta["note"], "ratio 3:1 — see #4")
        self.assertEqual(meta["status"], "proposed")

    def test_body_and_other_keys_survive_a_write(self):
        p = self.write("---\nworkflow: desk-note\nstatus: proposed\n---\n\n# Title\n\ntext\n")
        set_fm(p, "status", "confirmed")
        meta, txt = read_fm(p)
        self.assertEqual(meta, {"workflow": "desk-note", "status": "confirmed"})
        self.assertIn("# Title", txt)

    def test_inline_comment_is_not_part_of_the_value(self):
        p = self.write("---\nstatus: proposed        # proposed | confirmed\n---\n")
        meta, _ = read_fm(p)
        self.assertEqual(meta["status"], "proposed")

    def test_missing_key_is_appended(self):
        p = self.write("---\nstatus: proposed\n---\n")
        set_fm(p, "eval_hash", "abc123")
        meta, _ = read_fm(p)
        self.assertEqual(meta["eval_hash"], "abc123")


if __name__ == "__main__":
    unittest.main()
