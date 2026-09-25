# -*- coding: utf-8 -*-
"""vaults.py - read-only views of your second brain and your CRM.

Nothing in this file writes to a vault. Every path a browser asks for is
checked to be inside the vault it names, so a crafted address such as
`../../secret.txt` is refused rather than served.
"""

import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import config as C

SKIP_PARTS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__",
              "_engine", "_layers", "_state", ".claude"}
MAX_FILES = 4000
MAX_BYTES = 400_000


def refused(root):
    """macOS's refusal of a folder, in words, or "" (Mac only).

    A program that starts by itself on a Mac (Jeeves' start-up file) may be refused the
    Documents folder with "Operation not permitted". Python then reads the folder as not
    there, so the page said the vault was missing when it was where it should be."""
    if sys.platform != "darwin":
        return ""
    try:
        os.listdir(root)
    except PermissionError:
        return ("macOS refused access to %s. Jeeves cannot read it, so nothing below is a real "
                "answer. A program that starts by itself may be refused the Documents folder: move "
                "the folder out of Documents, for example to %s, and put its new place in "
                "config.json." % (root, Path.home() / Path(root).name))
    except OSError:
        return ""
    return ""


def _vault_map(cfg):
    return {k: (label, p) for k, label, p in C.vaults(cfg)}


def listing(cfg):
    out = []
    for key, label, p in C.vaults(cfg):
        no = refused(p)
        out.append({"key": key, "label": label, "path": str(p), "exists": False if no else p.is_dir(),
                    "refused": no})
    return out


def _md_files(root):
    n = 0
    for p in root.rglob("*.md"):
        rel = p.relative_to(root)
        if set(rel.parts[:-1]) & SKIP_PARTS:
            continue
        yield p, rel
        n += 1
        if n >= MAX_FILES:
            return


def tree(cfg, key):
    vm = _vault_map(cfg)
    if key not in vm:
        return {"error": "unknown vault"}
    label, root = vm[key]
    no = refused(root)
    if no or not root.is_dir():
        return {"key": key, "label": label, "exists": False, "files": [], "refused": no}
    files = []
    for p, rel in _md_files(root):
        try:
            st = p.stat()
        except OSError:
            continue
        files.append({"path": rel.as_posix(), "mtime": int(st.st_mtime), "size": st.st_size})
    files.sort(key=lambda f: f["path"].lower())
    return {"key": key, "label": label, "exists": True, "files": files}


def resolve(cfg, name, prefer=None):
    """Which vault the note a [[link]] names is in: the second brain first, then the CRM.

    A link is a note name ("Tom Reyes"), sometimes with a folder ("People/Tom Reyes")
    or a heading ("Tom Reyes#Calls"). Returns {"key", "path"}, both None if no vault has it.
    """
    n = (name or "").split("#")[0].split("|")[0].strip().replace("\\", "/").lower()
    if n.endswith(".md"):
        n = n[:-3]
    if not n:
        return {"key": None, "path": None}
    # prefer="crm" looks in the CRM first: a person picked from the CRM's own list.
    order = sorted(C.vaults(cfg), key=lambda v: v[0] != prefer)
    for key, _label, root in order:
        if not root.is_dir():
            continue
        best = None
        for _p, rel in _md_files(root):
            r = rel.as_posix()
            low = r.lower()[:-3]
            if low == n:
                return {"key": key, "path": r}
            if best is None and (low.endswith("/" + n) or low.rsplit("/", 1)[-1] == n):
                best = r
        if best:
            return {"key": key, "path": best}
    return {"key": None, "path": None}


def safe_path(root, rel):
    """The file `rel` inside `root`, or None if it would escape the vault."""
    try:
        root_r = root.resolve()
        target = (root_r / rel).resolve()
    except (OSError, ValueError):
        return None
    if target != root_r and root_r not in target.parents:
        return None
    return target


def read(cfg, key, rel):
    vm = _vault_map(cfg)
    if key not in vm:
        return {"error": "unknown vault"}
    _, root = vm[key]
    if not rel or not rel.lower().endswith(".md"):
        return {"error": "only markdown notes can be opened here"}
    target = safe_path(root, rel)
    if target is None:
        return {"error": "that path is outside the vault"}
    if not target.is_file():
        return {"error": "no such note"}
    data = target.read_bytes()[:MAX_BYTES]
    return {"key": key, "path": rel, "text": data.decode("utf-8", errors="replace"),
            "mtime": int(target.stat().st_mtime)}


def search(cfg, q, limit=60):
    q = (q or "").strip()
    if len(q) < 2:
        return {"q": q, "hits": []}
    pat = re.compile(re.escape(q), re.I)
    hits = []
    for key, label, root in C.vaults(cfg):
        if not root.is_dir():
            continue
        for p, rel in _md_files(root):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = pat.search(text)
            if not m and not pat.search(rel.as_posix()):
                continue
            snippet = ""
            if m:
                s = max(0, m.start() - 60)
                snippet = text[s:m.end() + 80].replace("\n", " ")
            hits.append({"key": key, "label": label, "path": rel.as_posix(), "snippet": snippet})
            if len(hits) >= limit:
                return {"q": q, "hits": hits}
    return {"q": q, "hits": hits}


# ---------------------------------------------------------------- Today

def _daily_note(cfg, root, day):
    names = [day.strftime("%Y-%m-%d") + ".md", day.strftime("%Y-%m-%d") + " daily.md"]
    folders = [""] + list(cfg.get("daily_note_folders") or [])
    for f in folders:
        for n in names:
            p = root / f / n if f else root / n
            if p.is_file():
                return p
    return None


def _moved(root, days=3, limit=8):
    cut = (datetime.now() - timedelta(days=days)).timestamp()
    out = []
    for p, rel in _md_files(root):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > cut:
            out.append((m, rel.as_posix()))
    out.sort(reverse=True)
    return [{"path": r, "when": datetime.fromtimestamp(m).strftime("%a %H:%M")}
            for m, r in out[:limit]]


_TODO = re.compile(r"^\s*[-*]\s*\[ \]\s*(.+)$", re.M)


def _open_items(root, limit=10):
    out = []
    for p, rel in _md_files(root):
        try:
            s = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _TODO.finditer(s):
            out.append({"text": m.group(1).strip()[:140], "path": rel.as_posix()})
            if len(out) >= limit:
                return out
    return out


def today(cfg, now=None):
    """What the day looks like: the CRM's ranked page and the second brain's day."""
    now = now or datetime.now()
    vm = _vault_map(cfg)
    out = {"date": now.strftime("%A %d %B %Y"), "crm": None, "brain": None}

    # Every half says which folder it looked in and whether that folder is there.
    # Without it the panel said "Nothing has moved and nothing is left open" for a
    # folder that did not exist, while the Vaults panel on the same screen said so.
    if "crm" in vm:
        root = vm["crm"][1]
        page = root / "Today.md"
        no = refused(root)
        if no:
            out["crm"] = {"found": False, "exists": False, "vault": str(root), "refused": no, "hint": no}
        elif page.is_file():
            out["crm"] = {"found": True, "exists": True, "vault": str(root), "path": "Today.md",
                          "text": page.read_text(encoding="utf-8", errors="replace")[:MAX_BYTES],
                          "built": datetime.fromtimestamp(page.stat().st_mtime).strftime("%a %d %b %H:%M")}
        elif not root.is_dir():
            out["crm"] = {"found": False, "exists": False, "vault": str(root),
                          "hint": "Your CRM folder does not exist: %s . Check \"crm_vault\" "
                                  "in config.json." % root}
        elif sys.platform == "darwin" and not (root / "_engine" / "today.py").is_file():
            # A CRM from the first CRM sessions has no program that writes Today.md; it comes with
            # part 7. Telling the member to run it only gives them an error (wave 6, 2026-09-25).
            out["crm"] = {"found": False, "exists": True, "vault": str(root), "no_today_tool": True,
                          "hint": "No Today.md yet. Your CRM gets its Today list in part 7 of the CRM "
                                  "sessions, which adds the program that writes it."}
        else:
            out["crm"] = {"found": False, "exists": True, "vault": str(root),
                          "hint": "No Today.md yet. In your CRM folder run: %s _engine/today.py --write"
                                  % ("python3" if sys.platform == "darwin" else "python")}

    if "brain" in vm:
        root = vm["brain"][1]
        no = refused(root)
        b = {"found": False if no else root.is_dir(), "path": str(root), "daily": None, "moved": [],
             "open": [], "refused": no}
        if b["found"]:
            dn = _daily_note(cfg, root, now)
            if dn:
                b["daily"] = {"path": dn.relative_to(root).as_posix(),
                              "text": dn.read_text(encoding="utf-8", errors="replace")[:MAX_BYTES]}
            b["moved"] = _moved(root)
            b["open"] = _open_items(root)
        out["brain"] = b
    return out


# ---------------------------------------------------------------- Inbox

INBOX_CANDIDATES = ["Inbox/Recommendations.md", "Recommendations.md",
                    "Areas/Recommendations.md", "AI/Recommendations.md", "Inbox.md"]


def inbox(cfg):
    vm = _vault_map(cfg)
    if "brain" not in vm:
        return {"found": False, "hint": "No second brain is set in config.json."}
    root = vm["brain"][1]
    wanted = [cfg["inbox_file"]] if cfg.get("inbox_file") else INBOX_CANDIDATES
    for rel in wanted:
        p = safe_path(root, rel)
        if p and p.is_file():
            return {"found": True, "path": rel,
                    "text": p.read_text(encoding="utf-8", errors="replace")[:MAX_BYTES]}
    return {"found": False, "looked_for": wanted,
            "hint": "Create %s in your second brain and anything you or your agents write "
                    "there appears here." % wanted[0]}
