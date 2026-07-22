"""Phase 3 baseline: every attempt leaves a step-level trail triage can read."""
import os
import unittest

from conductor_fixture import ConductorTestCase, FakeRun

import conductor
import triage as triage_lib

EVAL_YAML = "output: output.md\nlayer1:\n  required_fields: [cash]\n"


class BuildLog(ConductorTestCase):
    def test_the_build_brief_asks_for_a_step_level_log(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "eval/eval.yaml": EVAL_YAML})
        run = self.patch_run(FakeRun(returncode=1))

        conductor.build_skill("demo-skill")

        prompt = run.calls[0][0][2]
        self.assertIn("BUILD_LOG.md", prompt)

    def test_the_refine_brief_asks_for_it_too(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "eval/eval.yaml": EVAL_YAML})
        run = self.patch_run(FakeRun(returncode=0))

        conductor.refine_skill("demo-skill", ["required: cash"])

        prompt = run.calls[0][0][2]
        self.assertIn("BUILD_LOG.md", prompt)
        self.assertIn("read-only context", prompt, "the suite is still off limits")

    def test_each_attempt_archives_its_log_and_scorecard(self):
        sdir = self.skill_dir("demo-skill", {
            "eval/eval.yaml": EVAL_YAML,
            "eval/scorecard.json": '{"gate": {"overall": false}}',
            "BUILD_LOG.md": "12:00 wrote output.md\n",
        })

        conductor.archive_attempt("demo-skill", 2)

        self.assertTrue(os.path.exists(os.path.join(sdir, "BUILD_LOG.attempt-2.md")))
        self.assertTrue(os.path.exists(os.path.join(sdir, "eval", "scorecard.attempt-2.json")))

    def test_archiving_a_missing_log_is_not_an_error(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
        conductor.archive_attempt("demo-skill", 1)  # no log, no scorecard yet

    def test_triage_evidence_includes_the_build_log(self):
        self.skill_dir("demo-skill", {"BUILD_LOG.md": "12:00 wrote output.md\n"})
        evidence = triage_lib.evidence_for(self.root, "demo-skill")
        self.assertIn(os.path.join("skills", "demo-skill", "BUILD_LOG.md"), evidence)


if __name__ == "__main__":
    unittest.main()
