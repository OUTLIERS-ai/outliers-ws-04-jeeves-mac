# -*- coding: utf-8 -*-
"""A second copy to experiment on, while the everyday Jeeves keeps running.

Final check of 2026-09-24: the guide said "copy the whole folder and change the copy".
Done by hand, the copy kept the everyday Jeeves's port (4040), its saved conversation
and its state/jeeves.pid, so `python start.py --stop` typed in the copy stopped the
everyday Jeeves, and the copy's own "Start Jeeves (hidden).vbs" still started the
original. `python install.py --copy <folder>` makes the copy safely; these checks
hold it to that.
"""
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STARTUP = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def installer(monkeypatch, cfg):
    monkeypatch.setenv("JEEVES_CONFIG", str(cfg))
    import install
    importlib.reload(install)          # CONFIG is read when the file is imported
    return install


def everyday(world, tmp_path, monkeypatch, port=4555, launcher=False):
    """The member's everyday Jeeves: installed, with working files in state/."""
    w = json.loads(world.read_text(encoding="utf-8"))
    cfg = tmp_path / "everyday" / "config.json"
    inst = installer(monkeypatch, cfg)
    args = ["--yes", "--skip-claude-check", "--vault", w["second_brain"],
            "--crm", w["crm_vault"], "--port", str(port)]
    assert inst.main(args + (["--launcher"] if launcher else [])) == 0
    return inst, cfg


def test_the_copy_gets_its_own_port_and_none_of_the_running_copys_files(world, tmp_path,
                                                                       monkeypatch, capsys):
    inst, cfg = everyday(world, tmp_path, monkeypatch)
    dest = tmp_path / "jeeves-trial"
    assert inst.main(["--copy", str(dest)]) == 0
    got = json.loads((dest / "config.json").read_text(encoding="utf-8"))
    ours = json.loads(cfg.read_text(encoding="utf-8"))
    assert got["port"] != ours["port"], "the copy would clash with the everyday Jeeves"
    assert got["second_brain"] == ours["second_brain"] and got["crm_vault"] == ours["crm_vault"]
    assert (dest / "start.py").exists() and (dest / "jeeves" / "server.py").exists()
    # the running copy's record of itself and its saved conversation stay behind
    assert not (dest / "state").exists()
    assert not list(dest.glob("config.json.bak-*"))
    out = capsys.readouterr().out
    # a Mac has python3 and no python, so the copy tells a Mac member to type python3
    assert str(got["port"]) in out
    assert ("python3 start.py" if sys.platform == "darwin" else "python start.py") in out


@pytest.mark.skipif(os.name != "nt", reason="the double-click start file is made on Windows")
def test_the_copys_double_click_file_starts_the_copy_not_the_original(world, tmp_path,
                                                                     monkeypatch):
    inst, _ = everyday(world, tmp_path, monkeypatch)
    dest = tmp_path / "jeeves-trial"
    assert inst.main(["--copy", str(dest)]) == 0
    text = (dest / "Start Jeeves (hidden).vbs").read_text(encoding="utf-8")
    assert str(dest.resolve() / "start.py") in text
    assert str(inst.HERE / "start.py") not in text


@pytest.mark.skipif(os.name != "nt", reason="Windows Startup folder")
def test_making_a_copy_leaves_the_start_by_itself_file_alone(world, tmp_path, monkeypatch,
                                                             fake_home):
    inst, _ = everyday(world, tmp_path, monkeypatch, launcher=True)
    vbs = Path(os.environ["APPDATA"]).joinpath(*STARTUP) / "Jeeves.vbs"
    before = vbs.read_bytes()
    assert inst.main(["--copy", str(tmp_path / "jeeves-trial")]) == 0
    assert vbs.read_bytes() == before


def test_a_copy_refuses_a_folder_that_already_has_files(world, tmp_path, monkeypatch):
    inst, _ = everyday(world, tmp_path, monkeypatch)
    dest = tmp_path / "jeeves-trial"
    dest.mkdir()
    (dest / "mine.txt").write_text("keep me", encoding="utf-8")
    assert inst.main(["--copy", str(dest)]) == 1
    assert [p.name for p in dest.iterdir()] == ["mine.txt"]


def test_a_copy_needs_an_installed_jeeves_first(tmp_path, monkeypatch):
    inst = installer(monkeypatch, tmp_path / "nothing-yet" / "config.json")
    dest = tmp_path / "jeeves-trial"
    assert inst.main(["--copy", str(dest)]) == 1
    assert not dest.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows Startup folder")
def test_uninstall_in_another_folder_leaves_the_everyday_start_file(world, tmp_path,
                                                                   monkeypatch, fake_home):
    """A launcher that starts Jeeves from a different, existing folder is not this folder's
    to remove: `--uninstall` typed in a copy used to delete the everyday one's."""
    inst, _ = everyday(world, tmp_path, monkeypatch, launcher=True)
    vbs = Path(os.environ["APPDATA"]).joinpath(*STARTUP) / "Jeeves.vbs"
    other = tmp_path / "everyday-folder"
    other.mkdir()
    (other / "start.py").write_text("# the everyday Jeeves\n", encoding="utf-8")
    text = vbs.read_text(encoding="utf-8").replace(str(inst.HERE), str(other))
    vbs.write_text(text, encoding="utf-8")
    assert inst.main(["--uninstall"]) == 0
    assert vbs.exists() and vbs.read_text(encoding="utf-8") == text
    # and saying yes in this folder does not take the file over either
    assert inst.main(["--yes", "--skip-claude-check", "--launcher"]) == 0
    assert vbs.read_text(encoding="utf-8") == text


def test_the_installer_gives_the_real_python_310_date(monkeypatch, capsys):
    """python.org, checked 2026-09-24: 3.10 gets security fixes until 2026-10-31."""
    import install
    importlib.reload(install)
    monkeypatch.setattr(install, "too_old", lambda info: True)
    assert install.main(["--yes"]) == 1
    out = capsys.readouterr().out
    assert "2026-10-31" in out and "3.10 and older no longer" not in out
