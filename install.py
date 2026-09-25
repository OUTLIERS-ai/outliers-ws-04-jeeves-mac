# -*- coding: utf-8 -*-
"""
Outliers Workspace - Piece 4 - Jeeves

A personal-assistant cockpit that sits on top of your second brain and your CRM:
chat with your own Claude Code, today's list, both vaults, your agents, your
token use and your other apps, each in a panel you can move, tab and pop out.

    python install.py

It asks where your second brain, your CRM and your agents are, checks Claude
Code is installed, and writes config.json next to this file. On Windows it also
writes "Start Jeeves (hidden).vbs" here, and when an answer changes it keeps
the old settings as config.json.bak-<date>. Running it again with the same
answers changes nothing.

    python install.py --copy ../jeeves-trial
        makes a second copy to experiment on, with its own port, while this one runs

    python install.py --uninstall
        stops Jeeves, and removes the file that starts it by itself when the computer
        starts, if this folder made one

Nothing here runs on a timer. Nothing starts Claude unless you type a message.

Needs: Python 3.11 or newer and Claude Code. Nothing to pip install.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
# JEEVES_CONFIG lets the tests install into a temporary folder instead of this one.
if os.environ.get("JEEVES_CONFIG"):
    CONFIG = Path(os.environ["JEEVES_CONFIG"]).expanduser()
else:
    CONFIG = HERE / "config.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LAUNCHER_NAME = "Jeeves.vbs"
MIN_PY = (3, 11)
DEFAULT_PORT = 4040
# The 3 models the chat panel offers, named in full so FleetView can price them and
# so a member knows exactly what they are running. Checked live on 2026-09-22.
MODELS = {"best": "claude-opus-5-5", "deep": "claude-sonnet-5", "fast": "claude-haiku-4-5"}
PLIST_NAME = "ai.outliers.jeeves.plist"
# The command a member types to run Python: a Mac has python3 and no plain python.
PY = "python3" if sys.platform == "darwin" else "python"

# When the start-up file runs, in the words each system's member reads. On a Mac "log in" alone
# reads as needing an account (Ashley, 2026-09-24), so the Mac says "switch on your Mac and sign
# in". The other systems keep exactly the words this installer printed before (wave 6, 2026-09-25).
_MAC = sys.platform == "darwin"
WHEN_STARTS = "when you switch on your Mac and sign in" if _MAC else "when the computer starts"
EACH_TIME = ("each time you switch on your Mac and sign in" if _MAC
             else "each time you switch on this computer and sign in")


def too_old(info):
    """True when this Python is older than Jeeves needs. Kept apart so it can be tested
    without a second Python on the machine."""
    return tuple(info[:2]) < MIN_PY


def say(*lines):
    for ln in lines:
        print("  " + ln if ln else "")


def ask(q, default="", a=None):
    if a is not None and a.yes:
        return default
    try:
        got = input("  " + q + (" [%s]: " % default if default else ": ")).strip()
    except EOFError:
        got = ""
    return got or default


def yes(q, default, a):
    if a.yes:
        return default
    got = ask("%s (%s)" % (q, "Y/n" if default else "y/N")).lower()
    return default if not got else got.startswith("y")


def home():
    return Path(os.path.expanduser("~"))


def claude_home():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else home() / ".claude"


def pointer(name):
    """The folder an earlier Outliers installer recorded, if it did."""
    p = home() / name
    try:
        val = p.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return val if val and Path(val).is_dir() else ""


def guess_brain():
    # A Mac looks outside Documents first: macOS may refuse a program that starts by itself
    # access to ~/Documents, so the Mac guides put the Second Brain at ~/Second Brain.
    places = (home() / "Documents" / "Second Brain", home() / "Second Brain")
    if sys.platform == "darwin":
        places = places[::-1]
    return pointer(".outliers-sb") or next((str(p) for p in places if p.is_dir()), "")


def guess_crm():
    return pointer(".outliers-crm") or next(
        (str(p) for p in (home() / "CRM", home() / "Documents" / "CRM") if p.is_dir()), "")


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def port_to_offer(wanted):
    """The port to put in front of the member: the one asked for, or the next free one.

    The guide says the port is "4040 unless another program is using it", which reads as
    a check. There was none, so a member with anything already on 4040 -- another copy of
    Jeeves, or any other program -- pressed Enter, got a config that cannot start, and
    only found out at `python start.py`.
    """
    wanted = int(wanted)
    if port_free(wanted):
        return wanted
    for p in range(wanted + 1, wanted + 61):
        if p <= 65535 and port_free(p):
            return p
    return wanted


# ------------------------------------------------------------------ launchers

def startup_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def pythonw():
    pw = Path(sys.executable).with_name("pythonw.exe")
    return str(pw if pw.exists() else sys.executable)


def vbs_text(folder=None, config=None):
    """The Windows start file for the Jeeves in `folder` (this one unless a copy is made)."""
    folder = Path(folder or HERE)
    config = Path(config or (CONFIG if folder == HERE else folder / "config.json"))
    # Run ..., 0, False : 0 = no window at all, False = do not wait for it.
    cmd = '"%s" "%s" --no-open' % (pythonw(), folder / "start.py")
    if config != folder / "config.json":
        cmd += ' --config "%s"' % config
    return ('\' Starts Jeeves with no window. Made by install.py; remove with\n'
            '\' python install.py --uninstall\n'
            'Set sh = CreateObject("WScript.Shell")\n'
            'sh.CurrentDirectory = "%s"\n'
            'sh.Run "%s", 0, False\n') % (folder, cmd.replace('"', '""'))


def mac_path():
    """A job the Mac starts by itself when the computer starts has almost no PATH, so Claude Code would not be found.
    Give it the folders Claude Code's installers use, then the usual system ones."""
    h = str(home())
    return ":".join([h + "/.local/bin", h + "/.claude/local", "/opt/homebrew/bin",
                     "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])


def plist_text():
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.outliers.jeeves</string>
  <key>ProgramArguments</key><array>
    <string>%s</string><string>%s</string><string>--no-open</string></array>
  <key>WorkingDirectory</key><string>%s</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>%s</string></dict>
  <key>RunAtLoad</key><true/>
</dict></plist>
""" % (sys.executable, HERE / "start.py", HERE, mac_path())


def launcher_files():
    d = startup_dir()
    return ([d / LAUNCHER_NAME] if d else []) + [home() / "Library" / "LaunchAgents" / PLIST_NAME]


def started_folder(text):
    """The folder whose start.py a start file runs, or None if it cannot be read."""
    m = re.search(r'([A-Za-z]:[^"<>\r\n]*?|/[^"<>\r\n]*?)[\\/]start\.py', text)
    return Path(m.group(1)) if m else None


def belongs_here(path):
    """A start file is this folder's to replace or remove when it starts this folder's
    Jeeves, or a folder that is gone (moved or deleted). One that starts another Jeeves
    that is still there, such as the everyday one when this is a copy, is left alone.
    A file that cannot be read is left alone too."""
    try:
        folder = started_folder(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return False
    if folder is None:
        return False
    try:
        same = folder.resolve() == HERE
    except OSError:
        same = False
    return same or not (folder / "start.py").exists()


def not_ours(target):
    return ("Another Jeeves folder already starts by itself %s (%s)."
            % (WHEN_STARTS, target) + "\n  Left as it is. To move it to this folder, run  %s install.py" % PY
            + " --uninstall  in that folder first.")


def install_launcher():
    if os.name == "nt":
        d = startup_dir()
        if d is None:
            return "Could not find your Startup folder, so nothing was made to start Jeeves."
        target = d / LAUNCHER_NAME
        text = vbs_text()
        if target.exists() and target.read_text(encoding="utf-8") == text:
            return ("The file that starts Jeeves when the computer starts is already in place: %s"
                    % target)
        if target.exists() and not belongs_here(target):
            return not_ours(target)
        atomic_write(target, text)
        return "Jeeves will start by itself, with no window, when the computer starts: %s" % target
    if sys.platform == "darwin":
        target = home() / "Library" / "LaunchAgents" / PLIST_NAME
        if target.exists() and not belongs_here(target):
            return not_ours(target)
        atomic_write(target, plist_text())
        return ("Wrote %s. It starts Jeeves, with no window, each time you switch on your Mac and sign in.\n"
                "To start it now, without signing out, run:\n     launchctl load %s" % (target, target))
    return ("On Linux, add this line to 'crontab -e' to start Jeeves when the computer starts:\n"
            "     @reboot cd %s && %s start.py --no-open" % (HERE, sys.executable))


def unload_launch_agent(path):
    """Mac: switch the job off in launchd before its file goes, so `launchctl list` no longer
    shows it and a Jeeves it started stops now, not at the next log-out (wave 6, 2026-09-25).
    A job that was never loaded makes launchctl say so; that is not an error here."""
    try:
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True, text=True,
                       timeout=30, creationflags=NO_WINDOW)
    except Exception:  # noqa: BLE001
        pass


def remove_launcher():
    done, kept = [], []
    for p in launcher_files():
        if not p.exists():
            continue
        if belongs_here(p):
            if sys.platform == "darwin" and p.suffix == ".plist":
                unload_launch_agent(p)
            p.unlink()
            done.append(str(p))
        else:
            kept.append(str(p))
    return done, kept


def hidden_start_file():
    """A double-click file in this folder that starts Jeeves with no window (Windows)."""
    if os.name != "nt":
        return None
    target = CONFIG.parent / "Start Jeeves (hidden).vbs"
    text = vbs_text()
    if target.exists() and target.read_text(encoding="utf-8") == text:
        return target, False
    atomic_write(target, text)
    return target, True


# ------------------------------------------------------------------ main

def uninstall():
    say("", "Stopping Jeeves and removing the file that starts it %s" % WHEN_STARTS,
        "(your config.json and vaults are not touched).", "")
    try:
        sys.path.insert(0, str(HERE))
        from start import stop
        stop()
    except Exception:  # noqa: BLE001
        pass
    gone, kept = remove_launcher()
    for g in gone:
        say("removed  %s" % g)
    for k in kept:
        say("left in place  %s  (it starts Jeeves from another folder)" % k)
    if not gone and not kept:
        say("Nothing was set to start Jeeves %s." % WHEN_STARTS)
    say("", "To remove Jeeves completely, delete this folder: %s" % HERE, "")
    return 0


COPY_LEAVES = {"state", "__pycache__", ".pytest_cache", "Start Jeeves (hidden).vbs", "config.json"}


def copy_to(dest, port=None):
    """A second Jeeves to experiment on while this one keeps running.

    Copies this folder to `dest` with the same folders and settings but a port of its own.
    It leaves behind what belongs to the running Jeeves: state/ (its saved conversation
    and the record of which program is running, which `--stop` reads), the old-settings
    backups and the Windows double-click start file, which is made afresh for the copy.
    It never touches the file that starts Jeeves when the computer starts.
    """
    dest = Path(os.path.expanduser(dest)).resolve()
    old = {}
    if CONFIG.exists():
        try:
            old = json.loads(CONFIG.read_text(encoding="utf-8"))
        except ValueError:
            old = {}
    if not old.get("second_brain"):
        say("Install this Jeeves first (%s install.py), then make the copy." % PY,
            "Nothing has been changed.", "")
        return 1
    if dest == HERE or HERE in dest.parents:
        say("The copy has to go outside this folder, for example ../jeeves-trial .",
            "Nothing has been changed.", "")
        return 1
    if dest.exists() and any(dest.iterdir()):
        say("%s already has files in it. Pick a new folder name." % dest,
            "Nothing has been changed.", "")
        return 1
    ours = int(old.get("port") or DEFAULT_PORT)
    port = port or port_to_offer(ours + 1)

    def leave(folder, names):
        return [n for n in names if n in COPY_LEAVES or n.startswith("config.json.bak-")
                or n.endswith(".tmp")]

    shutil.copytree(HERE, dest, ignore=leave, dirs_exist_ok=True)
    cfg = dict(old, port=port)
    atomic_write(dest / "config.json", json.dumps(cfg, indent=2) + "\n")
    say("Made a copy of Jeeves to experiment on: %s" % dest,
        "It reads the same note folders as this one, on port %d instead of %d." % (port, ours),
        "It starts a new conversation. Your everyday Jeeves is not touched, and neither is",
        "the file that starts it %s." % WHEN_STARTS)
    if os.name == "nt":
        atomic_write(dest / "Start Jeeves (hidden).vbs", vbs_text(dest, dest / "config.json"))
        say("Its own Start Jeeves (hidden).vbs starts the copy, not this one.")
    say("", "Start the copy:", "", "    cd %s" % dest, "    %s start.py" % PY, "",
        "It opens http://127.0.0.1:%d/ . Ctrl+C in that terminal stops it." % port, "")
    return 0


def ccusage_install():
    """The line that installs ccusage on this computer (jeeves/config.py)."""
    from jeeves.config import CCUSAGE_INSTALL
    return CCUSAGE_INSTALL


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install Jeeves.")
    ap.add_argument("--vault", help="your second-brain folder")
    ap.add_argument("--crm", help="your CRM folder (optional)")
    ap.add_argument("--agents", help="a folder of Claude Code agents")
    ap.add_argument("--port", type=int)
    ap.add_argument("--launcher", action="store_true",
                    help="start by itself, with no window, %s" % WHEN_STARTS)
    ap.add_argument("--yes", action="store_true", help="accept every default, ask nothing")
    ap.add_argument("--uninstall", action="store_true",
                    help="stop Jeeves and remove the file that starts it %s" % WHEN_STARTS)
    ap.add_argument("--copy", metavar="FOLDER",
                    help="make a second copy to experiment on, with its own port")
    ap.add_argument("--skip-claude-check", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    say("", "=" * 66, "  OUTLIERS WORKSPACE - PIECE 4 - JEEVES", "=" * 66, "")
    if a.uninstall:
        return uninstall()
    if a.copy:
        return copy_to(a.copy, a.port)

    # 1. What it needs. If anything is missing, stop and change nothing.
    if too_old(sys.version_info):
        say("Jeeves needs Python %d.%d or newer. This is %s."
            % (MIN_PY[0], MIN_PY[1], sys.version.split()[0]),
            "Python 3.9 and older no longer get security fixes, and 3.10 gets them only",
            "until 2026-10-31 (python.org, checked 2026-09-24).",
            "Install a newer Python from https://www.python.org/downloads/ and run this again.",
            "Nothing has been changed.", "")
        return 1
    claude = shutil.which("claude")
    if not claude and os.name != "nt":
        # Claude Code's own Mac installer puts claude in ~/.local/bin and may leave that
        # folder off the PATH a Mac's Terminal uses (seen on GitHub's Intel test Mac,
        # 2026-09-24): it is installed, just not found by name.
        for c in (home() / ".local" / "bin" / "claude", home() / ".claude" / "local" / "claude"):
            if c.is_file() and os.access(str(c), os.X_OK):
                claude = str(c)
                say("Found Claude Code at %s. That folder is not on this Terminal's PATH, so" % c,
                    "typing  claude  may say \"command not found\"; Jeeves finds it anyway. To fix",
                    "it for typing too:  echo 'export PATH=\"%s:$PATH\"' >> ~/.zshrc" % c.parent,
                    "then open a new Terminal window.", "")
                break
    if not claude and not a.skip_claude_check:
        say("Claude Code is not installed, or not on your PATH.", "",
            "Jeeves has no brain of its own: every answer comes from your Claude Code.",
            "Install it from https://code.claude.com/docs/en/setup ,",
            "open a new terminal, type  claude  once to log in, then run this again.", "",
            "Nothing has been changed.", "")
        return 1
    if claude:
        try:
            v = subprocess.run([claude, "--version"], capture_output=True, text=True,
                               timeout=30, creationflags=NO_WINDOW).stdout.strip()
        except Exception:  # noqa: BLE001
            v = ""
        say("Found Claude Code %s" % (v or "(version unknown)"))
    say("Python %s - nothing to install with pip." % sys.version.split()[0], "")

    old = {}
    if CONFIG.exists():
        try:
            old = json.loads(CONFIG.read_text(encoding="utf-8"))
        except ValueError:
            old = {}

    # 2. Where your folders are.
    brain = a.vault or ask("Where is your second brain (the folder)?",
                           old.get("second_brain") or guess_brain(), a)
    brain = str(Path(os.path.expanduser(brain)).resolve()) if brain else ""
    if not brain or not Path(brain).is_dir():
        say("", "I cannot find a second brain at %r." % brain,
            "Install it first (outliers-sb-01-memory), or give the right folder.",
            "Nothing has been changed.", "")
        return 1
    crm = a.crm if a.crm is not None else ask(
        "Where is your CRM (the folder)? Leave blank if you do not have one",
        old.get("crm_vault") or guess_crm(), a)
    crm = str(Path(os.path.expanduser(crm)).resolve()) if crm else ""
    if crm and not Path(crm).is_dir():
        say("", "There is no folder at %s. Leave it blank or give the right one." % crm,
            "Nothing has been changed.", "")
        return 1
    default_agents = (old.get("agents_dirs") or [str(claude_home() / "agents")])[0]
    agents = a.agents or ask("Where are your agents?", default_agents, a)
    agents = str(Path(os.path.expanduser(agents)).resolve()) if agents else ""
    port = a.port
    # A port already in config.json is the member's own Jeeves, so it is busy on purpose:
    # offer it back. Only the very first install looks for a free one.
    default_port = int(old.get("port") or DEFAULT_PORT)
    if not port and not old.get("port"):
        offered = port_to_offer(default_port)
        if offered != default_port:
            say("  Port %d is already being used by another program, so Jeeves offers %d."
                % (default_port, offered))
        default_port = offered
    while not port:
        got = ask("Which port should Jeeves use?", str(default_port), a)
        try:
            port = int(got)
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            port = None
            say("Please type a number between 1024 and 65535, for example 4040.")
            if a.yes:
                return 1

    # 3. Nice to have, never required.
    say("", "Optional extras:")
    say("  ccusage (shows your 5-hour usage window): %s"
        % ("found" if shutil.which("ccusage") else "not found - needs Node.js, then: " + ccusage_install()))
    try:
        import playwright  # noqa: F401
        pw = "found"
    except ImportError:
        pw = "not found"
    say("  playwright (only needed to retake the guide's pictures): %s" % pw)
    if not port_free(port) and old.get("port") != port:
        # Name a port that is actually free, never a fixed number: a member already on
        # 4041 was being told to try the port that had just refused them.
        spare = next((p for p in range(port + 1, port + 60) if port_free(p)), port + 1)
        say("  Port %d is busy right now. Jeeves will say so when it starts; pick another "
            "with %s install.py --port %d" % (port, PY, spare))

    # 4. One config file. Keep anything you added by hand.
    cfg = dict(old)
    cfg.update({"second_brain": brain, "crm_vault": crm,
                "agents_dirs": [agents] if agents else [], "port": port})
    cfg.setdefault("name", "Jeeves")
    cfg.setdefault("models", dict(MODELS))
    cfg.setdefault("default_model", "best")
    cfg.setdefault("permission_mode", "dontAsk")
    cfg.setdefault("allow_actions", False)
    cfg.setdefault("claude_command", "claude")
    # The download addresses come from 1 setting in jeeves/config.py (MAC_REPOS_PUBLISHED).
    from jeeves.config import app_repo
    cfg.setdefault("apps", {
        "projectforge": {"url": "http://127.0.0.1:3020",
                         "repo": app_repo("outliers-ws-03-projectforge")},
        "fleetview": {"url": "http://127.0.0.1:3010",
                      "repo": app_repo("outliers-ws-02-fleetview")}})
    say("")
    if cfg == old:
        say("config.json already says exactly this. Nothing changed.")
    else:
        if CONFIG.exists():
            backup = CONFIG.with_name("config.json.bak-%s" % date.today().isoformat())
            shutil.copy2(CONFIG, backup)
            say("Kept a copy of your old settings: %s" % backup.name)
        atomic_write(CONFIG, json.dumps(cfg, indent=2) + "\n")
        say("Wrote config.json")

    hs = hidden_start_file()
    if hs:
        say(("Made %s - double-click it to start Jeeves with no window." if hs[1] else
             "%s is already in place (double-click it to start Jeeves with no window).")
            % hs[0].name)

    # 5. Start by itself when the computer starts? Off unless you say yes.
    if a.launcher or yes("Start Jeeves by itself, with no window, %s?" % EACH_TIME, False, a):
        say(install_launcher())
    else:
        say("Jeeves will not start by itself %s. " % WHEN_STARTS
            + "Start it yourself with:  %s start.py" % PY)

    say("", "-" * 66,
        "Done. Start it now:", "",
        "    %s start.py" % PY, "",
        "Your browser opens http://127.0.0.1:%d/ . You should see the orb top left," % port,
        "Chat on the left, Today in the middle and Across everything on the right.",
        "On a laptop: Chat on the left and a stack of tabs on the right.",
        "Leave the terminal open while you use it; Ctrl+C in it stops Jeeves.",
        "Chat is given 3 tools and no others: open a file, search inside files, find",
        "files by name. Commands, file changes and the internet are switched off until",
        "you set \"allow_actions\": true in config.json.",
        "Nothing runs on a timer: Claude is only used when you send a message.", "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
