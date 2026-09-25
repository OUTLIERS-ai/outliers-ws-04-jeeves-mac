# What I stole

Everything here was either written fresh for this download or taken from the
places below. Nothing was copied from any private data, logs or settings.

| What | From | Licence | What we took |
|---|---|---|---|
| Dockview (`jeeves/static/vendor/dockview/`) | https://github.com/mathuo/dockview, package `dockview-core` version 4.9.0 from npm via jsDelivr | MIT, Copyright (c) 2021 mathuo. Its LICENSE file is kept beside it. | The whole library, unchanged. It is what makes every panel dockable, tabbable and draggable, and saves the layout. The original Jeeves used the same version. |
| The orb (`jeeves/static/orb.js`) | Ashley's original Jeeves (`raphael-presence.js`, built overnight 2026-06-20 to 21) | Our own code, MIT | The animated SVG magic circle, renamed and cleaned: the rune text is now set in `config.json`, and the animation pauses while the tab is hidden. |
| The layout idea | The original Jeeves, 2026-06-13 | Our own code | Every ability as a Dockview panel; pop-out through `/?only=<panel>`; "+ Panel" so nothing is ever gone for good. |
| The chat runner | The original Jeeves's "brain" | Our own code, rewritten | Driving `claude -p --output-format stream-json --include-partial-messages`, resuming one Claude Code session per chat, and reading `text_delta` events as they stream. |
| The token reader | The original `token_stats.py` | Our own code, rewritten | Reading `usage` blocks from Claude Code's session files under `~/.claude/projects/`. New here: each reply counted once, not once per line. |
| The same idea as ccusage | https://github.com/ccusage/ccusage (npm version 20.0.24, checked 2026-09-22) | MIT | Nothing copied. Jeeves calls `ccusage blocks --active --json` only if you already have it installed. |
| Today's page | Outliers CRM Layer 7 (`Today.md`) and Second Brain Layer 4 (`today.py`) | Our own code | The CRM page is read as it is. For the second brain, the same idea as Layer 4's morning list (what moved, what is left unticked), plus today's daily note if you keep one. |

## Left behind on purpose

The original Jeeves had a cloned voice, a phone app, a login screen, a
PowerShell terminal, a 3D map of agents, email and calendar connectors, a
15-minute heartbeat and an embedded outreach app. None of that is here. The
guide explains why each one was dropped or is left for you to add.
