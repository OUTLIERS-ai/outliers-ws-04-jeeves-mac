# -*- coding: utf-8 -*-
"""config.py - one file of settings, read in one place.

The installer writes `config.json` next to `start.py`. Nothing else in Jeeves
knows where your vaults are: every module asks this file. A test can point the
whole program somewhere else by setting JEEVES_CONFIG to another file.
"""

import json
import os
import sys
from pathlib import Path

# The command a member types to run Python. A Mac has python3 and no python, so a
# printed "python start.py" fails there with "command not found".
PY = "python3" if sys.platform == "darwin" else "python"

# How to install ccusage. On a Mac, Node.js from nodejs.org refuses a plain global install
# ("EACCES: permission denied"); installing into ~/.local needs no password and puts ccusage in
# ~/.local/bin, where Jeeves finds it (GitHub's test Macs, 2026-09-25).
CCUSAGE_INSTALL = ("npm install -g --prefix ~/.local ccusage" if sys.platform == "darwin"
                   else "npm install -g ccusage")

# Where the Work board and FleetView are downloaded from. The Mac copy of each (its name
# ends in -mac) prints Mac commands. With this line True, a Mac member is sent to the Mac copy
# and a Windows member to the Windows repo. It was False until the Mac build plan's wave 6, which
# switched it on (2026-09-25); nothing else changes with it.
MAC_REPOS_PUBLISHED = True


def app_repo(name, mac=None):
    """The address to download the app `name` from, on this computer (or on a Mac if mac=True)."""
    mac = sys.platform == "darwin" if mac is None else mac
    return "https://github.com/OUTLIERS-ai/" + name + ("-mac" if mac and MAC_REPOS_PUBLISHED else "")


ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "name": "Jeeves",
    "port": 4040,
    "second_brain": "",
    "crm_vault": "",
    "agents_dirs": [],
    "claude_home": "",
    "claude_command": "claude",
    # Named in full, not as the short words "opus", "sonnet" and "haiku". Those words
    # move: on 2026-09-22 "opus" started meaning Claude Opus 5.5, so Jeeves was running
    # a model FleetView's price table had never heard of and the two disagreed about
    # what you were using. Names checked live against Claude Code 2.1.280 that day.
    # Put a short word back here if you would rather always follow the newest model.
    "models": {"best": "claude-opus-5-5", "deep": "claude-sonnet-5", "fast": "claude-haiku-4-5"},
    "default_model": "best",
    "permission_mode": "dontAsk",
    "chat_timeout_seconds": 600,
    "inbox_file": "",
    "daily_note_folders": ["Daily", "Daily Notes", "Journal", "Diary", "Calendar"],
    "apps": {
        "projectforge": {"url": "http://127.0.0.1:3020", "repo": app_repo("outliers-ws-03-projectforge")},
        "fleetview": {"url": "http://127.0.0.1:3010", "repo": app_repo("outliers-ws-02-fleetview")},
    },
    "ccusage": "auto",
    "orb": {"inner": "At your service", "outer": "Your second brain is listening"},
}


def config_path():
    env = os.environ.get("JEEVES_CONFIG")
    if env:
        return Path(env).expanduser()
    return ROOT / "config.json"


def _merge(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None):
    """Your settings, with every missing value filled from DEFAULTS.

    A file that cannot be read falls back to the defaults so Jeeves keeps running.
    Ask problem() what went wrong: saying nothing, or blaming a missing file, sent
    members looking in the wrong place.
    """
    p = Path(path) if path else config_path()
    data = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            data = {}
    return _merge(DEFAULTS, data)


def problem(path=None):
    """Plain words for what is wrong with config.json, or None if it is fine.

    utf-8-sig above reads a file Notepad saved as "UTF-8 with BOM", which used to
    break every read. What is left is a real mistake in the file: a trailing comma,
    a missing bracket, a path typed with single backslashes.
    """
    p = Path(path) if path else config_path()
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return "%s could not be read: %s" % (p, exc)
    try:
        data = json.loads(text)
    except ValueError as exc:
        where = ""
        line = getattr(exc, "lineno", None)
        if line:
            where = "\n  Look at line %d:  %s" % (line, text.splitlines()[line - 1].strip()[:90])
        return ("%s could not be read: %s%s\n"
                "  Fix that line, or run  %s install.py  to write a fresh one."
                % (p, exc.msg if hasattr(exc, "msg") else exc, where, PY))
    if not isinstance(data, dict):
        return "%s could not be read: it must start with { and end with }." % p
    return None


def claude_home(cfg):
    """Where Claude Code keeps its own files (session logs, agents)."""
    if cfg.get("claude_home"):
        return Path(cfg["claude_home"]).expanduser()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def vaults(cfg):
    """The two vaults Jeeves reads, as (key, label, path). Missing ones are skipped."""
    out = []
    if cfg.get("second_brain"):
        out.append(("brain", "Second brain", Path(cfg["second_brain"]).expanduser()))
    if cfg.get("crm_vault"):
        out.append(("crm", "CRM", Path(cfg["crm_vault"]).expanduser()))
    return out


def state_dir():
    """Jeeves's own working files (chat session ids, the running server's number)."""
    env = os.environ.get("JEEVES_STATE")
    d = Path(env).expanduser() if env else ROOT / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write(path, text):
    """Write a file without ever leaving a half-written one behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
