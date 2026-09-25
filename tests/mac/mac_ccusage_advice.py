# -*- coding: utf-8 -*-
"""Wave 6 (2026-09-25): on a Mac, the advice for installing ccusage must be a line that works.

With Node.js from nodejs.org, `npm install -g ccusage` is refused on a Mac ("EACCES: permission
denied": the global folder belongs to the system). `npm install -g --prefix ~/.local ccusage` works
with no password and puts ccusage in ~/.local/bin, where Jeeves finds it from Terminal and from its
LaunchAgent (GitHub's test Macs, runs 36154211225 and 36154873391). The installer (install.py) and
the Tokens panel (jeeves/sessions.py) both advised the refused line. Windows keeps its line.

Run by name only:  python3 -m pytest -q tests/mac/mac_ccusage_advice.py
"""
import sys

import pytest

from conftest import ROOT

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Mac wording")
WORKS = "npm install -g --prefix ~/.local ccusage"


def test_the_tokens_panel_names_the_line_that_works(monkeypatch):
    from jeeves import sessions
    monkeypatch.setattr(sessions.shutil, "which", lambda name: None)
    reason = sessions.ccusage_block({})["reason"]
    assert WORKS in reason, reason


def test_the_installer_names_the_line_that_works():
    text = (ROOT / "install.py").read_text(encoding="utf-8")
    assert "npm install -g ccusage" not in text, "install.py still prints the line a Mac refuses"
    from jeeves import config
    assert config.CCUSAGE_INSTALL == WORKS
