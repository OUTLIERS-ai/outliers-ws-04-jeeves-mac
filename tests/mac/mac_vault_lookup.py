# -*- coding: utf-8 -*-
"""Mac only (fault row 23, build plan V3): on a Mac, Jeeves suggests ~/Second Brain first.

macOS may refuse a program that starts by itself access to ~/Documents, so the Mac guides put the
Second Brain at ~/Second Brain. The installer looked in ~/Documents/Second Brain first. Windows
keeps its own order, unchanged.

Run by name only:  python3 -m pytest -q tests/mac/mac_vault_lookup.py
"""
import importlib
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Mac look-up order")


def test_second_brain_outside_documents_comes_first(fake_home):
    for p in (fake_home / "Second Brain", fake_home / "Documents" / "Second Brain"):
        p.mkdir(parents=True)
    import install
    importlib.reload(install)
    assert install.guess_brain() == str(fake_home / "Second Brain")


def test_documents_is_still_found_when_it_is_the_only_one(fake_home):
    (fake_home / "Documents" / "Second Brain").mkdir(parents=True)
    import install
    importlib.reload(install)
    assert install.guess_brain() == str(fake_home / "Documents" / "Second Brain")
