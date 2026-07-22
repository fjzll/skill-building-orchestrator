"""Frontmatter read/write for proposal and verdict files.

The frontmatter block is parsed as YAML, so values containing ':' or '#'
round-trip intact instead of being truncated by a naive split. Writes go
through a temp file + os.replace, so a portal Confirm and a conductor tick
cannot interleave and leave a half-written proposal on disk.
"""
import os
import re
import tempfile

import yaml

FM_RE = re.compile(r"^---\n([\s\S]*?)\n---")


def read_fm(path):
    """Returns (metadata dict, full file text). No frontmatter -> ({}, text)."""
    with open(path) as f:
        txt = f.read()
    m = FM_RE.match(txt)
    if not m:
        return {}, txt
    meta = yaml.safe_load(m.group(1))
    if not isinstance(meta, dict):
        return {}, txt
    return meta, txt


def format_value(value):
    """YAML-encode a scalar so ':' and '#' survive the round trip."""
    out = yaml.safe_dump(value, default_flow_style=True, width=10**6).strip()
    if out.endswith("..."):
        out = out[: -len("...")].strip()
    return out


def write_atomic(path, text):
    """Replace path's contents in one rename — no torn reads for a concurrent tick."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".fm-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_fm(path, key, value):
    """Set one frontmatter key, preserving the rest of the block and the body."""
    with open(path) as f:
        txt = f.read()
    m = FM_RE.match(txt)
    if not m:
        raise ValueError(f"{path} has no frontmatter block to update")
    block = m.group(1)
    line = f"{key}: {format_value(value)}"
    key_re = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    block = key_re.sub(line, block) if key_re.search(block) else block + "\n" + line
    write_atomic(path, txt.replace(m.group(0), f"---\n{block}\n---", 1))
