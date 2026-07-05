"""Shared client.yaml loader.

Every client clone of this template carries a client.yaml at repo root
(gitignored in the template itself, committed in client clones):

    slug: jpe
    display_name: JP Equity Partners
    portal_title: Skill Implementation — JP Equity Partners
    template_commit: <hash>

If client.yaml is missing, this is a bare template clone — callers should
exit with a clear message rather than traceback. Use `load_client_config`
or `require_client_config` (which exits(1) for you) from any runner script.
"""
import os
import sys

import yaml

INIT_MESSAGE = (
    "No client.yaml found — this looks like a template clone, not a client repo.\n"
    "Run `./orch init <slug> \"<Display Name>\"` to turn it into a client repo."
)


def client_config_path(root="."):
    return os.path.join(root, "client.yaml")


def load_client_config(root="."):
    """Returns the parsed client.yaml dict, or None if it doesn't exist."""
    path = client_config_path(root)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def require_client_config(root="."):
    """Returns the parsed client.yaml dict, or exits(1) with INIT_MESSAGE."""
    cfg = load_client_config(root)
    if cfg is None:
        print(INIT_MESSAGE, file=sys.stderr)
        sys.exit(1)
    return cfg
