"""The executable test suite for a skill: eval/eval.yaml plus its fixtures.

The suite is part of the contract, not part of the build. It is written at
grill exit, approved by the same Confirm that approves the proposal prose, and
hashed at that moment. Every later build and refine attempt is checked against
the confirm-time hash, so a builder cannot weaken a test to pass it.
"""
import hashlib
import os

CONFIG_RELPATH = os.path.join("eval", "eval.yaml")


def config_path(root, skill):
    return os.path.join(root, "skills", skill, CONFIG_RELPATH)


def suite_files(root, skill):
    """Every file the suite is made of, as (relative path, absolute path)."""
    sdir = os.path.join(root, "skills", skill)
    found = []
    cfg = config_path(root, skill)
    if os.path.exists(cfg):
        found.append((CONFIG_RELPATH, cfg))
    fixtures = os.path.join(sdir, "fixtures")
    for dirpath, _, filenames in os.walk(fixtures):
        for name in filenames:
            absolute = os.path.join(dirpath, name)
            found.append((os.path.relpath(absolute, sdir), absolute))
    return sorted(found)


def suite_hash(root, skills):
    """A single digest over the test suites of every skill in a proposal."""
    digest = hashlib.sha256()
    for skill in sorted(skills):
        for relpath, absolute in suite_files(root, skill):
            with open(absolute, "rb") as f:
                body = f.read()
            digest.update(f"{skill}/{relpath}\n".encode())
            digest.update(hashlib.sha256(body).hexdigest().encode())
            digest.update(b"\n")
    return digest.hexdigest()


def skills_missing_suite(root, skills):
    return [s for s in skills if not os.path.exists(config_path(root, s))]
