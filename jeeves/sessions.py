# -*- coding: utf-8 -*-
"""sessions.py - what Claude Code has been doing, read from its own log files.

Claude Code writes one file per conversation under `<claude home>/projects/`.
Each line is one event. Assistant lines carry a `usage` block (tokens in, out,
and cached). This is the same record the free `ccusage` tool reads.

Two rules learned the hard way:
- The same reply can be written more than once (one line per content block),
  so lines are counted once per message id + request id, never twice.
- Only files touched in the last few days are opened, and results are kept for
  20 seconds, so a panel refresh never re-reads months of history.
"""

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config as C

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CACHE = {}
_FILE_CACHE = {}


def _cached(key, ttl, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (time.time(), val)
    return val


def clear_cache():
    _CACHE.clear()
    _FILE_CACHE.clear()


def _tier(model):
    m = (model or "").lower()
    for t in ("opus", "sonnet", "haiku", "fable"):
        if t in m:
            return t
    return m or "unknown"


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _is_prompt(d):
    """A line the person typed, as opposed to a tool result fed back in."""
    if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
        return False
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return bool(c.strip()) and not c.lstrip().startswith("<")
    if isinstance(c, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in c) and \
            not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c)
    return False


def parse_file(path):
    """One session file summed up. Cached by size and time so it is read once."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = str(path)
    hit = _FILE_CACHE.get(key)
    if hit and hit[0] == (st.st_size, st.st_mtime):
        return hit[1]
    info = {"id": path.stem, "cwd": "", "title": "", "turns": 0, "first": None,
            "last": None, "usage": []}
    seen = set()
    try:
        fh = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return None
    with fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            t = d.get("type")
            if d.get("cwd") and not info["cwd"]:
                info["cwd"] = d["cwd"]
            if t in ("ai-title", "summary") and not info["title"]:
                info["title"] = d.get("aiTitle") or d.get("summary") or ""
            te = _ts(d.get("timestamp")) if d.get("timestamp") else None
            if te:
                info["first"] = te if info["first"] is None else min(info["first"], te)
                info["last"] = te if info["last"] is None else max(info["last"], te)
            if _is_prompt(d):
                info["turns"] += 1
            if t == "assistant":
                msg = d.get("message") or {}
                u = msg.get("usage")
                # "<synthetic>" is a message Claude Code writes itself (for example
                # "Not logged in"); it used no tokens and is not a model.
                if not u or te is None or msg.get("model") == "<synthetic>":
                    continue
                k = (msg.get("id"), d.get("requestId"))
                if k[0] and k in seen:
                    continue
                seen.add(k)
                info["usage"].append((te, _tier(msg.get("model")),
                                      int(u.get("input_tokens") or 0),
                                      int(u.get("output_tokens") or 0),
                                      int(u.get("cache_creation_input_tokens") or 0),
                                      int(u.get("cache_read_input_tokens") or 0)))
    _FILE_CACHE[key] = ((st.st_size, st.st_mtime), info)
    return info


def _recent_files(cfg, days):
    root = C.claude_home(cfg) / "projects"
    if not root.is_dir():
        return []
    cut = time.time() - days * 86400
    out = []
    for f in root.glob("**/*.jsonl"):
        try:
            if f.stat().st_mtime >= cut:
                out.append(f)
        except OSError:
            continue
    return out


def activity(cfg, days=7, limit=40):
    def build():
        rows = []
        root = C.claude_home(cfg) / "projects"
        for f in _recent_files(cfg, days):
            # Sub-agent logs live one folder deeper; they are counted in tokens,
            # but listed here only as part of the conversation that started them.
            if f.parent.parent != root:
                continue
            info = parse_file(f)
            if not info or not info["last"]:
                continue
            tok = sum(u[2] + u[3] + u[4] + u[5] for u in info["usage"])
            if tok == 0 and not info["title"]:
                continue  # a run that failed before Claude answered: nothing to show
            out_tok = sum(u[3] for u in info["usage"])
            models = sorted({u[1] for u in info["usage"]})
            rows.append({
                "id": info["id"][:8], "title": info["title"][:90],
                "folder": info["cwd"] or f.parent.name,
                "folder_name": Path(info["cwd"]).name if info["cwd"] else f.parent.name,
                "turns": info["turns"], "tokens": tok, "output_tokens": out_tok,
                "models": models,
                "last": datetime.fromtimestamp(info["last"]).strftime("%a %d %b %H:%M"),
                "last_ts": info["last"],
                "minutes": int(((info["last"] or 0) - (info["first"] or 0)) / 60),
            })
        rows.sort(key=lambda r: -r["last_ts"])
        return {"sessions": rows[:limit], "total_sessions": len(rows), "days": days}
    return _cached(("activity", str(C.claude_home(cfg)), days), 20, build)


def _blank():
    return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "total": 0}


def _add(b, u):
    b["input"] += u[2]
    b["output"] += u[3]
    b["cache_write"] += u[4]
    b["cache_read"] += u[5]
    b["total"] += u[2] + u[3] + u[4] + u[5]


def tokens(cfg, now=None):
    def build():
        n = now or datetime.now()
        day_start = n.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        five = n.timestamp() - 5 * 3600
        today, last5 = _blank(), _blank()
        by_model = {}
        sessions_today = 0
        for f in _recent_files(cfg, 2):
            info = parse_file(f)
            if not info:
                continue
            touched = False
            for u in info["usage"]:
                if u[0] >= day_start:
                    _add(today, u)
                    by_model.setdefault(u[1], _blank())
                    _add(by_model[u[1]], u)
                    touched = True
                if u[0] >= five:
                    _add(last5, u)
            sessions_today += 1 if touched else 0
        return {"date": n.strftime("%A %d %B"), "today": today, "last_5_hours": last5,
                "by_model": by_model, "sessions_today": sessions_today,
                "ccusage": ccusage_block(cfg)}
    return _cached(("tokens", str(C.claude_home(cfg))), 20, build)


def ccusage_block(cfg):
    """Your current 5-hour usage window, if the free `ccusage` tool is installed.

    Only a `ccusage` already on your PATH is used. Jeeves never downloads it for
    you, because a panel that quietly installs software is a panel you cannot
    trust. Set "ccusage": "off" in config.json to skip this entirely.
    """
    mode = str(cfg.get("ccusage", "auto")).lower()
    if mode == "off":
        return {"available": False, "reason": "switched off in config.json"}
    exe = shutil.which("ccusage")
    if not exe:
        return {"available": False,
                "reason": "ccusage is not installed. It needs Node.js: npm install -g ccusage"}

    def run():
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = str(C.claude_home(cfg))
        try:
            r = subprocess.run([exe, "blocks", "--active", "--json"], capture_output=True,
                               text=True, timeout=30, env=env, creationflags=NO_WINDOW)
            d = json.loads(r.stdout or "{}")
        except Exception as exc:  # noqa: BLE001 - any failure is reported, not raised
            return {"available": False, "reason": "ccusage did not answer: %s" % exc}
        blocks = d.get("blocks") or []
        if not blocks:
            return {"available": True, "active": False}
        b = blocks[0]
        return {"available": True, "active": True, "start": b.get("startTime"),
                "end": b.get("endTime"), "tokens": b.get("totalTokens"),
                "remaining_minutes": (b.get("projection") or {}).get("remainingMinutes"),
                "models": b.get("models") or []}
    return _cached(("ccusage", str(C.claude_home(cfg))), 60, run)
