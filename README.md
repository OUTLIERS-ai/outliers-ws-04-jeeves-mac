**This is the Mac version.** On Windows, use [outliers-ws-04-jeeves](https://github.com/OUTLIERS-ai/outliers-ws-04-jeeves).

# Jeeves: a personal-assistant cockpit over your own second brain and CRM

```
git clone https://github.com/OUTLIERS-ai/outliers-ws-04-jeeves-mac; cd outliers-ws-04-jeeves-mac; python3 install.py; python3 start.py
```

One browser page on your own computer. Every ability is a panel you can drag,
dock, stack as tabs, close, bring back and pop out onto another screen:

| Panel | What it shows |
|---|---|
| Chat | Your own Claude Code, working in your second brain with your CRM added. Replies stream in word by word. Model picker: best, deep, fast. |
| Today | Your CRM's `Today.md` (the daily ranked list from part 7 of the CRM series) and your second brain's day: today's daily note if you keep one, notes that moved in the last 3 days, unticked boxes. |
| Across everything | One screen that sums up what is moving: people to speak to, decisions waiting, notes moved, Claude use today, your other apps. |
| Recommendations | A markdown file in your second brain (`Inbox/Recommendations.md` by default) that you and your agents write to. |
| Vaults | Both vaults, read-only. Filter, search both, click `[[links]]`. |
| Agents | Every agent in `~/.claude/agents` and in each vault's `.claude/agents`, with its description and an "Ask in chat" button. |
| Activity | Your recent Claude Code conversations: which folder, how many turns, how many tokens. |
| Tokens | Today's tokens from Claude Code's own log files, by kind and by model; your 5-hour window if the free `ccusage` tool is installed. |
| Work board | ProjectForge (piece 3) inside the panel, if it is running. If not, the link to install it. |
| FleetView | FleetView (piece 2), the same way. |

The animated orb at the top left, and above the chat, shows what Jeeves is
doing: slow when idle, pulsing while Claude thinks, bright while the answer
streams in.

## What it needs

- Python 3.11 or newer. Nothing to install with pip: the server is Python's own library.
  (Python 3.9 and older no longer get security fixes, and 3.10 gets them only until
  2026-10-31; the installer refuses anything older than 3.11.)
- Claude Code, installed and logged in (`claude` works in a terminal).
- Your second brain (from the second-brain series). Your CRM is optional.

## Install

```
python3 install.py
```

It asks 5 questions: 4 about folders and the port (second brain folder, CRM
folder, agents folder, port), offering what it finds, then whether Jeeves should
start by itself, with no window, each time you switch on your computer and sign
in; the answer is no unless you type y. It writes `config.json`. Run it again
and nothing changes unless you give a different answer.

## Start and stop

```
python3 start.py            # opens http://127.0.0.1:4040/ ; Ctrl+C in that terminal stops it
python3 start.py --stop     # stops a copy started any other way
```

Only 1 copy runs per port: starting it again just says it is already running.

To experiment without touching the Jeeves you use every day, make a second copy
with a port of its own: `python3 install.py --copy ../jeeves-trial`, then
`cd ../jeeves-trial` and `python3 start.py`. The guide's "The safe way" explains.

**Layouts** (top bar) switches between 4 arrangements of all 10 panels (Big
screen, Laptop, Chat focus, Morning review) and saves your own. Double-click a
tab, or press the corner arrow of a group, to make it fill the screen; Esc
puts it back.

## What it will not do

- It never listens on your network: 127.0.0.1 only.
- It never writes to your vaults. The vault panels only read.
- It never runs Claude on a timer. Claude runs when you press Send, and at no other time.
- By default Chat is given 3 tools and no others: open a file, search inside
  files, find files by name (`--tools Read,Grep,Glob`). Everything else is
  absent, including anything you allowed in your own Claude Code settings, and
  anything Claude Code adds in a future version. Checked live on 2026-09-22
  against Claude Code 2.1.280: the session reported exactly `Glob, Grep, Read`,
  a request to write a file and run a command was refused and no file appeared,
  and a request to read a note was answered from the note. To let Chat act, set
  `"allow_actions": true` in `config.json` and choose a `"permission_mode"`
  (`"acceptEdits"` lets it edit notes). Every setting is described in
  `guide/GUIDE.md`, section "Every command and setting".

## Tests

```
python3 -m venv ~/outliers-checks
source ~/outliers-checks/bin/activate && python -m pip install pytest
source ~/outliers-checks/bin/activate && python -m pytest -q
```

On a Mac this says `64 passed, 13 skipped`: 4 checks look at files a Mac does
not use, and the other 9 open the page in a real browser
and run only when Playwright is installed (`python3 -m pip install playwright`, then
`python3 -m playwright install chromium`); skipped is fine. They run against made-up vaults in a temporary folder, with a stand-in for
Claude Code (`tools/fake_claude.py`), so no test touches your real files or
spends a token.

## Try it on made-up data first

```
python3 tools/demo.py ../jeeves-demo --serve --port 4099
```

Then open http://127.0.0.1:4099/ . It builds "Sam the bookkeeper": 2 vaults,
5 agents and a day of fake Claude logs. The chat answers from a script.

## Uninstall

```
python3 install.py --uninstall
```

Stops Jeeves, and removes the file that starts it by itself when the computer
starts, if one was made. Then delete this folder.

The full guide, with pictures and the story of how the original was built, is
in `guide/GUIDE.md`.

This repo is made automatically from outliers-ws-04-jeeves@ff560a0. To report a problem or suggest a change, use that repo, not this one.
