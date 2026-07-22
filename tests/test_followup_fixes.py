"""Follow-up fixes after the plan audit: judge model, grill seed, timeouts,
gate-pass short-circuit, and attempt-archive indexing."""
import os
import subprocess
import unittest

from conductor_fixture import ConductorTestCase, FakeRun

import conductor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EVAL_YAML = """fixtures: [fixtures/source.txt]
output: output.md
layer1:
  required_fields: ["cash", "catalysts"]
layer2:
  number_sources: [fixtures/source.txt]
"""
SOURCE = "cash of 12.4m, three catalysts ahead\n"


class JudgeModelIsValid(unittest.TestCase):
    def test_the_default_is_not_the_known_bad_identifier(self):
        harness = os.path.join(REPO, "evals", "harness", "run_evals.py")
        with open(harness) as f:
            body = f.read()
        self.assertNotIn("claude-sonnet-5", body,
                         "claude-sonnet-5 is not a valid API model identifier; "
                         "the layer 3 judge 404s the first time it runs")


class GrillSeedWritesTheSuite(unittest.TestCase):
    def test_the_seed_exit_protocol_includes_the_executable_suite(self):
        with open(os.path.join(REPO, "docs", "grill-seed.txt")) as f:
            seed = f.read()
        self.assertIn("eval/eval.yaml", seed,
                      "the seed's enumerated exit protocol is what a session "
                      "follows; if it omits the suite, every proposal blocks at confirm")


class TimeoutsConsumeTheAttempt(ConductorTestCase):
    def _timeout_fake(self):
        def raise_timeout(cmd, kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))
        fake = FakeRun()
        fake.on_call = raise_timeout
        return self.patch_run(fake)

    def test_a_hung_build_is_a_retry_not_a_tick_crash(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "brief",
                                      "eval/eval.yaml": EVAL_YAML})
        self._timeout_fake()
        outcome = conductor.build_skill("demo-skill")
        self.assertEqual(outcome, "retry")
        self.assertEqual(conductor.attempts_used("demo-skill"), 1)
        self.assertIn("TIMED OUT", self.log_text())

    def test_a_hung_build_on_the_final_attempt_exhausts_the_budget(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "brief",
                                      "eval/eval.yaml": EVAL_YAML})
        for _ in range(conductor.BUILD_ATTEMPT_CAP - 1):
            conductor.record_attempt("demo-skill")
        self._timeout_fake()
        self.assertEqual(conductor.build_skill("demo-skill"), "exhausted")

    def test_a_hung_refine_maps_to_a_next_tick_retry(self):
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "brief"})
        self._timeout_fake()
        self.assertEqual(conductor.refine_skill("demo-skill", ["required: cash"]),
                         "timeout")
        self.assertEqual(conductor.attempts_used("demo-skill"), 1)

    def test_a_hung_triage_leaves_the_failure_for_a_human(self):
        os.makedirs(os.path.join(self.root, "docs"), exist_ok=True)
        with open(os.path.join(self.root, "docs", "triage-prompt.md"), "w") as f:
            f.write("{SKILL} {TRIGGER} {OUTPUT} {EVIDENCE}")
        self.skill_dir("demo-skill", {"BUILD_BRIEF.md": "brief"})
        self._timeout_fake()
        verdict = conductor.triage("demo-skill", "build FAILED")
        self.assertIsNone(verdict)
        self.assertIn("TIMED OUT", self.log_text())


class GatePassShortCircuit(ConductorTestCase):
    def test_a_passed_skill_is_not_rebuilt_or_retested(self):
        self.skill_dir("demo-skill", {"SKILL.md": "# skill",
                                      "eval/eval.yaml": EVAL_YAML,
                                      "fixtures/source.txt": SOURCE})
        conductor.record_gate_pass("demo-skill", "frozenhash")
        run = self.patch_run(FakeRun())
        conductor.converge_skill("demo-skill", ["demo-skill"], None)
        # The marker was stamped under a different hash, so it must not satisfy
        # this proposal: the harness has to actually run again.
        self.assertNotEqual(run.calls, [], "a stale marker must force a real re-test")

        conductor.record_gate_pass("demo-skill", None)  # stamped for this version
        run.calls.clear()
        outcome = conductor.converge_skill("demo-skill", ["demo-skill"], None)
        self.assertEqual(outcome, "pass")
        self.assertEqual(run.calls, [], "no build, no harness, no judge calls")

    def test_reconfirming_a_proposal_invalidates_the_old_pass(self):
        self.skill_dir("demo-skill", {"SKILL.md": "# skill",
                                      "eval/eval.yaml": EVAL_YAML,
                                      "fixtures/source.txt": SOURCE})
        conductor.record_gate_pass("demo-skill", "oldhash")
        path = self.proposal(status="confirmed", skills=("demo-skill",))
        from fm import read_fm
        conductor.confirm_proposal(path, read_fm(path)[0])
        self.assertFalse(os.path.exists(conductor.pass_marker_file("demo-skill")),
                         "a new proposal version must re-earn its pass")


class ArchiveIndexSurvivesTicks(ConductorTestCase):
    def setUp(self):
        super().setUp()
        harness_dir = os.path.join(self.root, "evals", "harness")
        os.makedirs(harness_dir)
        with open(os.path.join(REPO, "evals", "harness", "run_evals.py")) as src:
            body = src.read()
        with open(os.path.join(harness_dir, "run_evals.py"), "w") as dst:
            dst.write(body)

    def test_each_attempt_keeps_its_own_scorecard(self):
        sdir = self.skill_dir("demo-skill", {
            "BUILD_BRIEF.md": "brief",
            "eval/eval.yaml": EVAL_YAML,
            "fixtures/source.txt": SOURCE,
        })
        real_run = subprocess.run

        def claude_or_real(cmd, **kwargs):
            if cmd[0] == "claude":
                # Every build/refine "succeeds" but the output never satisfies
                # layer 1, so the loop burns the whole budget.
                with open(os.path.join(sdir, "SKILL.md"), "w") as f:
                    f.write("# skill")
                with open(os.path.join(sdir, "output.md"), "w") as f:
                    f.write("cash of 12.4m\n")
                return FakeRun.Result(0)
            return real_run(cmd, **kwargs)

        self._patch(conductor.subprocess, "run", claude_or_real)
        from eval_suite import suite_hash
        frozen = suite_hash(self.root, ["demo-skill"])
        outcome = conductor.converge_skill("demo-skill", ["demo-skill"], frozen)
        self.assertEqual(outcome, "exhausted")
        archived = sorted(n for n in os.listdir(os.path.join(sdir, "eval"))
                          if n.startswith("scorecard.attempt-"))
        self.assertEqual(archived, [f"scorecard.attempt-{i}.json"
                                    for i in range(1, conductor.BUILD_ATTEMPT_CAP + 1)],
                         "one archive per budget attempt, none overwritten")


if __name__ == "__main__":
    unittest.main()
