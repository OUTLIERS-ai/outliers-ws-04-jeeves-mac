# -*- coding: utf-8 -*-
"""Wave 6 (2026-09-25): the practice world (tools/demo.py) links a Mac member to the Mac downloads.

tools/demo.py wrote the Windows addresses of the Work board and FleetView into the practice
config.json on every computer, while the installer takes them from jeeves.config.app_repo, which on
a Mac gives the `-mac` repos. A Windows member keeps the Windows addresses (checked on every system).

Run by name only:  python3 -m pytest -q tests/mac/mac_demo_links.py
"""
import json
import sys

import demo

BASE = "https://github.com/OUTLIERS-ai/"


def test_the_practice_world_uses_the_same_download_links_as_the_installer(tmp_path):
    cfg = json.loads(demo.build(tmp_path / "world").read_text(encoding="utf-8"))
    end = "-mac" if sys.platform == "darwin" else ""
    assert cfg["apps"]["projectforge"]["repo"] == BASE + "outliers-ws-03-projectforge" + end
    assert cfg["apps"]["fleetview"]["repo"] == BASE + "outliers-ws-02-fleetview" + end
