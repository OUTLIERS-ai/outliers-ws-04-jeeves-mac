# -*- coding: utf-8 -*-
"""Wave 6 (2026-09-25): on a Mac, a CRM with no Today list builder is not told to run it.

A CRM made in the first CRM sessions has no `_engine/today.py`: that program comes with part 7 of
the CRM sessions. Yet the Today panel and the overview card told every member with no Today.md to
run `python3 _engine/today.py --write` in the CRM folder, which then fails (GitHub's test Macs,
run 36154211225). With the program there, the old instruction stays.

The same now holds on every system: tests/mac/mac_today_without_tool_every_system.py.

Run by name only:  python3 -m pytest -q tests/mac/mac_today_without_tool.py
"""
import sys

import pytest

from conftest import ROOT

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Mac wording")


def _today(tmp_path, with_tool):
    from jeeves import vaults
    crm = tmp_path / "CRM"
    crm.mkdir()
    if with_tool:
        (crm / "_engine").mkdir()
        (crm / "_engine" / "today.py").write_text("print('today')\n", encoding="utf-8")
    brain = tmp_path / "Second Brain"
    brain.mkdir()
    return vaults.today({"crm_vault": str(crm), "second_brain": str(brain)})["crm"]


def test_a_crm_without_the_builder_is_not_told_to_run_it(tmp_path):
    crm = _today(tmp_path, with_tool=False)
    assert crm["found"] is False and crm.get("no_today_tool") is True
    assert "--write" not in crm["hint"], crm["hint"]
    assert "part 7 of the CRM sessions" in crm["hint"], crm["hint"]


def test_a_crm_with_the_builder_keeps_the_instruction(tmp_path):
    crm = _today(tmp_path, with_tool=True)
    assert "python3 _engine/today.py --write" in crm["hint"]
    assert not crm.get("no_today_tool")


def test_the_overview_card_shows_the_servers_words_when_the_builder_is_missing():
    js = (ROOT / "jeeves" / "static" / "app.js").read_text(encoding="utf-8")
    assert "td.crm.no_today_tool" in js
