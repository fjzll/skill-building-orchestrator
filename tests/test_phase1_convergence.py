"""Phase 1 exit criteria: converge within budget, and fail any attempt that edits the suite."""
import json
import os
import subprocess
import unittest

from conductor_fixture import ConductorTestCase, FakeRun

import conductor
from eval_suite import suite_hash

EVAL_YAML = """fixtures: [fixtures/source.txt]
output: output.md
layer1:
  required_fields: ["cash", "catalysts"]
layer2:
  number_sources: [fixtures/source.txt]
"""
SOURCE = "cash of 12.4m, three catalysts ahead\n"


class ConvergenceLoop(ConductorTestCase):
    """The real eval harness runs; only the LLM subprocess is faked."""

    def setUp(self):
        super().setUp()
        # The harness resolves paths from its own location, so it needs the real
        # repo layout — copy the checked-in harness into the throwaway root.
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        harness_dir = os.path.join(self.root, "evals", "harness")
        os.makedirs(harness_dir)
        with open(os.path.join(real_root, "evals", "harness", "run_evals.py")) as src:
            body = src.read()
        with open(os.path.join(harness_dir, "run_evals.py"), "w") as dst:
            dst.write(body)

    def seeded_skill(self, output):
        return self.skill_dir("demo-skill", {
            "BUILD_BRIEF.md": "write output.md covering cash and catalysts",
            "SKILL.md": "# skill",
            "eval/eval.yaml": EVAL_YAML,
            "fixtures/source.txt": SOURCE,
            "output.md": output,
        })

    def test_a_layer1_miss_converges_within_budget_with_no_human_touch(self):
        sdir = self.seeded_skill("cash of 12.4m\n")  # "catalysts" missing -> layer 1 fails
        frozen = suite_hash(self.root, ["demo-skill"])

        def refine(cmd, kwargs):
            with open(os.path.join(sdir, "output.md"), "w") as f:
                f.write("cash of 12.4m, three catalysts ahead\n")
            return 0

        # The harness must really run, so only the claude subprocess is faked.
        self.patch_run(RealHarnessFake(refine))

        outcome = conductor.converge_skill("demo-skill", ["demo-skill"], frozen)

        self.assertEqual(outcome, "pass")
        self.assertEqual(conductor.attempts_used("demo-skill"), 0, "budget cleared on a pass")
        self.assertTrue(os.path.exists(os.path.join(sdir, "eval", "scorecard.attempt-1.json")))
        self.assertIn("refine demo-skill", self.log_text())

    def test_a_refine_that_edits_the_suite_is_caught_by_the_hash_guard(self):
        sdir = self.seeded_skill("cash of 12.4m\n")
        frozen = suite_hash(self.root, ["demo-skill"])

        def cheat(cmd, kwargs):
            # Weaken the test instead of fixing the output.
            with open(os.path.join(sdir, "eval", "eval.yaml"), "w") as f:
                f.write('output: output.md\nlayer1:\n  required_fields: ["cash"]\n')
            return 0

        self.patch_run(RealHarnessFake(cheat))

        outcome = conductor.converge_skill("demo-skill", ["demo-skill"], frozen)

        self.assertEqual(outcome, "tampered")
        self.assertIn("TAMPERED", self.log_text())

    def test_an_unfixable_failure_stops_at_the_budget(self):
        self.seeded_skill("cash of 12.4m\n")
        frozen = suite_hash(self.root, ["demo-skill"])
        self.patch_run(RealHarnessFake(lambda c, k: 0))  # refine changes nothing

        outcome = conductor.converge_skill("demo-skill", ["demo-skill"], frozen)

        self.assertEqual(outcome, "exhausted")
        self.assertEqual(conductor.attempts_used("demo-skill"), conductor.BUILD_ATTEMPT_CAP)

    def test_a_missing_output_escalates_instead_of_refining(self):
        sdir = self.seeded_skill("placeholder\n")
        os.unlink(os.path.join(sdir, "output.md"))
        run = RealHarnessFake(lambda c, k: 0)
        self.patch_run(run)

        outcome = conductor.converge_skill("demo-skill", ["demo-skill"], None)

        self.assertEqual(outcome, "blocked")
        self.assertEqual([c for c, _ in run.claude_calls], [], "no refine attempt is spent")


class FailureShape(ConductorTestCase):
    def write_scorecard(self, card):
        sdir = self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
        with open(os.path.join(sdir, "eval", "scorecard.json"), "w") as f:
            json.dump(card, f)

    def test_a_failed_layer1_check_is_implementation_shaped(self):
        self.write_scorecard({"layer1": {"checks": [{"check": "required: cash", "pass": False}]}})
        self.assertEqual(conductor.failure_shape("demo-skill"), "implementation")

    def test_ungrounded_numbers_are_implementation_shaped(self):
        self.write_scorecard({"layer1": {"checks": []}, "layer2": {"ungrounded": ["42"]}})
        self.assertEqual(conductor.failure_shape("demo-skill"), "implementation")

    def test_a_judge_score_below_threshold_is_implementation_shaped(self):
        self.write_scorecard({"layer1": {"checks": []}, "layer3": {"overall_avg": 3.1},
                              "gate": {"layer3": False}})
        self.assertEqual(conductor.failure_shape("demo-skill"), "implementation")

    def test_an_unrecognised_failure_escalates(self):
        self.write_scorecard({"layer1": {"checks": []}, "layer2": {"ungrounded": []}})
        self.assertEqual(conductor.failure_shape("demo-skill"), "environment")


class RealHarnessFake:
    """Runs the eval harness for real; fakes only the `claude` subprocess.

    Constructed before patch_run swaps subprocess.run out, so it keeps a
    reference to the genuine one to delegate the harness call to.
    """

    def __init__(self, on_claude):
        self.on_claude = on_claude
        self.claude_calls = []
        self.real_run = subprocess.run

    def __call__(self, cmd, **kwargs):
        if cmd[0] == "claude":
            self.claude_calls.append((cmd, kwargs))
            return FakeRun.Result(self.on_claude(cmd, kwargs))
        return self.real_run(cmd, **kwargs)


if __name__ == "__main__":
    unittest.main()
