"""Phase 5: calibration transfer — priors accelerate, local evidence always wins."""
import json
import os
import tempfile
import unittest

from conductor_fixture import ConductorTestCase

import fleet
import triage as triage_lib


def line(archetype, cls, human="agree", client="acme", actual=None):
    return {"timestamp": "2026-07-22T00:00:00", "skill": "x", "archetype": archetype,
            "class": cls, "human": human, "actual_class": actual, "client": client}


class Aggregation(ConductorTestCase):
    def client_repo(self, slug, lines):
        root = os.path.join(self.root, slug)
        os.makedirs(os.path.join(root, "analysis"))
        with open(os.path.join(root, "client.yaml"), "w") as f:
            f.write(f"slug: {slug}\ndisplay_name: {slug}\n")
        with open(os.path.join(root, "analysis", "triage-calibration.jsonl"), "w") as f:
            for l in lines:
                f.write(json.dumps(l) + "\n")
        return root

    def test_verdicts_pool_by_archetype_across_clients(self):
        a = self.client_repo("acme", [line("shared/ground-truth", "transient")] * 4)
        b = self.client_repo("globex", [line("shared/ground-truth", "transient")] * 6)
        fleet_dir = os.path.join(self.root, "fleet")

        counts = fleet.aggregate(fleet_dir, [a, b])

        self.assertEqual(counts["shared/ground-truth"], 10)
        pooled = fleet.fleet_lines(fleet_dir)["shared/ground-truth"]
        self.assertEqual({l["client"] for l in pooled}, {"acme", "globex"})


class Priors(ConductorTestCase):
    def write_fleet(self, archetype, lines):
        fleet_dir = os.path.join(self.root, "fleet")
        os.makedirs(fleet.calibration_dir(fleet_dir), exist_ok=True)
        path = os.path.join(fleet.calibration_dir(fleet_dir),
                            archetype.replace("/", "__") + ".jsonl")
        with open(path, "w") as f:
            for l in lines:
                f.write(json.dumps(l) + "\n")
        return fleet_dir

    def test_a_well_evidenced_archetype_grants_transient(self):
        fleet_dir = self.write_fleet("shared/ground-truth",
                                     [line("shared/ground-truth", "transient")] * 10)
        priors = fleet.compute_priors(fleet_dir)
        self.assertIn("transient", priors["shared/ground-truth"])
        self.assertNotIn("implementation", priors["shared/ground-truth"])

    def test_implementation_needs_breadth_across_clients(self):
        one_client = [line("desk-note/research", "transient", client="acme")] * 10 + \
                     [line("desk-note/research", "implementation", client="acme")] * 20
        fleet_dir = self.write_fleet("desk-note/research", one_client)
        priors = fleet.compute_priors(fleet_dir)
        self.assertNotIn("implementation", priors["desk-note/research"],
                         "one busy client cannot speak for the fleet")

        spread = [line("desk-note/research", "transient", client=c) for c in ("a", "b", "c")] * 4 + \
                 [line("desk-note/research", "implementation", client=c) for c in ("a", "b", "c")] * 7
        fleet_dir = self.write_fleet("desk-note/research", spread)
        priors = fleet.compute_priors(fleet_dir)
        self.assertIn("implementation", priors["desk-note/research"])

    def test_one_contract_misclassification_anywhere_zeroes_the_archetype(self):
        lines = [line("shared/ground-truth", "transient")] * 20
        lines.append(line("shared/ground-truth", "implementation", client="globex",
                          actual="contract"))
        fleet_dir = self.write_fleet("shared/ground-truth", lines)
        self.assertNotIn("shared/ground-truth", fleet.compute_priors(fleet_dir),
                         "the fleet-wide circuit breaker fires for every client")

    def test_a_single_disagreement_blocks_the_prior(self):
        lines = [line("shared/ground-truth", "transient")] * 15
        lines.append(line("shared/ground-truth", "transient", human="disagree"))
        fleet_dir = self.write_fleet("shared/ground-truth", lines)
        self.assertNotIn("shared/ground-truth", fleet.compute_priors(fleet_dir))


class InheritedAutonomy(ConductorTestCase):
    def seed_priors(self, grants):
        path = os.path.join(self.root, fleet.PRIORS_FILE)
        fleet.write_priors(grants, path)

    def test_a_fresh_client_starts_automated_for_an_evidenced_archetype(self):
        self.seed_priors({"shared/ground-truth": {"transient": {"agreements": 12,
                                                                "clients": ["acme", "globex"]}}})
        # No local agreements at all — the streak is zero.
        self.assertEqual(triage_lib.consecutive_agreements(self.root, "transient"), 0)
        self.assertTrue(triage_lib.is_automated(self.root, "transient", "shared/ground-truth"))

    def test_the_prior_is_scoped_to_its_archetype(self):
        self.seed_priors({"shared/ground-truth": {"transient": {"agreements": 12, "clients": ["a"]}}})
        self.assertFalse(triage_lib.is_automated(self.root, "transient", "desk-note/research"))

    def test_a_local_disagreement_demotes_immediately_and_the_prior_cannot_override(self):
        self.seed_priors({"shared/ground-truth": {"transient": {"agreements": 12, "clients": ["a"]}}})
        triage_lib.record_agreement(self.root, "c-shared-ground-truth", "transient", "disagree",
                                    actual_class="environment", client="c",
                                    workflow=None)
        self.assertTrue(fleet.locally_demoted(self.root, "transient", "shared/ground-truth"))
        self.assertFalse(triage_lib.is_automated(self.root, "transient", "shared/ground-truth"))

    def test_an_inherited_implementation_prior_still_needs_transient(self):
        self.seed_priors({"shared/ground-truth": {
            "implementation": {"agreements": 25, "clients": ["a", "b", "c"]}}})
        self.assertFalse(triage_lib.is_automated(self.root, "implementation", "shared/ground-truth"))

    def test_contract_never_inherits_autonomy(self):
        self.seed_priors({"shared/ground-truth": {"contract": {"agreements": 99, "clients": ["a"]}}})
        self.assertFalse(triage_lib.is_automated(self.root, "contract", "shared/ground-truth"))

    def test_no_priors_file_means_shadow(self):
        self.assertFalse(triage_lib.is_automated(self.root, "transient", "shared/ground-truth"))


class EnginePathBoundary(unittest.TestCase):
    def test_client_data_paths_are_outside_the_upgrade_surface(self):
        for client_path in ("ledger/", "proposals/", "skills/", "build-plans/",
                            "deep-dives/", "analysis/", "client.yaml"):
            self.assertFalse(any(client_path.startswith(e) for e in fleet.ENGINE_PATHS),
                             f"{client_path} must never be touched by an upgrade")

    def test_the_engine_paths_exist_in_this_repo(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for engine_path in fleet.ENGINE_PATHS:
            self.assertTrue(os.path.exists(os.path.join(repo, engine_path.rstrip("/"))),
                            f"{engine_path} is listed as an engine path but does not exist")


if __name__ == "__main__":
    unittest.main()
