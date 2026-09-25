# -*- coding: utf-8 -*-
"""Mac only (fault row 11, build plan V3): stopping Jeeves must never stop the program that asked.

`start.py --stop` ends Jeeves with jeeves/proc.py kill_tree, which ended the whole process group
of the Jeeves it found. A Jeeves started by a script or a check (not typed in Terminal) shares its
caller's group, so the caller was ended too: on GitHub's test Macs (2026-09-24) the test run
itself was ended once Jeeves started in time to be found (the other half of row 11). Each check
here runs in a separate Python program, in a session of its own, so a wrong kill_tree ends only
that program and the check reports it.

Run by name only:  python3 -m pytest -q tests/mac/mac_stop_spares_caller.py
"""
import subprocess
import sys
import textwrap

import pytest

from conftest import ROOT

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process groups are a Mac and Linux idea")


def run_caller(body):
    code = textwrap.dedent('''
        import os, subprocess, sys, time
        sys.path.insert(0, %r)
        from jeeves import proc as P
    ''' % str(ROOT)) + textwrap.dedent(body) + "\nprint('CALLER SURVIVED', flush=True)\n"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                          start_new_session=True)


def test_ending_a_jeeves_in_our_group_spares_the_caller():
    r = run_caller('''
        kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        P.kill_tree(kid.pid)
        kid.wait(timeout=20)
        print("child ended with", kid.returncode, flush=True)
    ''')
    assert "CALLER SURVIVED" in r.stdout, "kill_tree ended its caller (exit %s): %s%s" % (r.returncode, r.stdout, r.stderr)
    assert "child ended with" in r.stdout


def test_what_that_jeeves_started_is_ended_too():
    r = run_caller('''
        kid = subprocess.Popen([sys.executable, "-c",
            "import subprocess, sys, time; g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
            "print(g.pid, flush=True); time.sleep(60)"], stdout=subprocess.PIPE, text=True)
        grandkid = int(kid.stdout.readline())
        P.kill_tree(kid.pid)
        kid.wait(timeout=20)
        end = time.time() + 10
        while time.time() < end and P.alive(grandkid):
            time.sleep(0.2)
        print("grandchild alive:", P.alive(grandkid), flush=True)
    ''')
    assert "CALLER SURVIVED" in r.stdout, "kill_tree ended its caller (exit %s): %s%s" % (r.returncode, r.stdout, r.stderr)
    assert "grandchild alive: False" in r.stdout, r.stdout + r.stderr


def test_a_jeeves_in_its_own_group_is_ended_with_its_whole_group():
    r = run_caller('''
        kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
        P.kill_tree(kid.pid)
        kid.wait(timeout=20)
        print("child ended with", kid.returncode, flush=True)
    ''')
    assert "CALLER SURVIVED" in r.stdout and "child ended with -9" in r.stdout, r.stdout + r.stderr
