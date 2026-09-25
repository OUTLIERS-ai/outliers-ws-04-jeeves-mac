# -*- coding: utf-8 -*-
"""Mac only (wave 0b fault, build plan V3 row list): Jeeves' Work board and FleetView links must
lead a Mac member to the Mac repos.

The panels for the Work board (ProjectForge) and FleetView link to the repo to download when the
app is not running. They named the Windows repos, whose guides print Windows commands. On a Mac
they name the Mac copy of each (its name ends in -mac) once those copies are published; until then
(jeeves/config.py MAC_REPOS_PUBLISHED = False, see tests/mac/mac_repo_setting.py) they name the
repos that exist, whose code also runs on a Mac.

Run by name only:  python3 -m pytest -q tests/mac/mac_app_links.py
"""
import importlib
import json
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Mac repo links")

def want():
    from jeeves import config as C
    end = "-mac" if C.MAC_REPOS_PUBLISHED else ""
    return {"projectforge": "https://github.com/OUTLIERS-ai/outliers-ws-03-projectforge" + end,
            "fleetview": "https://github.com/OUTLIERS-ai/outliers-ws-02-fleetview" + end}


def test_the_installer_writes_the_mac_links(world, tmp_path, monkeypatch):
    w = json.loads(world.read_text(encoding="utf-8"))
    cfg = tmp_path / "out" / "config.json"
    monkeypatch.setenv("JEEVES_CONFIG", str(cfg))
    import install
    importlib.reload(install)
    assert install.main(["--vault", w["second_brain"], "--crm", w["crm_vault"], "--yes", "--skip-claude-check"]) == 0
    apps = json.loads(cfg.read_text(encoding="utf-8"))["apps"]
    assert {k: v["repo"] for k, v in apps.items()} == want()


def test_the_built_in_settings_name_the_mac_links():
    from jeeves import config as C
    assert {k: v["repo"] for k, v in C.DEFAULTS["apps"].items()} == want()
