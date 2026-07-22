"""Phase 0 exit criteria: retry cap, change-request guard, missing-eval block, lock."""
import json
import os
import time
import unittest

from conductor_fixture import ConductorTestCase, FakeRun

import conductor

# Every build now requires a confirmed suite (Phase 1.0); these tests are about
# what happens after that gate is satisfied.
EVAL_YAML = "output: output.md\nlayer1:\n  required_fields: [cash]\n"


class RetryBudget(ConductorTestCase):
    def test_a_failing_build_stops_at_the_cap(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "eval/eval.yaml": EVAL_YAML})
        self.patch_run(FakeRun(returncode=1))  # build never produces SKILL.md
        path = self.proposal()

        for _ in range(conductor.BUILD_ATTEMPT_CAP + 3):
            conductor.stage_proposals()

        self.assertEqual(self.status_of(path), "build-failed")
        self.assertEqual(conductor.attempts_used("demo-skill"), conductor.BUILD_ATTEMPT_CAP)
        self.assertIn("demo-skill", self.log_text())

    def test_the_counter_spans_builds_and_refines_and_resets_on_confirm(self):
        # Phase 1 shares this budget with the refine loop, so a successful build
        # is not the reset point — a gate pass or a new confirmed version is.
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "eval/eval.yaml": EVAL_YAML})
        conductor.record_attempt("demo-skill")
        conductor.record_attempt("demo-skill")
        self.assertEqual(conductor.attempts_used("demo-skill"), 2)

        path = self.proposal()
        conductor.confirm_proposal(path, {"skills": ["demo-skill"]})

        self.assertEqual(conductor.attempts_used("demo-skill"), 0)


class ChangeRequestGuard(ConductorTestCase):
    def test_a_change_request_is_never_rebuilt(self):
        self.skill_dir("demo-skill", {
            "BUILD_BRIEF.md": "build it",
            "eval/eval.yaml": EVAL_YAML,
            "CHANGE_REQUEST.md": "the contract's output shape is impossible",
        })
        run = self.patch_run(FakeRun(returncode=0))
        path = self.proposal()

        conductor.stage_proposals()
        conductor.stage_proposals()

        self.assertEqual(self.status_of(path), "changes-requested")
        self.assertEqual(run.calls, [], "no build subprocess should have been launched")

    def test_a_builder_raising_mid_build_is_caught(self):
        sdir = self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "eval/eval.yaml": EVAL_YAML})

        def build(cmd, kwargs):
            with open(os.path.join(sdir, "CHANGE_REQUEST.md"), "w") as f:
                f.write("cannot satisfy the brief")
            return 0

        self.patch_run(FakeRun(on_call=build))
        self.assertEqual(conductor.build_skill("demo-skill"), "change-request")


class MissingEvalConfig(ConductorTestCase):
    def test_a_skill_without_eval_yaml_blocks_instead_of_stalling(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "SKILL.md": "# skill"})
        self.patch_run(FakeRun(returncode=0))
        path = self.proposal()

        conductor.stage_proposals()

        self.assertEqual(self.status_of(path), "blocked")
        self.assertIn("BLOCKED", self.log_text())


class ConductorLock(ConductorTestCase):
    def test_a_second_conductor_no_ops(self):
        with open(conductor.LOCK, "w") as f:
            json.dump({"pid": os.getpid() + 90000, "timestamp": time.time()}, f)
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "build it", "eval/eval.yaml": EVAL_YAML})
        run = self.patch_run(FakeRun(returncode=0))
        path = self.proposal()

        conductor.tick()

        self.assertEqual(self.status_of(path), "confirmed", "the lock holder owns this work")
        self.assertEqual(run.calls, [])
        self.assertIn("holds the lock", self.log_text())

    def test_a_stale_lock_is_taken_over(self):
        with open(conductor.LOCK, "w") as f:
            json.dump({"pid": os.getpid() + 90000,
                       "timestamp": time.time() - conductor.LOCK_STALE_SECONDS - 1}, f)
        self.assertIsNone(conductor.lock_holder())

    def test_our_own_lock_does_not_block_us(self):
        conductor.take_lock()
        self.assertIsNone(conductor.lock_holder())


if __name__ == "__main__":
    unittest.main()
