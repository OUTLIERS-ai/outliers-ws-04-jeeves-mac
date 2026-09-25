# -*- coding: utf-8 -*-
"""agents.py - the Claude Code agents you have, read from their instruction files.

An agent is a markdown file with a short header (between two `---` lines) that
gives its name, a description and optionally a model and a list of tools.
Jeeves reads the header only; it never runs or edits an agent from this panel.
"""

from pathlib import Path

from . import config as C


def _front(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out, key = {}, None
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        if line[:1] in " \t" and key:
            out[key] = (out[key] + " " + line.strip()).strip()
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val in (">", "|", ">-", "|-"):
                val = ""
            out[key] = val.strip("\"'")
    return out


def folders(cfg):
    """Every folder agents may live in: your own list, the user-wide one, each vault's."""
    seen, out = set(), []
    cands = [(Path(d).expanduser(), "your folder") for d in (cfg.get("agents_dirs") or [])]
    cands.append((C.claude_home(cfg) / "agents", "all projects"))
    for key, label, p in C.vaults(cfg):
        cands.append((p / ".claude" / "agents", label))
    for p, label in cands:
        k = str(p.resolve()) if p.exists() else str(p)
        if k in seen:
            continue
        seen.add(k)
        out.append((p, label))
    return out


def listing(cfg):
    rows, looked = [], []
    for folder, label in folders(cfg):
        looked.append({"path": str(folder), "label": label, "exists": folder.is_dir()})
        if not folder.is_dir():
            continue
        for f in sorted(folder.glob("*.md")):
            try:
                # utf-8-sig drops the invisible mark Notepad and PowerShell's
                # `Out-File -Encoding utf8` put at the start of a file. Without it the
                # first line reads as "<mark>---", the header is never found, and the
                # card shows a name with no description and no model tag.
                fm = _front(f.read_text(encoding="utf-8-sig", errors="replace")[:20000])
            except OSError:
                continue
            rows.append({
                "name": fm.get("name") or f.stem,
                "description": fm.get("description", "")[:1200],
                "model": fm.get("model", ""),
                "tools": fm.get("tools", ""),
                "where": label,
                "file": f.name,
            })
    rows.sort(key=lambda r: r["name"].lower())
    return {"agents": rows, "folders": looked}
