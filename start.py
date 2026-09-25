# -*- coding: utf-8 -*-
"""Start (or stop) Jeeves.

    python start.py            start on the port in config.json and open your browser
    python start.py --no-open  start without opening a browser (the file that starts
                               Jeeves when the computer starts uses this)
    python start.py --stop     stop the Jeeves that is running on this folder's port
    python start.py --port 4041

It listens on 127.0.0.1 only: this computer, never your network.

Only 1 copy runs per port. Start it a second time and it says it is already
running (and opens the page) instead of starting another copy.

--stop asks the port first whether Jeeves is really there, and ends only the
program that answers. The old way trusted the number saved in state/jeeves.pid;
after a restart that number can belong to any other program on the computer.
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.request

import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from jeeves import config as C  # noqa: E402
from jeeves import proc as P  # noqa: E402
from jeeves.server import make_server  # noqa: E402


def pid_file():
    return C.state_dir() / "jeeves.pid"


def free_port(after, tries=60):
    """A port nothing is listening on, counting up from the one that just failed.

    The advice used to be the fixed text "--port 4041", so a member already on 4041
    was told to try the port that had just refused them.
    """
    start_at = int(after or 4040)
    for port in range(start_at + 1, start_at + 1 + tries):
        if port > 65535:
            break
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    return start_at + 1


def who_is_on(port):
    """What answers on this port: Jeeves's health reply (with its process number), or None."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/health" % int(port), timeout=2) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d if d.get("app") == "jeeves" and d.get("pid") else None
    except Exception:  # noqa: BLE001 - nothing there, or not Jeeves
        return None


def stop(config_file=None):
    p = pid_file()
    ports = []
    if p.exists():
        try:
            parts = p.read_text().split()
            ports.append(int(parts[1]))
        except (OSError, ValueError, IndexError):
            pass
    cfg_port = C.load(config_file).get("port", 4040)
    if cfg_port not in ports:
        ports.append(cfg_port)
    stopped = 0
    for port in ports:
        h = who_is_on(port)
        if not h:
            continue
        P.kill_tree(h["pid"])
        for _ in range(50):
            if not P.alive(h["pid"]):
                break
            time.sleep(0.1)
        print("  Stopped Jeeves on port %d (process %d)." % (port, h["pid"]))
        stopped += 1
    if not stopped:
        print("  Jeeves is not running (nothing answered on port %s)."
              % " or ".join(str(x) for x in ports))
    try:
        p.unlink()
    except OSError:
        pass
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Start the Jeeves cockpit.")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--config", default=None, help="another config.json (tests, demos)")
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    ap.add_argument("--stop", action="store_true", help="stop the running copy")
    a = ap.parse_args(argv)
    cfg_file = a.config or os.environ.get("JEEVES_CONFIG")
    if a.stop:
        return stop(cfg_file)
    cfg = C.load(cfg_file)
    # A config.json that cannot be read used to be reported as "No config.json yet",
    # which sent members to the installer instead of to the line they had just typed.
    broken = C.problem(cfg_file)
    if broken:
        print("  " + broken)
        return 1
    if not cfg.get("second_brain"):
        print("  No config.json yet. Run:  %s install.py" % C.PY)
        return 1
    try:
        srv = make_server(a.port, cfg_file)
    except OSError as exc:
        port = a.port or cfg.get("port")
        h = who_is_on(port)
        if h:
            url = "http://127.0.0.1:%d/" % int(port)
            print("  Jeeves is already running at %s (process %d). Not starting a second copy."
                  % (url, h["pid"]))
            print("  To stop it:  %s start.py --stop" % C.PY)
            if not a.no_open:
                try:
                    webbrowser.open(url)
                except Exception:  # noqa: BLE001
                    pass
            return 0
        print("  Could not listen on port %s: %s" % (port, exc))
        print("  Another program is using it. Try:  %s start.py --port %d" % (C.PY, free_port(port)))
        return 1
    port = srv.server_address[1]
    C.atomic_write(pid_file(), "%d %d\n" % (os.getpid(), port))
    url = "http://127.0.0.1:%d/" % port
    print("  %s is running at %s  (Ctrl+C to stop)" % (cfg.get("name", "Jeeves"), url))
    if not a.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        try:
            if pid_file().read_text().split()[0] == str(os.getpid()):
                pid_file().unlink()
        except (OSError, IndexError):
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
