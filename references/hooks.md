# Host hook installation and runtime details

The companion detail page for the "Host hook (optional install)" section of SKILL.md. The decision semantics and the honest degradation follow the body of SKILL.md; this page carries only the installation steps and the field conventions.

## Installation snippet (Claude Code, a manual user action)

Hooks configuration changes must be reviewed through the `/hooks` menu to take effect — a skill cannot register itself. This is the host's security design, not a defect. Add the following to the project `.claude/settings.json` or the global `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "python scripts/hook_entry.py" }
        ]
      }
    ]
  }
}
```

On Windows, if the direct command trips over shell quoting, use the PowerShell wrapper variant:

```json
{ "type": "command",
  "command": "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"python scripts/hook_entry.py\"" }
```

The path in `scripts/hook_entry.py` is relative to the project root (Claude Code runs hook commands with the project root as cwd). Python must be on PATH.

## Preinstalled registration (template form, optional)

When distributed as a plugin, you can preinstall the hooks registration in the plugin manifest, so installing the plugin brings the hook along and nobody has to paste settings.json by hand. The template (i-have-adhd's hooks/hooks.json) works through a trio: preinstalled registration, plugin-root variable resolution, and a silent backstop — the command reads the environment variable CLAUDE_PLUGIN_ROOT first, falls back to PLUGIN_ROOT when empty, and skips loading when neither resolves; the whole command is wrapped in a silent backstop (the template uses `.catch(()=>{})`), so a hook that fails on its own does not block the turn.

Three preconditions: it applies to the plugin form only, and the root variable resolves only because the host injects it; the manual form still pastes settings.json using the installation snippet above; a skill cannot register itself, so the landing point of preinstalled registration is the plugin manifest, not the skill directory. Do not copy the template's SessionStart/always-on semantics — this repository's hook is a Stop difference gate, the two semantics are not the same source; copy only the trio form above.

## The `.breakingdiff/` working directory convention

The disk state machine behind the hook decision (relative to the project root):

| File | Who writes it | When |
| --- | --- | --- |
| `.breakingdiff/pending` | agent | Write it before starting a claim differential (content is irrelevant; presence is the marker) |
| `.breakingdiff/receipt.json` | write_receipt in `scripts/receipt.py` | compare finishes and writes to disk |
| `.breakingdiff/expected.json` | write_expected in `scripts/receipt.py` | blind-written expectation (optional, used by reconcile) |

## Judge order and exit codes

    1. stdin is empty or not JSON → exit 0 silently
    2. stop_hook_active=true → exit 0 (prevents a Stop block loop; before any disk I/O)
    3. no marker (`.breakingdiff/` missing) → exit 0 in a split second (first fast-path branch; Stop fires every turn, so slow means slow every turn)
    4. pending without receipt → exit 2 + actionable text on stderr (receipt internal 2 = runtime error, whose shape is "no receipt produced")
    5. receipt gate fails → exit 2 + the difference fed back on stderr (receipt internal 1 → hook 2)
    6. claims newer than the receipt → exit 2 + stderr (stale artifact)
    7. otherwise → exit 0

Whether a claims file list is carried: the environment variable `BD_CLAIMS_FILES` (`os.pathsep`-separated, relative to cwd, injected by tests and special hosts) takes precedence; otherwise `git status --porcelain` (including untracked files). Not a git repository / git unavailable / timeout (10s) → empty list and skip the staleness check — with no list source, silence beats a false red.

The transcript lags asynchronously at Stop time (the official docs confirm it); the decision looks only at disk artifacts and never reads transcript semantics — disk checks are deterministic, sub-second, and have no transcript dependency.

The honest degradation semantics of the hook decision (a stale-artifact reminder rather than a requirements adjudicator, raising the cost of sloppiness without raising the cost of forgery, a backstop rather than a replacement, same root cause as the three gates) follow the "Host hook" section of SKILL.md; this page does not expand on them.
