"""Shared fixture: point the conductor at a throwaway repo instead of this one."""
import os
import sys
import tempfile
import unittest

RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runner")
sys.path.insert(0, RUNNER)

import conductor  # noqa: E402


class FakeRun:
    """Stands in for subprocess.run: records calls, replays queued results."""

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def __init__(self, on_call=None, returncode=0):
        self.calls = []
        self.on_call = on_call
        self.returncode = returncode

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        rc = self.on_call(cmd, kwargs) if self.on_call else self.returncode
        return self.Result(rc)


class ConductorTestCase(unittest.TestCase):
    """Gives each test its own ROOT, so no test touches the real repo state."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = self.dir.name
        for sub in ("proposals", "skills", "analysis", "build-plans"):
            os.makedirs(os.path.join(self.root, sub))
        self._patch(conductor, "ROOT", self.root)
        self._patch(conductor, "LOG", os.path.join(self.root, "analysis", "conductor.log"))
        self._patch(conductor, "LOCK", os.path.join(self.root, "analysis", ".conductor-lock"))
        self._patch(conductor, "STAMP", os.path.join(self.root, "analysis", ".facts-stamp"))
        self._patch(conductor, "which", lambda _: "/usr/bin/claude")

    def _patch(self, module, name, value):
        original = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, original)

    def patch_run(self, fake):
        self._patch(conductor.subprocess, "run", fake)
        return fake

    def skill_dir(self, skill, files=None):
        sdir = os.path.join(self.root, "skills", skill)
        os.makedirs(sdir, exist_ok=True)
        for name, body in (files or {}).items():
            path = os.path.join(sdir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(body)
        return sdir

    def proposal(self, name="p1.md", status="confirmed", skills=("demo-skill",)):
        path = os.path.join(self.root, "proposals", name)
        with open(path, "w") as f:
            f.write(f"---\nworkflow: demo\nstatus: {status}\nskills: [{', '.join(skills)}]\n---\n\nbody\n")
        return path

    def status_of(self, path):
        from fm import read_fm
        return read_fm(path)[0].get("status")

    def log_text(self):
        with open(conductor.LOG) as f:
            return f.read()
