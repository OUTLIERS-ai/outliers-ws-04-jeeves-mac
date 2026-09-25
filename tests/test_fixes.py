# -*- coding: utf-8 -*-
"""Faults found on 2026-09-22 by a cold walk-through, a usability audit and a security
audit. Each test was written to FAIL on the old code first, then the fix made it pass.
No AI is called: Claude Code is played by tools/fake_claude.py.
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import ROOT, events, get_json, post

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _log(tmp_path, monkeypatch):
    p = tmp_path / "fake-claude-calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(p))
    return p


def _calls(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------- chat is read-only

READ_ONLY_BLOCK = {"Bash", "PowerShell", "Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"}


def _blocked(argv):
    if "--disallowedTools" not in argv:
        return set()
    return set(argv[argv.index("--disallowedTools") + 1].replace(",", " ").split())


def _allowed(argv):
    if "--tools" not in argv:
        return None
    return set(argv[argv.index("--tools") + 1].replace(",", " ").split())


def test_chat_is_given_only_the_3_reading_tools(server, tmp_path, monkeypatch):
    """Security audit row 1 and the re-audit of 2026-09-22: naming the tools to block
    left 25 others available (CronCreate, ScheduleWakeup, SendMessage, Skill, Task and
    more). Chat is now given a list of what it MAY use: Read, Grep, Glob."""
    log = _log(tmp_path, monkeypatch)
    post(server[0] + "/api/chat", {"message": "hi"})
    a = _calls(log)[0]["argv"]
    assert _allowed(a) == {"Read", "Grep", "Glob"}
    # the value is 1 argument, so it can never swallow the flags after it
    assert a[a.index("--tools") + 1].count(" ") == 0
    # the same rules as deny rules, which Claude Code applies to subagents as well
    rules = json.loads(Path(a[a.index("--settings") + 1]).read_text(encoding="utf-8"))
    assert READ_ONLY_BLOCK <= set(rules["permissions"]["deny"])
    assert "--strict-mcp-config" in a          # no add-on servers that could act elsewhere


def test_allow_actions_in_config_lifts_the_block(server, tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)
    cfg = json.loads(server[1].read_text(encoding="utf-8"))
    cfg["allow_actions"] = True
    server[1].write_text(json.dumps(cfg), encoding="utf-8")
    post(server[0] + "/api/chat", {"message": "hi"})
    a = _calls(log)[0]["argv"]
    assert _allowed(a) is None and _blocked(a) == set()
    assert "--settings" not in a and "--strict-mcp-config" not in a


def test_public_config_says_whether_chat_is_read_only(server):
    assert get_json(server[0] + "/api/config")["read_only"] is True


# ---------------------------------------------------------------- failed runs

def test_login_error_is_shown_once_and_its_conversation_is_not_saved(server, tmp_path, monkeypatch):
    """Walk stuck point 2: after 'Not logged in', every later message failed with
    'No conversation found with session ID', because the failed run's id was saved."""
    log = _log(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_RESULT_ERROR", "Not logged in · Please run /login")
    ev = events(post(server[0] + "/api/chat", {"message": "x"})[1])
    texts = [e.get("text", "") for e in ev]
    assert sum("Not logged in" in t for t in texts) == 1, ev   # once, not twice
    assert ev[-1]["type"] == "error"
    monkeypatch.delenv("FAKE_CLAUDE_RESULT_ERROR")
    post(server[0] + "/api/chat", {"message": "y"})
    assert "--session-id" in _calls(log)[1]["argv"], "the failed conversation must not be resumed"


def test_a_conversation_claude_cannot_find_is_forgotten(server, tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)
    post(server[0] + "/api/chat", {"message": "one"})                 # saved
    monkeypatch.setenv("FAKE_CLAUDE_RESULT_ERROR", "No conversation found with session ID: abc")
    post(server[0] + "/api/chat", {"message": "two"})                 # resume fails
    monkeypatch.delenv("FAKE_CLAUDE_RESULT_ERROR")
    post(server[0] + "/api/chat", {"message": "three"})
    assert "--resume" in _calls(log)[1]["argv"]
    assert "--session-id" in _calls(log)[2]["argv"], "a lost conversation must start fresh"


# ---------------------------------------------------------------- 1 run at a time

def test_a_second_message_while_answering_is_refused(server, tmp_path, monkeypatch):
    """Critic finding 2: Enter sent a 2nd message mid-answer; 2 runs, 1 conversation lost."""
    log = _log(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_DELAY", "0.05")
    first = {}
    t = threading.Thread(target=lambda: first.update(r=post(server[0] + "/api/chat", {"message": "slow"})))
    t.start()
    deadline = time.time() + 10
    while time.time() < deadline and not (log.exists() and log.read_text(encoding="utf-8")):
        time.sleep(0.05)
    ev = events(post(server[0] + "/api/chat", {"message": "impatient"})[1])
    t.join(30)
    assert ev and ev[-1]["type"] == "error" and "Still answering" in ev[-1]["text"]
    assert len(_calls(log)) == 1, "the second message must never start Claude"
    assert events(first["r"][1])[-1]["type"] == "done"


# ---------------------------------------------------------------- Stop

def _alive(pid):
    from jeeves import proc
    return proc.alive(pid)


def test_stop_ends_claude_started_through_a_cmd_file(server, tmp_path, monkeypatch):
    """Security audit row 2: npm's claude.cmd runs the real Claude as a child; Stop ended
    only the parent and Claude kept working for up to 10 minutes."""
    pidfile = tmp_path / "child.pid"
    monkeypatch.setenv("FAKE_CLAUDE_CHILD", str(pidfile))
    out = {}
    t = threading.Thread(target=lambda: out.update(r=post(server[0] + "/api/chat", {"message": "go"})))
    t.start()
    deadline = time.time() + 15
    while time.time() < deadline and not (pidfile.exists() and pidfile.read_text()):
        time.sleep(0.05)
    child = int(pidfile.read_text())
    assert _alive(child)
    assert json.loads(post(server[0] + "/api/chat/stop", {})[1])["stopped"] is True
    deadline = time.time() + 8
    while time.time() < deadline and _alive(child):
        time.sleep(0.1)
    t.join(20)
    assert not _alive(child), "Claude's own process was still working after Stop"
    ev = events(out["r"][1])
    assert ev[-1]["type"] == "stopped", ev          # grey "Stopped", not a red crash
    assert not any(e["type"] == "error" for e in ev)


# ---------------------------------------------------------------- 1 copy per port

def test_a_second_copy_cannot_share_the_port(world):
    """Walk stuck point 1: on Windows 2 copies both listened on 4040."""
    from jeeves.server import make_server
    port = _free_port()
    a = make_server(port, str(world))
    try:
        with pytest.raises(OSError):
            make_server(port, str(world))
    finally:
        a.server_close()


def test_health_names_jeeves_and_its_process(server):
    h = get_json(server[0] + "/api/health")
    assert h["ok"] is True and h["app"] == "jeeves" and h["pid"] == os.getpid()


def test_start_says_jeeves_is_already_running(server, capsys):
    import start
    port = int(server[0].rsplit(":", 1)[1])
    rc = start.main(["--port", str(port), "--no-open", "--config", str(server[1])])
    assert rc == 0
    assert "already running" in capsys.readouterr().out


# ---------------------------------------------------------------- the checks stay in their own folder

def test_the_checks_read_a_config_inside_the_temporary_folder_only(tmp_path):
    """Acceptance test 2026-09-23, fault 1. The guide says these checks "never touch your
    real files". They did: with no JEEVES_CONFIG set, config.load() falls back to the
    config.json next to start.py -- the member's own -- so a check could read their real
    port and end the Jeeves they had open in a browser tab."""
    from jeeves import config as C
    p = C.config_path()
    assert p != C.ROOT / "config.json", \
        "the checks are reading the config.json next to start.py, which is the member's own"
    assert tmp_path in p.parents, \
        "the checks are reading %s, which is outside this check's temporary folder" % p


def test_no_check_stops_jeeves_without_naming_its_own_config():
    """Acceptance test 2026-09-23, fault 1. Stopping Jeeves without naming a config file
    loads the member's real config.json, finds the Jeeves running on their real port and
    ends it, mid-session, with no message. Every stop in these checks must name the config
    file that check wrote."""
    needle = "start." + "stop()"                  # built here so this line is not a match
    bad = []
    for f in sorted((ROOT / "tests").glob("test_*.py")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line:
                bad.append("%s line %d" % (f.name, n))
    assert not bad, ("these checks stop Jeeves without naming their own config, so they end "
                     "the member's running copy: " + ", ".join(bad))


# ---------------------------------------------------------------- --stop and stale numbers

def test_stop_never_kills_an_unrelated_program(tmp_path, capsys, world):
    """Security audit row 3: a stale jeeves.pid made --stop kill whatever now had that number."""
    import start
    from jeeves import config as C
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 creationflags=NO_WINDOW)
    try:
        C.atomic_write(start.pid_file(), "%d %d\n" % (bystander.pid, _free_port()))
        start.stop(str(world))
        time.sleep(0.5)
        assert bystander.poll() is None, "an unrelated program was killed"
        assert not start.pid_file().exists()
    finally:
        bystander.kill()


def test_stop_stops_a_real_jeeves(world, tmp_path):
    import start
    port = _free_port()
    env = dict(os.environ)
    p = subprocess.Popen([sys.executable, str(ROOT / "start.py"), "--no-open", "--port", str(port),
                          "--config", str(world)], env=env, creationflags=NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        start.stop(str(world))
        p.wait(10)
        assert p.returncode is not None
    finally:
        if p.poll() is None:
            p.kill()


# ---------------------------------------------------------------- [[links]] in either vault

def test_a_link_name_is_found_in_whichever_vault_has_it(server):
    """Critic finding 3: a [[link]] clicked while the CRM tab showed looked in the wrong vault."""
    base = server[0]
    assert get_json(base + "/api/vault/resolve?name=Pricing%20review") == \
        {"key": "brain", "path": "Projects/Pricing review.md"}
    assert get_json(base + "/api/vault/resolve?name=Marcus%20Webb") == \
        {"key": "crm", "path": "People/Marcus Webb.md"}
    assert get_json(base + "/api/vault/resolve?name=Nobody%20Here") == {"key": None, "path": None}


# ---------------------------------------------------------------- installer

def test_installer_asks_again_when_the_port_is_not_a_number(world, tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("JEEVES_CONFIG", str(tmp_path / "o" / "config.json"))
    import install
    importlib.reload(install)
    w = json.loads(world.read_text(encoding="utf-8"))
    answers = iter([w["second_brain"], "", "", "forty", "4556", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert install.main(["--skip-claude-check"]) == 0
    assert json.loads((tmp_path / "o" / "config.json").read_text(encoding="utf-8"))["port"] == 4556


def test_mac_logon_file_gives_claude_a_path(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("JEEVES_CONFIG", str(tmp_path / "config.json"))
    import install
    importlib.reload(install)
    text = install.plist_text()
    assert "<key>EnvironmentVariables</key>" in text and "<key>PATH</key>" in text
    assert "/opt/homebrew/bin" in text and ".local/bin" in text


def test_claude_is_found_in_its_usual_folder_when_not_on_path(tmp_path, monkeypatch):
    from jeeves import chat
    bindir = tmp_path / "fakehome" / ".local" / "bin"
    bindir.mkdir(parents=True)
    exe = bindir / ("claude.exe" if os.name == "nt" else "claude")
    exe.write_text("")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    got = chat.resolve_command({"claude_command": "claude"})
    assert got and Path(got[-1]) == exe


def test_a_person_from_the_crm_list_opens_their_crm_note(server):
    base = server[0]
    # Priya Shah has a note in both vaults; from the CRM's list the CRM note is wanted
    assert get_json(base + "/api/vault/resolve?name=Priya%20Shah")["key"] == "brain"
    assert get_json(base + "/api/vault/resolve?name=Priya%20Shah&prefer=crm") == \
        {"key": "crm", "path": "People/Priya Shah.md"}


def test_a_failed_login_run_adds_no_odd_rows(server):
    """Walk: after a failed login, Activity showed '(untitled)' and Tokens a '<synthetic> 0' model."""
    from datetime import datetime, timezone
    from jeeves import sessions
    cfg = json.loads(server[1].read_text(encoding="utf-8"))
    folder = Path(cfg["claude_home"]) / "projects" / "failed-run"
    folder.mkdir(parents=True)
    ts = datetime.now(timezone.utc).isoformat()
    lines = [{"type": "user", "cwd": cfg["second_brain"], "timestamp": ts,
              "message": {"role": "user", "content": "hello"}},
             {"type": "assistant", "timestamp": ts, "message": {
                 "id": "m1", "model": "<synthetic>", "content": [{"type": "text", "text": "Not logged in"}],
                 "usage": {"input_tokens": 0, "output_tokens": 0}}}]
    (folder / "abc.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    sessions.clear_cache()
    assert "<synthetic>" not in get_json(server[0] + "/api/tokens")["by_model"]
    assert all(s["id"] != "abc" for s in get_json(server[0] + "/api/activity")["sessions"])


# =================================================================== second audit
# Faults found on 2026-09-22 by the second usability teardown, the engine
# reliability run and the "is it still current" check. Each test below was
# written to FAIL on the code as published that morning.

def test_every_model_is_named_in_full_so_the_price_table_can_match(server):
    """Still-current audit, must-fix 2: the default model was the word "opus", which on
    2026-09-22 started resolving to Claude Opus 5.5. FleetView prices a model by its full
    name, so Jeeves and FleetView disagreed about what a member was running."""
    from jeeves import config as C
    assert C.DEFAULTS["models"] == {"best": "claude-opus-5-5", "deep": "claude-sonnet-5",
                                    "fast": "claude-haiku-4-5"}
    for name in get_json(server[0] + "/api/config")["models"].values():
        assert name.startswith("claude-"), "%r is an alias, not a model name" % name


def test_the_installer_writes_the_same_models_as_the_settings_file(tmp_path, monkeypatch):
    import importlib
    from jeeves import config as C
    monkeypatch.setenv("JEEVES_CONFIG", str(tmp_path / "config.json"))
    import install
    importlib.reload(install)
    assert install.MODELS == C.DEFAULTS["models"]


def test_today_says_which_second_brain_folder_is_missing(world):
    """Re-audit N1: with the second-brain folder gone, Today said "Nothing has moved and
    nothing is left open" while Vaults said the folder does not exist."""
    from jeeves import config as C, vaults
    cfg = C.load(str(world))
    cfg["second_brain"] = str(Path(cfg["second_brain"]).parent / "not-here")
    d = vaults.today(cfg)
    assert d["brain"]["found"] is False
    assert d["brain"]["path"] == cfg["second_brain"], "the panel needs the folder to name it"


def test_the_crm_half_says_the_folder_is_missing_too(world):
    from jeeves import config as C, vaults
    cfg = C.load(str(world))
    cfg["crm_vault"] = str(Path(cfg["crm_vault"]).parent / "no-crm")
    crm = vaults.today(cfg)["crm"]
    assert crm["found"] is False and crm["exists"] is False
    assert "does not exist" in crm["hint"] and cfg["crm_vault"] in crm["hint"]


def test_the_tests_own_world_never_asks_a_port_a_member_might_be_running(world):
    """Re-audit N5: the shipped tests asserted nothing was listening on port 3020. Anyone
    running ProjectForge (piece 3, out the same day) got 1 failed, 51 passed."""
    apps = json.loads(world.read_text(encoding="utf-8"))["apps"]
    for name, a in apps.items():
        assert ":1/" in a["url"] or a["url"].endswith(":1"), \
            "%s points at %s, which something on this computer could answer" % (name, a["url"])


def test_the_port_advice_names_a_free_port_not_the_one_that_just_failed(world, capsys):
    """Reliability fault J1: the advice was the fixed text --port 4041, so a member already
    on 4041 was told to try the port that had just refused them. Two blocked ports must
    now produce two different pieces of advice, each of them free."""
    import start
    suggestions = []
    for _ in range(2):
        taken = socket.socket()
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        port = taken.getsockname()[1]
        try:
            rc = start.main(["--port", str(port), "--no-open", "--config", str(world)])
            out = capsys.readouterr().out
        finally:
            taken.close()
        assert rc == 1
        suggested = int(out.split("--port")[-1].strip().split()[0])
        assert suggested != port, "it named the port that had just refused"
        free = socket.socket()
        try:
            free.bind(("127.0.0.1", suggested))     # the port it names must really be free
        finally:
            free.close()
        suggestions.append(suggested)
    assert suggestions[0] != suggestions[1], "the advice is fixed text, not a free port"


def test_a_broken_config_file_is_named_as_broken(tmp_path, capsys):
    """Reliability fault J2: a trailing comma in config.json was reported as
    "No config.json yet. Run: python install.py"."""
    import start
    bad = tmp_path / "config.json"
    bad.write_text('{\n "name": "Jeeves",\n "port": 4040,\n}\n', encoding="utf-8")
    rc = start.main(["--config", str(bad), "--no-open"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "No config.json yet" not in out
    assert "could not be read" in out and "line 3" in out and str(bad) in out


def test_a_config_saved_with_a_byte_order_mark_still_reads(tmp_path):
    from jeeves import config as C
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"name": "Bertie"}), encoding="utf-8-sig")
    assert C.load(str(p))["name"] == "Bertie"
    assert C.problem(p) is None


def test_an_agent_saved_with_a_byte_order_mark_still_shows_what_it_is_for(tmp_path):
    """Acceptance test 2026-09-23, fault 9. Notepad, and PowerShell's
    `Out-File -Encoding utf8`, put an invisible mark at the start of the file. The Agents
    panel then showed a name and nothing else: no description, no model tag. The guide
    promises the card says what each agent is for and which model it uses."""
    from jeeves import agents as A
    folder = tmp_path / "agents"
    folder.mkdir()
    (folder / "ledger-agent.md").write_text(
        "---\nname: ledger-agent\n"
        "description: Tidies bookkeeping notes and flags unreconciled months.\n"
        "model: haiku\n---\n\nBody.\n", encoding="utf-8-sig")
    rows = A.listing({"agents_dirs": [str(folder)], "claude_home": str(tmp_path / "none")})["agents"]
    card = [r for r in rows if r["file"] == "ledger-agent.md"][0]
    assert card["name"] == "ledger-agent"
    assert card["description"] == "Tidies bookkeeping notes and flags unreconciled months."
    assert card["model"] == "haiku"


def test_the_installer_refuses_a_python_older_than_3_11(tmp_path, monkeypatch):
    """Still-current audit, must-fix 4: the installer let Python 3.8 through. 3.8 stopped
    getting security fixes on 2024-10-07 and 3.9 on 2025-10-31."""
    import importlib
    monkeypatch.setenv("JEEVES_CONFIG", str(tmp_path / "config.json"))
    import install
    importlib.reload(install)
    assert install.MIN_PY == (3, 11)
    assert install.too_old((3, 10, 18)) is True
    assert install.too_old((3, 11, 0)) is False
    assert "3.11" in install.__doc__ and "3.8" not in install.__doc__
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Python 3.11 or newer" in readme
