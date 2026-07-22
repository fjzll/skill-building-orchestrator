"""Phase 4 exit criteria: shared-first then parallel, doctor flags a stall, retrospect renders."""
import json
import os
import threading
import time
import unittest

from conductor_fixture import ConductorTestCase, FakeRun

import conductor
import doctor
import retrospect

EVAL_YAML = "output: output.md\nlayer1:\n  required_fields: [cash]\n"

PROPOSAL_BODY = """
### c-shared-ground-truth
- **Shared dependencies:** none

### c-desk-note-research
- **Shared dependencies:** c-shared-ground-truth

### c-desk-note-drafting
- **Shared dependencies:** c-shared-ground-truth
"""


class DependencyLevels(unittest.TestCase):
    skills = ["c-shared-ground-truth", "c-desk-note-research", "c-desk-note-drafting"]

    def test_shared_dep_first_then_the_independent_pair(self):
        edges = conductor.shared_dependencies(PROPOSAL_BODY, self.skills)
        levels = conductor.build_levels(self.skills, edges)
        self.assertEqual(levels, [["c-shared-ground-truth"],
                                  ["c-desk-note-research", "c-desk-note-drafting"]])

    def test_no_dependency_lines_means_one_level(self):
        levels = conductor.build_levels(self.skills, conductor.shared_dependencies("", self.skills))
        self.assertEqual(levels, [self.skills])

    def test_a_dependency_cycle_degrades_to_listed_order(self):
        edges = {"a": {"b"}, "b": {"a"}}
        self.assertEqual(conductor.build_levels(["a", "b"], edges), [["a"], ["b"]])


class ParallelBuilds(ConductorTestCase):
    def test_independent_skills_run_concurrently(self):
        skills = ["c-shared-ground-truth", "c-desk-note-research", "c-desk-note-drafting"]
        for skill in skills:
            self.skill_dir(skill, {"eval/eval.yaml": EVAL_YAML, "SKILL.md": "# skill"})
        path = os.path.join(self.root, "proposals", "p1.md")
        with open(path, "w") as f:
            f.write(f"---\nworkflow: desk-note\nstatus: building\n"
                    f"skills: [{', '.join(skills)}]\n---\n{PROPOSAL_BODY}")

        concurrent, peak = set(), []
        lock = threading.Lock()

        def slow_test(skill):
            with lock:
                concurrent.add(skill)
                peak.append(len(concurrent))
            time.sleep(0.05)
            with lock:
                concurrent.discard(skill)
            return "pass"

        self._patch(conductor, "test_skill", slow_test)
        meta, content = conductor.read_fm(path)
        conductor.advance_proposal(path, meta, content)

        self.assertEqual(self.status_of(path), "tested")
        self.assertEqual(max(peak), 2, "the two independent skills overlapped")
        self.assertIn("in parallel", self.log_text())


class Doctor(ConductorTestCase):
    def test_a_stalled_proposal_is_flagged(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
        path = self.proposal(status="building")
        stale = time.time() - (doctor.STALL_MINUTES + 5) * 60
        for name in (".build-attempts",):
            marker = os.path.join(self.root, "skills", "demo-skill", name)
            with open(marker, "w") as f:
                f.write("1")
            os.utime(marker, (stale, stale))

        findings = doctor.proposal_checks(self.root)

        self.assertTrue(any("stalled" in message for _, message in findings), findings)

    def test_recent_progress_is_not_a_stall(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML, "BUILD_LOG.md": "12:00 working\n"})
        self.proposal(status="building")
        findings = doctor.proposal_checks(self.root)
        self.assertFalse(any("stalled" in message for _, message in findings), findings)

    def test_skill_state_reports_budget_and_suite(self):
        self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML, "SKILL.md": "# s"})
        conductor.record_attempt("demo-skill")
        rows = doctor.skill_states(self.root)
        self.assertEqual(rows[0]["attempts"], "1/3")
        self.assertEqual(rows[0]["suite"], "present")
        self.assertTrue(rows[0]["built"])

    def test_an_unreviewed_verdict_is_surfaced(self):
        sdir = self.skill_dir("demo-skill", {"eval/eval.yaml": EVAL_YAML})
        with open(os.path.join(sdir, "TRIAGE.md"), "w") as f:
            f.write("---\nclass: transient\naction: retry\nautonomy: proposed\n---\n\nbody\n")
        findings = doctor.awaiting_human(self.root)
        self.assertTrue(any("awaiting review" in message for _, message in findings), findings)

    def test_a_healthy_repo_exits_zero(self):
        with open(os.path.join(self.root, "client.yaml"), "w") as f:
            f.write("slug: demo\ndisplay_name: Demo\n")
        os.makedirs(os.path.join(self.root, "analysis"), exist_ok=True)
        with open(os.path.join(self.root, "analysis", "facts.yaml"), "w") as f:
            f.write("workflows: []\n")
        self.assertEqual(doctor.run(self.root), 0)


class Retrospect(ConductorTestCase):
    def test_the_report_renders_from_artifacts_on_disk(self):
        sdir = self.skill_dir("c-shared-ground-truth", {"eval/eval.yaml": EVAL_YAML})
        for attempt, passed in ((1, False), (2, True)):
            card = {"layer1": {"checks": [{"check": "required: cash", "pass": passed}]},
                    "layer2": {"ungrounded": [] if passed else ["42"]},
                    "gate": {"overall": passed}}
            with open(os.path.join(sdir, "eval", f"scorecard.attempt-{attempt}.json"), "w") as f:
                json.dump(card, f)
        with open(os.path.join(sdir, "eval", "scorecard.json"), "w") as f:
            json.dump({"gate": {"overall": True}}, f)
        with open(os.path.join(self.root, "client.yaml"), "w") as f:
            f.write("slug: c\ndisplay_name: Client C\n")

        self.assertEqual(retrospect.run(self.root), 0)

        with open(os.path.join(self.root, "analysis", "retrospect.md")) as f:
            report = f.read()
        self.assertIn("Client C", report)
        self.assertIn("shared/ground-truth", report)
        self.assertIn("| c-shared-ground-truth | shared/ground-truth | 2 | yes |", report)
        self.assertIn("layer 1 — deterministic checks", report)

    def test_an_empty_repo_still_renders(self):
        self.assertEqual(retrospect.run(self.root), 0)
        with open(os.path.join(self.root, "analysis", "retrospect.md")) as f:
            self.assertIn("No scorecards on disk yet", f.read())


if __name__ == "__main__":
    unittest.main()
