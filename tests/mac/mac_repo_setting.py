# -*- coding: utf-8 -*-
"""Wave 1 second read (push order): Jeeves' Work board and FleetView links must lead to a repo that
exists, and switch to the Mac copies with 1 setting.

The Mac copies of the Work board and FleetView (outliers-ws-03-projectforge-mac and
outliers-ws-02-fleetview-mac) are published in a later wave of the Mac build plan. A Mac member
sent there before then finds nothing. So jeeves/config.py has 1 setting, MAC_REPOS_PUBLISHED.
It was False until wave 6; Ashley switched it on on 2026-09-25 (wave 6), so a Mac member is sent to
the Mac copies and a Windows member keeps the Windows repos. These checks run on every system.

Run by name only:  python3 -m pytest -q tests/mac/mac_repo_setting.py
(pytest never collects tests/mac/ in a plain run, so the counts the guides print stay true.)
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://github.com/OUTLIERS-ai/"
APPS = {"projectforge": "outliers-ws-03-projectforge", "fleetview": "outliers-ws-02-fleetview"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def setting_lines(text):
    return re.findall(r"(?m)^MAC_REPOS_PUBLISHED\s*=\s*(\w+)\s*$", text)


def test_the_setting_is_1_line_and_on_since_wave_6():
    lines = setting_lines((ROOT / "jeeves" / "config.py").read_text(encoding="utf-8"))
    assert lines == ["True"], "jeeves/config.py must set MAC_REPOS_PUBLISHED exactly once, to True: %r" % lines
    for f in ROOT.rglob("*.py"):
        if f.name == "config.py" and f.parent.name == "jeeves" or "tests" in f.parts:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        assert '"-mac"' not in text and "'-mac'" not in text, "%s names a -mac repo itself; use config.app_repo" % f


def test_a_mac_member_gets_the_mac_copies_and_a_windows_member_keeps_the_windows_repos():
    from jeeves import config as C
    for name in APPS.values():
        assert C.app_repo(name, mac=True) == BASE + name + "-mac"
        assert C.app_repo(name, mac=False) == BASE + name
    end = "-mac" if sys.platform == "darwin" else ""
    assert {k: v["repo"] for k, v in C.DEFAULTS["apps"].items()} == {k: BASE + n + end for k, n in APPS.items()}


def mac_addresses_with(tmp_path, value):
    """Copy Jeeves, set the 1 line, and ask it (as a Mac) where the apps are downloaded from."""
    copy = tmp_path / ("jeeves-" + value)
    shutil.copytree(ROOT / "jeeves", copy / "jeeves", ignore=shutil.ignore_patterns("__pycache__"))
    cfg = copy / "jeeves" / "config.py"
    text = cfg.read_text(encoding="utf-8")
    new = re.sub(r"(?m)^MAC_REPOS_PUBLISHED\s*=\s*\w+\s*$", "MAC_REPOS_PUBLISHED = " + value, text)
    assert new.count("MAC_REPOS_PUBLISHED = " + value) == 1
    cfg.write_text(new, encoding="utf-8")
    code = ("import sys; sys.platform = 'darwin'\n"
            "from jeeves import config as C\n"
            "print({k: v['repo'] for k, v in C.DEFAULTS['apps'].items()})\n"
            "print(C.app_repo('outliers-ws-02-fleetview', mac=False))\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(copy), capture_output=True, text=True,
                       timeout=60, creationflags=NO_WINDOW)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def test_switching_the_1_line_sends_a_mac_member_to_the_mac_copies(tmp_path):
    on = mac_addresses_with(tmp_path, "True")
    assert on[0] == str({k: BASE + n + "-mac" for k, n in APPS.items()}), on
    assert on[1] == BASE + "outliers-ws-02-fleetview", "a Windows member must never be sent to a -mac repo"
    off = mac_addresses_with(tmp_path, "False")
    assert off[0] == str({k: BASE + n for k, n in APPS.items()}), off
