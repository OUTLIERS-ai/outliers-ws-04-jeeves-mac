# -*- coding: utf-8 -*-
"""proc.py - end a program and everything it started, and check whether a program is running.

Why this exists: Claude Code installed with npm is started through `claude.cmd`,
which runs the real Claude as a child program. Ending only the program Jeeves
started (cmd.exe) left the real Claude working, unseen, for up to 10 minutes.
So Stop ends the whole family: on Windows `taskkill /T /F`, elsewhere the whole
process group (Jeeves starts Claude in a group of its own for this reason).

No window ever opens: every call passes CREATE_NO_WINDOW.
"""

import os
import signal
import subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def popen_group_kwargs():
    """Extra Popen arguments so that kill_tree can later end every child too."""
    if os.name == "nt":
        return {}
    return {"start_new_session": True}


def kill_tree(pid):
    """End the program with this number and every program it started. Returns True if sent."""
    if not pid:
        return False
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                           creationflags=NO_WINDOW)
        return r.returncode == 0
    # The whole process group, but never the caller's own: a Jeeves started by a script
    # or a check (not typed in Terminal) shares its caller's group, and ending that group
    # ended the caller as well (GitHub's test Macs, 2026-09-24: the test run itself was
    # ended). Then the program and its children are ended one by one instead.
    try:
        group = os.getpgid(pid)
    except (OSError, AttributeError):
        group = None
    if group is not None and group != os.getpgrp():
        try:
            os.killpg(group, signal.SIGKILL)
            return True
        except OSError:
            pass
    sent = False
    for p in _descendants(pid) + [pid]:
        if p == os.getpid():
            continue
        try:
            os.kill(p, signal.SIGKILL)
            sent = True
        except OSError:
            pass
    return sent


def _descendants(pid):
    """Every program started by this one, and by those, and so on (Mac and Linux)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True,
                             timeout=10, creationflags=NO_WINDOW).stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return []
    children = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [int(pid)]
    while todo:
        for kid in children.get(todo.pop(), []):
            if kid not in found:
                found.append(kid)
                todo.append(kid)
    return found


def alive(pid):
    """Is a program with this number running? Never sends it any signal on Windows."""
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False
