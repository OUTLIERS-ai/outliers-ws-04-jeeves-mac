# -*- coding: utf-8 -*-
"""Build a made-up world for Jeeves to look at: two vaults, agents and session logs.

    python tools/demo.py D:/somewhere/jeeves-demo           build it and print the config path
    python tools/demo.py D:/somewhere/jeeves-demo --serve   build it and start Jeeves on it

Everything here is invented: "Sam the bookkeeper", his clients, his notes. The
chat uses tools/fake_claude.py, so the demo never calls an AI or spends a token.
The tests and the guide's screenshots are both built from this, so what you see
in the guide is what the tests check.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def w(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def brain(root, now):
    b = root / "Second Brain"
    w(b / "CLAUDE.md", "# How to work in this second brain\n\n## What this is\n\n"
      "Sam's bookkeeping practice: 14 small-business clients, month-end and VAT.\n")
    w(b / "People" / "Tom Reyes.md", "---\ntype: person\n---\n\n# Tom Reyes\n\n"
      "Runs a 4-person joinery. Mentioned VAT twice on the last call.\n\n"
      "- [ ] Send Tom the VAT checklist before Thursday\n")
    w(b / "People" / "Priya Shah.md", "---\ntype: person\n---\n\n# Priya Shah\n\n"
      "Priya Shah Design. Asked about month-end help on 2 days' notice.\n")
    w(b / "Projects" / "Pricing review.md", "---\ntype: project\n---\n\n# Pricing review\n\n"
      "Moving from hourly to 3 fixed monthly packages.\n\n"
      "| Package | Clients | Monthly |\n|---|---|---|\n| Books only | 6 | £180 |\n"
      "| Books + VAT | 5 | £290 |\n| Full month-end | 3 | £450 |\n\n"
      "- [x] List every client's hours for August\n- [ ] Draft the letter to existing clients\n"
      "- [ ] Decide what happens to the 2 clients under 3 hours a month\n")
    w(b / "Meetings" / "Call with Tom Reyes.md", "# Call with Tom Reyes\n\n"
      "He wants quarterly VAT done for him. Link: [[Tom Reyes]].\n")
    w(b / "Ideas" / "Month-end checklist as a lead magnet.md",
      "# Month-end checklist as a lead magnet\n\nA one-page checklist, given away on LinkedIn.\n")
    w(b / "Decisions" / "Stop taking payroll clients.md", "# Stop taking payroll clients\n\n"
      "Decided in August. Payroll is 20% of hours and 8% of income.\n")
    w(b / "Areas" / "Marketing.md", "# Marketing\n\n- [ ] Post the month-end checklist\n")
    w(b / "Daily" / (now.strftime("%Y-%m-%d") + ".md"),
      "# %s\n\n- 09:30 Call with Hannah Cole (new role, finance lead)\n"
      "- 11:00 Month-end for Priya Shah Design\n- [ ] Reply to Leah about the quarterly figures\n"
      % now.strftime("%A %d %B"))
    w(b / "Inbox" / "Recommendations.md", "# Recommendations\n\n"
      "Your agents write here. You decide.\n\n"
      "- [ ] **Raise the Books-only package to £195** - 4 of 6 clients are over their hours "
      "(from the pricing agent, today)\n"
      "- [ ] **Turn the month-end checklist into a post** - 3 clients asked for it this month\n"
      "- [ ] **Chase 2 unpaid invoices** - both over 30 days (from the invoice chaser)\n")
    w(b / ".claude" / "agents" / "note-filer.md", "---\nname: note-filer\ndescription: Files "
      "anything dropped in Inbox into the right room (People, Projects, Meetings) and links it.\n"
      "model: sonnet\n---\n\nYou file notes.\n")
    w(b / ".claude" / "agents" / "meeting-summariser.md", "---\nname: meeting-summariser\n"
      "description: Turns a call transcript into a Meetings note with decisions and next steps.\n"
      "---\n\nYou summarise meetings.\n")
    return b


CRM_TODAY = """# Today

_Built for 08:30. Open this before you open your inbox._

_Generated {date} from the event log. Do not edit by hand: this page is rewritten from scratch every run._

| # | Who | Why they are here | When |
|---|---|---|---|
| 1 | Priya Shah | Replied | 19 hours ago |
| 2 | Tom Reyes | Booked a call | 2 days ago |
| 3 | Hannah Cole | Changed role | 3 days ago |
| 4 | Leah Grant | Engaged with something you posted | 4 days ago |
| 5 | Marcus Webb | Quiet, and due a word | 23 days ago |

Ordered by how fast each reason cools off. A reply ranks first
because it cools fastest.

---

- 1 person left off because you picked that conversation up yourself.
- 2 parked themselves after 30 days of silence. Nobody had to decide to give up on them.
"""


def crm(root, now):
    c = root / "CRM"
    w(c / "Today.md", CRM_TODAY.format(date=now.strftime("%Y-%m-%d")))
    w(c / "_layers" / "config.json", json.dumps({"layer": 7, "start-time": "08:30"}))
    for n, what in [("Priya Shah", "Priya Shah Design, 3 staff."), ("Tom Reyes", "Joinery, 4 staff."),
                    ("Hannah Cole", "Finance lead at a 12-person agency."),
                    ("Leah Grant", "Florist, 2 shops."), ("Marcus Webb", "Café owner.")]:
        w(c / "People" / (n + ".md"), "---\ntype: person\n---\n\n# %s\n\n%s\n" % (n, what))
    return c


def agents(home):
    a = home / ".claude" / "agents"
    w(a / "invoice-chaser.md", "---\nname: invoice-chaser\ndescription: Finds invoices over 30 "
      "days, drafts a polite chase for each, and leaves the drafts for you to send. Never sends.\n"
      "model: sonnet\ntools: Read, Grep, Write\n---\n\nYou chase invoices.\n")
    w(a / "month-end-helper.md", "---\nname: month-end-helper\ndescription: Walks one client's "
      "month-end: bank reconciliation, missing receipts, questions for the client.\n---\n\nHelp.\n")
    w(a / "follow-up-writer.md", "---\nname: follow-up-writer\ndescription: Writes a short "
      "follow-up to one person in the CRM, using their note and their last message.\n"
      "model: opus\n---\n\nWrite follow-ups.\n")


def sessions(home, brain_dir, crm_dir, now):
    proj = home / ".claude" / "projects"
    plan = [
        (brain_dir, "Draft the letter about new packages", 5, 0.5, "claude-opus-5"),
        (brain_dir, "Who should I call today", 3, 1.5, "claude-opus-5"),
        (crm_dir, "Clean up duplicate people in the CRM", 7, 3.0, "claude-sonnet-5"),
        (brain_dir, "Summarise the call with Tom", 2, 6.5, "claude-haiku-4-5"),
        (crm_dir, "Why is Marcus on the list", 4, 26.0, "claude-sonnet-5"),
    ]
    for i, (cwd, title, turns, hours_ago, model) in enumerate(plan):
        sid = str(uuid.UUID(int=1000 + i))
        folder = proj / ("demo-" + Path(cwd).name.replace(" ", "-"))
        lines = [{"type": "ai-title", "aiTitle": title, "sessionId": sid}]
        t0 = now - timedelta(hours=hours_ago)
        for k in range(turns):
            ts = (t0 + timedelta(minutes=4 * k)).astimezone().isoformat()
            lines.append({"type": "user", "cwd": str(cwd), "sessionId": sid, "timestamp": ts,
                          "message": {"role": "user", "content": "%s (part %d)" % (title, k + 1)}})
            usage = {"input_tokens": 40 + k, "output_tokens": 600 + 50 * k,
                     "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 18000 + 4000 * k}
            msg = {"id": "msg_%d_%d" % (i, k), "model": model, "usage": usage,
                   "content": [{"type": "text", "text": "..."}]}
            # The same reply written twice, as Claude Code does: it must be counted once.
            lines.append({"type": "assistant", "cwd": str(cwd), "sessionId": sid, "timestamp": ts,
                          "requestId": "req_%d_%d" % (i, k), "message": msg})
            lines.append({"type": "assistant", "cwd": str(cwd), "sessionId": sid, "timestamp": ts,
                          "requestId": "req_%d_%d" % (i, k), "message": msg})
        w(folder / (sid + ".jsonl"), "\n".join(json.dumps(x) for x in lines) + "\n")


def build(root, port=4099, now=None):
    # the same download links the installer writes: the Mac copies on a Mac (wave 6)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from jeeves.config import app_repo
    now = now or datetime.now()
    root = Path(root).resolve()
    home = root / "home"
    b = brain(root, now)
    c = crm(root, now)
    agents(home)
    sessions(home, b, c, now)
    cfg = {
        "name": "Jeeves", "port": port, "second_brain": str(b), "crm_vault": str(c),
        "agents_dirs": [], "claude_home": str(home / ".claude"),
        "claude_command": [sys.executable, str(HERE / "fake_claude.py")],
        "apps": {"projectforge": {"url": "http://127.0.0.1:3020",
                                  "repo": app_repo("outliers-ws-03-projectforge")},
                 "fleetview": {"url": "http://127.0.0.1:3010",
                               "repo": app_repo("outliers-ws-02-fleetview")}},
        "ccusage": "off",
    }
    cfg_path = root / "config.json"
    w(cfg_path, json.dumps(cfg, indent=2))
    return cfg_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--port", type=int, default=4099)
    ap.add_argument("--serve", action="store_true")
    a = ap.parse_args()
    cfg = build(a.folder, a.port)
    print(cfg)
    if a.serve:
        # The demo keeps its own working files, so it never touches your real
        # Jeeves's conversation or its record of which copy is running.
        import os
        os.environ.setdefault("JEEVES_STATE", str(Path(a.folder).resolve() / "state"))
        sys.path.insert(0, str(ROOT))
        from start import main as start_main
        return start_main(["--config", str(cfg), "--no-open"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
