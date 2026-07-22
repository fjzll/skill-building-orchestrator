"""Phase 1.0 exit criteria: no build without a confirmed suite; hash frozen on confirm."""
import os
import unittest

from conductor_fixture import ConductorTestCase, FakeRun

import conductor
from eval_suite import suite_hash
from fm import read_fm

EVAL_YAML = "output: output.md\nlayer1:\n  required_fields: [cash]\n"


class ConfirmFreezesTheSuite(ConductorTestCase):
    def test_a_proposal_cannot_reach_building_without_eval_yaml(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it"})
        run = self.patch_run(FakeRun(returncode=0))
        path = self.proposal()

        conductor.stage_proposals()

        self.assertEqual(self.status_of(path), "blocked")
        self.assertEqual(run.calls, [], "no build may start without a confirmed suite")
        self.assertIn("no confirmed eval/eval.yaml", self.log_text())

    def test_confirm_records_the_hash_of_the_suite_it_approved(self):
        self.skill_dir("demo-skill", {
            "BUILD_BRIEF.md": "build it",
            "eval/eval.yaml": EVAL_YAML,
            "fixtures/announcement.txt": "cash of 12.4m",
        })
        self.patch_run(FakeRun(returncode=0))
        path = self.proposal()

        conductor.confirm_proposal(path, read_fm(path)[0])

        meta = read_fm(path)[0]
        self.assertEqual(meta["status"], "building")
        self.assertEqual(meta["eval_hash"], suite_hash(self.root, ["demo-skill"]))

    def test_the_hash_covers_fixtures_not_just_the_config(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML, "fixtures/a.txt": "one"})
        before = suite_hash(self.root, ["demo-skill"])
        self.skill_dir("demo-skill", {"fixtures/a.txt": "one — tampered"})
        self.assertNotEqual(before, suite_hash(self.root, ["demo-skill"]))

    def test_the_hash_ignores_files_outside_the_suite(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
        before = suite_hash(self.root, ["demo-skill"])
        self.skill_dir("demo-skill", {"SKILL.md": "# the build's own output"})
        self.assertEqual(before, suite_hash(self.root, ["demo-skill"]))


class BuilderPrecondition(ConductorTestCase):
    def test_build_skill_refuses_without_a_suite(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it"})
        run = self.patch_run(FakeRun(returncode=0))
        self.assertEqual(conductor.build_skill("demo-skill"), "blocked")
        self.assertEqual(run.calls, [])

    def test_build_proceeds_once_the_suite_is_present(self):
        sdir = self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "eval/eval.yaml": EVAL_YAML})

        def build(cmd, kwargs):
            with open(os.path.join(sdir, "SKILL.md"), "w") as f:
                f.write("# skill")
            return 0

        self.patch_run(FakeRun(on_call=build))
        self.assertEqual(conductor.build_skill("demo-skill"), "built")


if __name__ == "__main__":
    unittest.main()
