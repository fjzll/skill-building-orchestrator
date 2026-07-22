"""Archetype key for a skill name — the unit calibration data is pooled under.

Derived mechanically from the naming convention (ledger 000 item 1):

    <client>-shared-<skill>      -> shared/<skill>
    <client>-<workflow>-<skill>  -> <workflow>/<skill>

The client prefix is dropped on purpose: a verdict about "the shared
ground-truth skill" is evidence about that shape of work, not about the client
it happened at. Phase 5 aggregates fleet-wide on this key.

Workflow names contain hyphens (`desk-note`), so `desk-note-research` cannot be
split into workflow and skill by string surgery alone. Pass the proposal's
`workflow` field when you have it — `workflow_of()` in triage.py finds it. The
no-workflow fallback splits at the first hyphen and is therefore a guess; it
exists so a verdict is never dropped for want of a proposal.

FAMILIES maps names that differ between clients onto one archetype. It starts
empty: generalize only when two clients' names are demonstrably the same shape
of work, and record the merge as a ledger addendum in the template.
"""

FAMILIES = {}


def archetype(skill, client=None, workflow=None):
    name = skill
    if client and name.startswith(f"{client}-"):
        name = name[len(client) + 1:]
    elif "-" in name:
        name = name.split("-", 1)[1]  # unknown client prefix — drop the first segment
    if name.startswith("shared-"):
        key = "shared/" + name[len("shared-"):]
    elif workflow and name.startswith(f"{workflow}-"):
        key = f"{workflow}/{name[len(workflow) + 1:]}"
    elif "-" in name:
        head, tail = name.split("-", 1)
        key = f"{head}/{tail}"
    else:
        key = name
    return FAMILIES.get(key, key)
