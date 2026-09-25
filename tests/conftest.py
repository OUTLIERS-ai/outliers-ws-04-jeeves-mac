# -*- coding: utf-8 -*-
"""Every test runs against a made-up world in a temporary folder.

No test reads or writes your real home folder, your real ~/.claude, your
vaults, your Startup folder or your scheduled tasks: HOME, USERPROFILE,
APPDATA and CLAUDE_CONFIG_DIR all point into the temporary folder first.
"""
import json
import sys
from datetime import datetime
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import demo  # noqa: E402
from jeeves import sessions  # noqa: E402
from jeeves.server import serve_in_thread  # noqa: E402


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    h = tmp_path / "fakehome"
    h.mkdir()
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(h))
    monkeypatch.setenv("APPDATA", str(h / "AppData" / "Roaming"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(h / ".claude"))
    monkeypatch.setenv("JEEVES_STATE", str(tmp_path / "state"))
    # A made-up config.json inside the temporary folder. Without this, any check that
    # forgot to name its own config fell back to the config.json next to start.py -- the
    # member's real one -- and could read their real port. On 2026-09-23 that ended the
    # Jeeves a member had open in a browser tab, halfway through `python -m pytest -q`.
    # Port 1 is reserved, so nothing on the computer can answer on it.
    stand_in = h / "config.json"
    stand_in.write_text(json.dumps({"name": "Jeeves", "port": 1}), encoding="utf-8")
    monkeypatch.setenv("JEEVES_CONFIG", str(stand_in))
    sessions.clear_cache()
    return h


@pytest.fixture
def world(tmp_path):
    # Noon today, so the "today" totals do not depend on when the tests are run.
    noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    cfg_path = demo.build(tmp_path / "world", now=noon)
    # The demo keeps the real addresses (3020 and 3010) so the guide's pictures are
    # honest. The TESTS must not: a member who had also installed ProjectForge, which
    # listens on 3020, got "1 failed, 51 passed" and thought they had broken Jeeves.
    # Port 1 is reserved and nothing on a member's computer can answer on it.
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    for name, app in cfg["apps"].items():
        app["url"] = "http://127.0.0.1:1"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg_path


@pytest.fixture
def server(world):
    srv = serve_in_thread(0, str(world))
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    yield base, world
    srv.shutdown()
    srv.server_close()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read().decode("utf-8")


def get_json(url):
    return json.loads(get(url)[1])


def post(url, body, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def events(sse_text):
    return [json.loads(chunk[6:]) for chunk in sse_text.split("\n\n") if chunk.startswith("data: ")]
