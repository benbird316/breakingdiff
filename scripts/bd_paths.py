# -*- coding: utf-8 -*-
"""
bd_paths — four-level bd_home resolution (env → skill_dir → plugin_root → file_relative)
============================================================================
One entry point for "locate the breakingdiff repository root": four sources, first
match wins, and every candidate passes the same usability assertion (scripts/breakingdiff.py
under the candidate directory is a real file).

Decision point A (B6 spec freeze): a source is set (non-empty) but its candidate is
unusable → raise BdPathError at once, never degrade silently to the next level. An
explicit environment variable is the user's or host's intent, and silently substituting
it would drop the degraded value into the legal readout domain — "resolved" against the
wrong directory is worse than not resolved at all. An empty string counts as unset
(skipped). When all four levels are unset, fall back to file_relative; if the fallback
is unusable too, raise and stop. Do not guess cwd, do not fall back to cwd, do not touch
the network or global configuration. Pure standard library.
"""
import os

__all__ = ["BdPathError", "resolve_bd_home", "SOURCES"]

# source enumeration (B6 spec freeze; the B7 receipt persists by this), one-to-one with
# the resolution order
SOURCES = ("env", "skill_dir", "plugin_root", "file_relative")

# The first three levels: (environment variable name, source name); the fourth does not
# use an environment variable but walks two levels up from file_hint
_ENV_LEVELS = (
    ("BD_HOME", "env"),
    ("CLAUDE_SKILL_DIR", "skill_dir"),
    ("CLAUDE_PLUGIN_ROOT", "plugin_root"),
)

_ANCHOR = ("scripts", "breakingdiff.py")   # the usability assertion's anchor: must be a real file under the candidate


class BdPathError(ValueError):
    """bd_home resolution failed: an explicit source is unusable, or all four levels miss."""


def _anchor_ok(root):
    return os.path.isfile(os.path.join(root, *_ANCHOR))


def resolve_bd_home(environ=None, file_hint=None):
    """Resolve bd_home and return (absolute path, source). environ=None takes
    os.environ; file_hint=None takes this file's __file__ (parameter injection is for
    test isolation, so the process env is not polluted)."""
    env = os.environ if environ is None else environ
    hint = __file__ if file_hint is None else file_hint
    tried = []
    for name, source in _ENV_LEVELS:
        val = env.get(name) or ""            # None and the empty string are synonymous: unset
        if not val:
            continue
        tried.append(f"{source} ({name}={val}, missing {'/'.join(_ANCHOR)})")
        if _anchor_ok(val):
            return os.path.abspath(val), source
        # Decision point A: set but the candidate is unusable → raise at once, do not
        # degrade to the next level
        raise BdPathError(
            f"[bd_paths] source {source} is set ({name}={val}) but lacks "
            f"{'/'.join(_ANCHOR)} beneath it — an explicit environment variable is intent, "
            f"so do not degrade silently to the next level; sources tried: {'; '.join(tried)}")
    root = os.path.dirname(os.path.dirname(os.path.abspath(hint)))
    if _anchor_ok(root):
        return root, "file_relative"
    tried.append(f"file_relative (fallback {root}, missing {'/'.join(_ANCHOR)})")
    raise BdPathError(
        "[bd_paths] all four sources missed: "
        f"the three env levels ({'/'.join(name for name, _ in _ENV_LEVELS)}) are all unset; "
        f"sources tried: {'; '.join(tried)}. Do not guess cwd, do not fall back to cwd")
