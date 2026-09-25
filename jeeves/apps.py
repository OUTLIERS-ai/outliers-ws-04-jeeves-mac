# -*- coding: utf-8 -*-
"""apps.py - is the work board (ProjectForge) or FleetView running on this machine?

Jeeves only LOOKS. It never starts, restarts or installs another program. The
original started one of its neighbours itself and restarted it every 120
seconds; the neighbour then quietly reused that copy, so a fix to it looked
dead. A panel that only looks cannot cause that.
"""

import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request

_CACHE = {}


def probe(url, timeout=0.5):
    hit = _CACHE.get(url)
    if hit and time.time() - hit[0] < 10:
        return hit[1]
    up = False
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            up = 200 <= r.status < 500
    except urllib.error.HTTPError as e:
        up = e.code < 500
    except Exception:  # noqa: BLE001 - down, refused, timed out: all mean "not running"
        up = False
    _CACHE[url] = (time.time(), up)
    return up


def status(cfg):
    items = list((cfg.get("apps") or {}).items())
    # Ask every app at once, so two apps that are off cost one wait, not two.
    with ThreadPoolExecutor(max_workers=max(1, len(items))) as pool:
        ups = list(pool.map(lambda kv: bool((kv[1] or {}).get("url")) and
                            probe(kv[1]["url"]), items))
    return {k: {"url": (a or {}).get("url", ""), "repo": (a or {}).get("repo", ""), "up": up}
            for (k, a), up in zip(items, ups)}
