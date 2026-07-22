"""Phase 2 exit criteria: a verdict per trigger type in shadow, then earned autonomy."""
import os
import unittest

from conductor_fixture import ConductorTestCase, FakeRun

import conductor
import triage as triage_lib
from archetype import archetype
from fm import read_fm

EVAL_YAML = "output: output.md\nlayer1:\n  required_fields: [cash]\n"

VERDICT = """---
class: {cls}
action: {action}
confidence: high
autonomy: proposed
trigger: {trigger}
---

## Diagnosis
The build subprocess timed out.
"""


class Archetype(unittest.TestCase):
    def test_shared_skills_key_on_the_shape_of_the_work(self):
        self.assertEqual(archetype("jpe-shared-ground-truth", "jpe"), "shared/ground-truth")

    def test_workflow_skills_keep_workflow_and_skill(self):
        # The workflow name itself contains a hyphen, so it has to be supplied.
        self.assertEqual(archetype("jpe-desk-note-research", "jpe", "desk-note"), "desk-note/research")

    def test_without_a_workflow_the_split_is_a_documented_guess(self):
        self.assertEqual(archetype("jpe-desk-note-research", "jpe"), "desk/note-research")

    def test_the_client_prefix_is_dropped_even_when_unknown(self):
        self.assertEqual(archetype("acme-shared-ground-truth"), "shared/ground-truth")


class CalibrationRamp(ConductorTestCase):
    def agree(self, verdict_class, times, **kwargs):
        for _ in range(times):
            triage_lib.record_agreement(self.root, "c-shared-x", verdict_class, "agree", **kwargs)

    def test_shadow_is_the_starting_phase(self):
        self.assertEqual(triage_lib.calibration_phase(self.root), 0)
        self.assertFalse(triage_lib.is_automated(self.root, "transient"))

    def test_transient_earns_autonomy_at_the_bar(self):
        self.agree("transient", triage_lib.AUTONOMY_BAR - 1)
        self.assertFalse(triage_lib.is_automated(self.root, "transient"))
        self.agree("transient", 1)
        self.assertTrue(triage_lib.is_automated(self.root, "transient"))
        self.assertEqual(triage_lib.calibration_phase(self.root), 1)

    def test_a_disagreement_resets_the_streak(self):
        self.agree("transient", triage_lib.AUTONOMY_BAR)
        triage_lib.record_agreement(self.root, "c-shared-x", "transient", "disagree",
                                    actual_class="environment")
        self.assertFalse(triage_lib.is_automated(self.root, "transient"))

    def test_implementation_needs_transient_first(self):
        self.agree("implementation", triage_lib.AUTONOMY_BAR)
        self.assertFalse(triage_lib.is_automated(self.root, "implementation"),
                         "the ramp is ordered — transient auto comes first")
        self.agree("transient", triage_lib.AUTONOMY_BAR)
        self.assertTrue(triage_lib.is_automated(self.root, "implementation"))
        self.assertEqual(triage_lib.calibration_phase(self.root), 2)

    def test_a_contract_misclassification_zeroes_implementation(self):
        self.agree("transient", triage_lib.AUTONOMY_BAR)
        self.agree("implementation", triage_lib.AUTONOMY_BAR)
        self.assertTrue(triage_lib.is_automated(self.root, "implementation"))
        # Recorded as an agreement, but it was really a contract problem: the
        # drift failure mode the whole design exists to prevent.
        triage_lib.record_agreement(self.root, "c-shared-x", "implementation", "agree",
                                    actual_class="contract")
        self.assertFalse(triage_lib.is_automated(self.root, "implementation"))

    def test_contract_and_environment_never_automate(self):
        for cls in ("contract", "environment"):
            self.agree(cls, triage_lib.AUTONOMY_BAR * 3)
            self.assertFalse(triage_lib.is_automated(self.root, cls))

    def test_the_line_records_the_archetype_not_just_the_skill(self):
        # The workflow comes from the proposal that lists the skill.
        self.proposal(name="desk-note.md", skills=("jpe-desk-note-research",))
        with open(os.path.join(self.root, "proposals", "desk-note.md"), "w") as f:
            f.write("---\nworkflow: desk-note\nstatus: building\n"
                    "skills: [jpe-desk-note-research]\n---\n")
        line = triage_lib.record_agreement(self.root, "jpe-desk-note-research", "transient",
                                           "agree", client="jpe")
        self.assertEqual(line["archetype"], "desk-note/research")


class TriageTriggers(ConductorTestCase):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "docs"))
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(real_root, "docs", "triage-prompt.md")) as src:
            body = src.read()
        with open(os.path.join(self.root, "docs", "triage-prompt.md"), "w") as dst:
            dst.write(body)

    def triage_session(self, cls, action="retry"):
        """Fakes the triage subprocess by writing the verdict it would write."""
        def run(cmd, kwargs):
            target = os.path.join(self.root, "skills", "demo-skill", "TRIAGE.md")
            if "(conductor tick)" in cmd[2]:
                target = os.path.join(self.root, triage_lib.TICK_VERDICT_FILE)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w") as f:
                f.write(VERDICT.format(cls=cls, action=action, trigger="fake"))
            return 0
        return FakeRun(on_call=run)

    def test_each_trigger_writes_a_verdict_in_shadow_mode(self):
        for outcome, trigger in conductor.TRIAGE_TRIGGERS.items():
            with self.subTest(outcome=outcome):
                self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
                self.patch_run(self.triage_session("transient"))

                retried = conductor.triage_failure("demo-skill", outcome)

                verdict = triage_lib.read_verdict(self.root, "demo-skill")
                self.assertEqual(verdict["class"], "transient")
                self.assertEqual(verdict["autonomy"], "proposed", "shadow mode changes nothing")
                self.assertFalse(retried)
                os.unlink(triage_lib.verdict_path(self.root, "demo-skill"))

    def test_a_tick_error_triages_only_on_the_third_repeat(self):
        self.patch_run(self.triage_session("environment", "escalate-human"))
        conductor.triage_tick_error("boom")
        self.assertTrue(os.path.exists(os.path.join(self.root, triage_lib.TICK_VERDICT_FILE)))

    def test_an_earned_transient_verdict_is_applied_once(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
        for _ in range(triage_lib.AUTONOMY_BAR):
            triage_lib.record_agreement(self.root, "demo-skill", "transient", "agree")
        conductor.record_attempt("demo-skill")
        conductor.record_attempt("demo-skill")
        conductor.record_attempt("demo-skill")
        self.patch_run(self.triage_session("transient"))

        self.assertTrue(conductor.triage_failure("demo-skill", "exhausted"))
        self.assertEqual(conductor.attempts_used("demo-skill"), 0, "budget restored for one more run")
        self.assertEqual(read_fm(triage_lib.verdict_path(self.root, "demo-skill"))[0]["autonomy"],
                         "applied")

        # A second failure in the same proposal version must not re-apply.
        conductor.record_attempt("demo-skill")
        self.assertFalse(conductor.triage_failure("demo-skill", "exhausted"))
        self.assertEqual(conductor.attempts_used("demo-skill"), 1)

    def test_a_contract_verdict_is_never_applied_however_much_agreement_exists(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
        for _ in range(triage_lib.AUTONOMY_BAR * 3):
            triage_lib.record_agreement(self.root, "demo-skill", "contract", "agree")
        conductor.record_attempt("demo-skill")
        self.patch_run(self.triage_session("contract", "escalate-structural"))

        self.assertFalse(conductor.triage_failure("demo-skill", "change-request"))
        self.assertEqual(conductor.attempts_used("demo-skill"), 1)


if __name__ == "__main__":
    unittest.main()
