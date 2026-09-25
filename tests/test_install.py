# -*- coding: utf-8 -*-
"""install.py against a temporary home: asks, writes one file, twice changes nothing."""
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_install(monkeypatch, cfg_path, *args):
    monkeypatch.setenv("JEEVES_CONFIG", str(cfg_path))
    import importlib
    import install
    importlib.reload(install)          # re-reads JEEVES_CONFIG
    return install.main(list(args) + ["--yes", "--skip-claude-check"]), install


def test_installs_then_changes_nothing_the_second_time(world, tmp_path, monkeypatch, capsys):
    w = json.loads(world.read_text(encoding="utf-8"))
    cfg = tmp_path / "out" / "config.json"
    rc, inst = run_install(monkeypatch, cfg, "--vault", w["second_brain"], "--crm", w["crm_vault"],
                           "--port", "4555")
    assert rc == 0 and cfg.exists()
    got = json.loads(cfg.read_text(encoding="utf-8"))
    assert got["second_brain"] == str(Path(w["second_brain"]).resolve())
    assert got["port"] == 4555 and got["permission_mode"] == "dontAsk"
    assert got["models"] == {"best": "claude-opus-5-5", "deep": "claude-sonnet-5",
                             "fast": "claude-haiku-4-5"}
    before = cfg.read_bytes()
    capsys.readouterr()
    rc, _ = run_install(monkeypatch, cfg, "--vault", w["second_brain"], "--crm", w["crm_vault"],
                        "--port", "4555")
    assert rc == 0 and cfg.read_bytes() == before
    assert "Nothing changed" in capsys.readouterr().out
    assert not list(cfg.parent.glob("config.json.bak-*"))


def test_keeps_your_own_settings_and_backs_up_before_a_change(world, tmp_path, monkeypatch):
    w = json.loads(world.read_text(encoding="utf-8"))
    cfg = tmp_path / "out" / "config.json"
    run_install(monkeypatch, cfg, "--vault", w["second_brain"], "--crm", "")
    d = json.loads(cfg.read_text(encoding="utf-8"))
    d["models"]["best"] = "my-own-model"
    cfg.write_text(json.dumps(d), encoding="utf-8")
    run_install(monkeypatch, cfg, "--vault", w["second_brain"], "--crm", w["crm_vault"])
    d2 = json.loads(cfg.read_text(encoding="utf-8"))
    assert d2["models"]["best"] == "my-own-model" and d2["crm_vault"]
    assert list(cfg.parent.glob("config.json.bak-*"))


def test_refuses_and_changes_nothing_without_a_second_brain(tmp_path, monkeypatch):
    cfg = tmp_path / "out" / "config.json"
    rc, _ = run_install(monkeypatch, cfg, "--vault", str(tmp_path / "nope"))
    assert rc == 1 and not cfg.exists() and not cfg.parent.exists()


def test_refuses_without_claude_code(tmp_path, monkeypatch, world):
    monkeypatch.setenv("JEEVES_CONFIG", str(tmp_path / "c.json"))
    monkeypatch.setenv("PATH", str(tmp_path))
    import importlib
    import install
    importlib.reload(install)
    w = json.loads(world.read_text(encoding="utf-8"))
    assert install.main(["--yes", "--vault", w["second_brain"]]) == 1
    assert not (tmp_path / "c.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows Startup folder")
def test_logon_launcher_is_hidden_and_uninstall_removes_it(world, tmp_path, monkeypatch, fake_home):
    w = json.loads(world.read_text(encoding="utf-8"))
    cfg = tmp_path / "out" / "config.json"
    rc, inst = run_install(monkeypatch, cfg, "--vault", w["second_brain"], "--launcher")
    vbs = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/Jeeves.vbs"
    assert str(vbs).startswith(str(fake_home)), "must be the temporary Startup folder"
    text = vbs.read_text(encoding="utf-8")
    assert ", 0, False" in text and "pythonw" in text.lower() and "--no-open" in text
    assert inst.main(["--uninstall"]) == 0
    assert not vbs.exists()


def test_every_subprocess_call_is_silent_on_windows():
    """No window may ever flash: every subprocess call passes CREATE_NO_WINDOW."""
    bad = []
    for p in ROOT.rglob("*.py"):
        if "tests" in p.parts:
            continue
        s = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"subprocess\.(run|Popen|call|check_output)\s*\(", s):
            if "creationflags" not in s[m.start():m.start() + 600]:
                bad.append("%s:%d" % (p.name, s[:m.start()].count("\n") + 1))
    assert not bad, bad


def test_no_truncating_writes_on_existing_files():
    """Writes go to a temporary file and are swapped in with os.replace."""
    for p in (ROOT / "jeeves").rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        for m in re.finditer(r"open\(([^)]*)[\"']w[\"']", s):
            assert "tmp" in m.group(1), "%s writes in place: %s" % (p.name, m.group(0))


def test_the_installer_does_not_offer_a_port_another_program_is_using(world, tmp_path,
                                                                     monkeypatch, capsys):
    """Acceptance test 2026-09-23, fault 4. The guide says the port is "4040 unless another
    program is using it", which reads as a check. There was none: with 4040 already taken
    the installer still offered it, so pressing Enter wrote a config that cannot start and
    the member only found out at `python start.py`."""
    import importlib
    import socket
    monkeypatch.setenv("JEEVES_CONFIG", str(tmp_path / "out" / "config.json"))
    import install as _i
    importlib.reload(_i)               # CONFIG is read when the file is imported
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen(1)
    busy = taken.getsockname()[1]
    try:
        monkeypatch.setattr(_i, "DEFAULT_PORT", busy)
        w = json.loads(world.read_text(encoding="utf-8"))
        # --yes takes every default, which is exactly what pressing Enter does.
        rc = _i.main(["--yes", "--skip-claude-check", "--vault", w["second_brain"], "--crm", ""])
        assert rc == 0
        got = json.loads((tmp_path / "out" / "config.json").read_text(encoding="utf-8"))
        assert got["port"] != busy, "the installer offered a port another program is using"
        assert _i.port_free(got["port"]), "the port it offered is not free either"
        assert "already being used" in capsys.readouterr().out
    finally:
        taken.close()


def test_the_installer_keeps_the_port_you_already_chose(world, tmp_path, monkeypatch):
    """The port in an existing config.json is the member's own running Jeeves, so it is
    busy on purpose. A second install must still offer it back, not move them."""
    import importlib
    cfg = tmp_path / "out" / "config.json"
    w = json.loads(world.read_text(encoding="utf-8"))
    monkeypatch.setenv("JEEVES_CONFIG", str(cfg))
    import install as _i
    importlib.reload(_i)               # CONFIG is read when the file is imported
    _i.main(["--yes", "--skip-claude-check", "--vault", w["second_brain"], "--crm", "",
             "--port", "4555"])
    _i.main(["--yes", "--skip-claude-check", "--vault", w["second_brain"], "--crm", ""])
    assert json.loads(cfg.read_text(encoding="utf-8"))["port"] == 4555
