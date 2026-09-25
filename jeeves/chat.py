# -*- coding: utf-8 -*-
"""chat.py - every message is answered by your own Claude Code, in your second brain.

Jeeves has no brain of its own. It runs `claude -p` (Claude Code's one-shot
mode) inside your second-brain folder, with your CRM folder added, and streams
the answer back word by word. So it knows every agent, skill and rulebook you
already have, and it costs nothing beyond your Claude subscription.

Choices made on purpose:
- The message goes in on standard input, never on the command line, so quotes,
  new lines and long pastes arrive intact.
- Each chat keeps one Claude Code session id and resumes it, so Jeeves
  remembers the conversation across messages and restarts.
- Read-only unless you say otherwise. The permission mode comes from
  config.json ("dontAsk" by default: anything that would need your approval is
  refused). On its own that is not enough: "dontAsk" still lets Claude use any
  tool you have already allowed in your own Claude Code settings, such as
  running commands or fetching web pages. So unless config.json says
  "allow_actions": true, Jeeves passes --tools Read,Grep,Glob: the 3 tools Chat
  MAY use, and no others.
  This used to be the other way round - a list of tools to block. Measured on
  2026-09-22, naming 7 tools to block still left 25 available, among them
  CronCreate and ScheduleWakeup (book a future run), SendMessage (write to
  another agent), RemoteTrigger (start work elsewhere), PushNotification, Skill,
  Workflow and Task. A block list has to be edited every time Claude Code ships
  a tool; a list of what is allowed does not.
  Two more locks go on with it: the tools that run commands, change files or
  reach the internet also go in as deny rules through --settings, because deny
  rules bind any subagent Chat hands work to, and --strict-mcp-config loads no
  add-on (MCP) servers. Chat can then read and search your 2 vaults, and
  nothing else.
- One run per conversation at a time. A second message while the first is
  still being answered is refused, never run alongside it.
- Stop ends Claude and everything it started (see proc.py): an npm install
  runs Claude as a child of claude.cmd, and ending only the parent left the
  real Claude working.
- A run that fails is never remembered. Saving its conversation number made
  every later message fail with "No conversation found".
- No window ever opens: the process is started with CREATE_NO_WINDOW.
"""

import json
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

from . import config as C
from . import proc as P

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_LOCK = threading.Lock()
_RUNNING = {}      # session key -> the running Claude (or _RESERVED while it starts)
_STOPPED = set()   # session keys whose run the member stopped on purpose
_RESERVED = object()

# The only 3 tools Chat may use unless config.json says "allow_actions": true.
# Read opens a file, Grep searches inside files, Glob finds files by name.
READ_ONLY_TOOLS = ["Read", "Grep", "Glob"]
# The tools that run commands, change files or reach the internet. These go in as
# deny rules, which also bind any subagent Chat hands work to.
READ_ONLY_BLOCK = ["Bash", "PowerShell", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"]
BUSY_TEXT = "Still answering your last message. Wait for it to finish, or press Stop first."

PERSONA = (
    "You are {name}, a personal assistant working through a chat panel in a local web page. "
    "Today is {date}. The person's second brain (an Obsidian vault of their notes) is the "
    "folder you are in: {brain}. {crm_line}"
    "Answer from their own notes whenever you can and name the note you used. "
    "Keep replies short and plain. {power_line}"
)
POWER_READ_ONLY = (
    "In this chat you can read and search files only: running commands, changing files and "
    "using the internet are switched off. If asked for one of those, say so plainly and say what "
    "they could do instead (for example run it themselves in Claude Code).")
POWER_ACTIONS = (
    "If something would change a file or reach another person, say what you would do and wait "
    "for them to agree.")


def read_only(cfg):
    return not cfg.get("allow_actions")


def _sessions_file():
    return C.state_dir() / "chat-sessions.json"


def _load_sessions():
    try:
        return json.loads(_sessions_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_sessions(d):
    C.atomic_write(_sessions_file(), json.dumps(d, indent=1))


def forget(session_key):
    with _LOCK:
        d = _load_sessions()
        d.pop(session_key, None)
        _save_sessions(d)


def resolve_command(cfg):
    """The Claude Code command as a list, or None if it cannot be found."""
    cmd = cfg.get("claude_command") or "claude"
    if isinstance(cmd, list):
        return list(cmd)
    exe = shutil.which(cmd)
    if not exe and cmd == "claude":
        exe = _usual_place()
    if not exe:
        return None
    if exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe]
    return [exe]


def _usual_place():
    """Where Claude Code's installers put it, for a Jeeves started without your PATH
    (a Mac logon job, or a window opened before Claude Code was installed)."""
    h = Path.home()
    names = ["claude.exe", "claude.cmd", "claude"] if os.name == "nt" else ["claude"]
    folders = [h / ".local" / "bin", h / ".claude" / "local",
               Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
    if os.environ.get("APPDATA"):
        folders.append(Path(os.environ["APPDATA"]) / "npm")
    for f in folders:
        for n in names:
            if (f / n).is_file():
                return str(f / n)
    return None


def _read_only_settings():
    """A small settings file of refusals for the acting tools, rewritten only if it changed."""
    f = C.state_dir() / "read-only-settings.json"
    text = json.dumps({"permissions": {"deny": READ_ONLY_BLOCK}}, indent=1)
    try:
        same = f.read_text(encoding="utf-8") == text
    except OSError:
        same = False
    if not same:
        C.atomic_write(f, text)
    return f


def build_args(cfg, model_key, session_key):
    """The full command line, plus the session id and whether it is new."""
    models = cfg.get("models") or {}
    model = (models.get(model_key) or models.get(cfg.get("default_model", "best"))
             or C.DEFAULTS["models"]["best"])
    base = resolve_command(cfg)
    if base is None:
        return None, None, None
    sessions = _load_sessions()
    rec = sessions.get(session_key)
    args = base + ["-p", "--output-format", "stream-json", "--include-partial-messages",
                   "--verbose", "--model", model]
    if cfg.get("permission_mode"):
        args += ["--permission-mode", cfg["permission_mode"]]
    if read_only(cfg):
        # The list of what Chat MAY use. 1 argument, commas between the names, so it
        # can never swallow the flags after it.
        args += ["--tools", ",".join(READ_ONLY_TOOLS)]
        # The acting tools as deny rules in a settings file: Claude Code's documentation
        # says deny rules apply to subagents too, so an agent Chat hands work to is
        # blocked in the same way. No add-on (MCP) servers are loaded either: their
        # tools could send messages or change files elsewhere.
        args += ["--settings", str(_read_only_settings()), "--strict-mcp-config"]
    crm = cfg.get("crm_vault")
    if crm:
        args += ["--add-dir", str(crm)]
    if rec:
        sid = rec["sid"]
        args += ["--resume", sid]
        new = False
    else:
        sid = str(uuid.uuid4())
        persona = PERSONA.format(
            name=cfg.get("name", "Jeeves"), date=datetime.now().strftime("%A %d %B %Y"),
            brain=cfg.get("second_brain") or "(not set)",
            crm_line=("Their CRM is a separate vault at %s. " % crm) if crm else "",
            power_line=POWER_READ_ONLY if read_only(cfg) else POWER_ACTIONS)
        args += ["--session-id", sid, "--append-system-prompt", persona]
        new = True
    return args, sid, new


def _activity(name, inp):
    inp = inp or {}
    for k in ("file_path", "path", "pattern", "command", "query", "url", "description"):
        if inp.get(k):
            return "%s: %s" % (name, str(inp[k])[:120])
    return name or "tool"


def stream(cfg, message, model_key="best", session_key="main"):
    """A generator of events: activity / delta / done / error / stopped."""
    message = (message or "").strip()
    if not message:
        yield {"type": "done", "text": "You did not type anything."}
        return
    with _LOCK:
        busy = session_key in _RUNNING
        if not busy:
            _RUNNING[session_key] = _RESERVED
            _STOPPED.discard(session_key)
    if busy:
        yield {"type": "error", "code": "busy", "text": BUSY_TEXT}
        return
    try:
        yield from _run(cfg, message, model_key, session_key)
    finally:
        with _LOCK:
            _RUNNING.pop(session_key, None)
            _STOPPED.discard(session_key)


def _run(cfg, message, model_key, session_key):
    args, sid, new = build_args(cfg, model_key, session_key)
    if args is None:
        yield {"type": "error", "code": "not_found",
               "text": "Claude Code was not found. Install it, log in once by typing `claude` "
                       "in a terminal, then restart Jeeves. If it is installed somewhere unusual, "
                       "put its full path in config.json as \"claude_command\"."}
        return
    cwd = cfg.get("second_brain") or None
    final, parts, failed = "", [], None
    try:
        proc = subprocess.Popen(
            args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=P.NO_WINDOW, **P.popen_group_kwargs())
    except OSError as exc:
        yield {"type": "error", "code": "start", "text": "Could not start Claude Code: %s" % exc}
        return
    with _LOCK:
        _RUNNING[session_key] = proc
        stopped_early = session_key in _STOPPED
    if stopped_early:
        P.kill_tree(proc.pid)
    # Read the error channel on its own thread, so a chatty error stream can
    # never fill up and freeze the reply stream.
    errbuf = []
    drain = threading.Thread(target=lambda: errbuf.append(proc.stderr.read()), daemon=True)
    drain.start()
    limit = float(cfg.get("chat_timeout_seconds") or 600)
    timed_out = []
    timer = threading.Timer(limit, lambda: (timed_out.append(1), P.kill_tree(proc.pid)))
    timer.start()
    err = ""
    try:
        try:
            proc.stdin.write(message)
            proc.stdin.close()
        except OSError:
            pass
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            t = ev.get("type")
            if t == "stream_event":
                e = ev.get("event") or {}
                d = e.get("delta") or {}
                if e.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                    parts.append(d.get("text", ""))
                    yield {"type": "delta", "text": d.get("text", "")}
            elif t == "assistant":
                for block in (ev.get("message") or {}).get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        yield {"type": "activity",
                               "text": _activity(block.get("name"), block.get("input"))}
            elif t == "result":
                final = (ev.get("result") or "").strip()
                if ev.get("is_error"):
                    failed = final or "Claude Code reported an error."
        proc.wait(timeout=15)
        drain.join(timeout=5)
        err = "".join(x or "" for x in errbuf).strip()
    except Exception as exc:  # noqa: BLE001 - reported to the panel, never swallowed
        failed = failed or ("The reply was cut short: %s" % exc)
    finally:
        timer.cancel()
    with _LOCK:
        stopped = session_key in _STOPPED
    if stopped:
        yield {"type": "stopped", "text": "".join(parts)}
        return
    if timed_out:
        yield {"type": "error", "code": "timeout",
               "text": "No answer after %d minutes, so Jeeves stopped it. Try a smaller question, "
                       "or raise \"chat_timeout_seconds\" in config.json." % round(limit / 60)}
        return
    if failed is None and proc.returncode not in (0, None) and not final:
        failed = err[-600:] or "Claude Code stopped with code %s." % proc.returncode
    if failed is not None:
        low = failed.lower()
        if "no conversation found" in low:
            forget(session_key)   # Claude no longer has it: start fresh next time
            code = "lost"
        elif "log in" in low or "login" in low or "not logged" in low:
            code = "login"
        else:
            code = "failed"
        yield {"type": "error", "code": code, "text": failed}
        return
    with _LOCK:
        d = _load_sessions()
        d[session_key] = {"sid": sid, "updated": datetime.now().isoformat(timespec="seconds")}
        _save_sessions(d)
    yield {"type": "done", "text": final or "".join(parts)}


def stop(session_key="main"):
    """Stop the run for this conversation and everything Claude started. True if one was running."""
    with _LOCK:
        p = _RUNNING.get(session_key)
        if p is None:
            return False
        _STOPPED.add(session_key)
    if p is _RESERVED:
        return True          # _run sees the flag as soon as Claude has started, and ends it
    if p.poll() is None:
        P.kill_tree(p.pid)
        return True
    return False


def last_updated(session_key="main"):
    """When this conversation last got an answer, or None if there is none to carry on."""
    rec = _load_sessions().get(session_key)
    return rec.get("updated") if rec else None
