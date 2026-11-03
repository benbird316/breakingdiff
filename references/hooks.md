# Host hook installation and runtime details

The optional Stop hook in full: the installation snippet, the `.breakingdiff/` markers the decision reads, the judge order with its exit codes, and the boundary of what the hook can honestly buy.

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
  "command": "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"python scripts/hook_entry.py; exit $LASTEXITCODE\"" }
```

The trailing `; exit $LASTEXITCODE` is not cosmetic: without it the wrapper returns 1 for any non-zero Python exit, and the host only blocks on exit 2 — every injection would be silently downgraded to a no-op.

The path in `scripts/hook_entry.py` is relative to the project root (Claude Code runs hook commands with the project root as cwd). Python must be on PATH.

## Preinstalled registration (template form, optional)

When distributed as a plugin, you can preinstall the hooks registration in the plugin manifest, so installing the plugin brings the hook along and nobody has to paste settings.json by hand. The template (i-have-adhd's hooks/hooks.json) works through a trio: preinstalled registration, plugin-root variable resolution, and a silent backstop — the command reads the environment variable CLAUDE_PLUGIN_ROOT first, falls back to PLUGIN_ROOT when empty, and skips loading when neither resolves; the whole command is wrapped in a silent backstop (the template uses `.catch(()=>{})`), so a hook that fails on its own does not block the turn.

Three preconditions: it applies to the plugin form only, and the root variable resolves only because the host injects it; the manual form still pastes settings.json using the installation snippet above; a skill cannot register itself, so the landing point of preinstalled registration is the plugin manifest, not the skill directory. Do not copy the template's SessionStart/always-on semantics — this repository's hook is a Stop difference gate, the two semantics are not the same source; copy only the trio form above.

## The `.breakingdiff/` working directory convention

The hook decision is a **product state machine** (disk markers, not transcript semantics). The disk layout, relative to the project root:

| File | Who writes it | When |
| --- | --- | --- |
| `.breakingdiff/pending` | begin_differential in `scripts/receipt.py` | written when the differential starts (content is irrelevant; presence is the marker); removed when `write_receipt` persists a receipt |
| `.breakingdiff/receipt.json` | write_receipt in `scripts/receipt.py` | compare finishes and writes to disk; cleared when a new differential starts |
| `.breakingdiff/expected.json` | write_expected in `scripts/receipt.py` | blind-written expectation (optional, used by reconcile) |

## Judge order and exit codes

    1. stdin is empty or not JSON → exit 0 silently
    2. stop_hook_active=true → exit 0 immediately (prevents a Stop block loop; before any disk I/O)
    3. no marker (`.breakingdiff/` missing) → exit 0 instantly (first fast-path branch; Stop fires every turn, so slow means slow every turn)
    4. pending marker on disk → exit 2 + feed actionable text back over stderr (a differential started and no receipt closed it; receipt internal 2 = runtime error, whose shape is "no receipt produced")
    5. receipt gate fails → exit 2 + the difference fed back on stderr (receipt internal 1 → hook 2)
    6. otherwise → exit 0

`pending` on disk is the whole in-flight state: `begin_differential` writes it before removing a previous receipt, and `write_receipt` removes it in the same step that persists the receipt. A crash that leaves both markers reads as open and the next begin/write repairs it. Once closed, later edits to claim-bearing files are not stale against the receipt: it describes the round that ended, not the working tree, and reconciling it on idle turns would turn unrelated edits into a permanent red — the loudest way to break the promise above.

The transcript lags asynchronously at Stop time (the official docs confirm it); the decision looks only at disk artifacts and never reads transcript semantics — disk checks are deterministic, sub-second, and have no transcript dependency.

## Honest degradation

The hook is a staleness reminder, not a requirements judge: it raises the cost of sloppiness, not the cost of forgery. If no differential starts, it stays silent; a red says "rerun the compare", never "the claim failed". It is a backstop rather than a replacement — the same root cause as the three gates in the body of the skill, where a cheap disk marker beats a promise the agent can talk its way around.
