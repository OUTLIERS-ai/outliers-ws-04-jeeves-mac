# -*- coding: utf-8 -*-
"""Take every picture in the guide, headless (no window ever appears), on made-up data.

    python tools/shoot.py <empty work folder> guide/img
    python tools/shoot.py <empty work folder> guide/img diagram-files.png,terminal-install.png
        (retakes only the pictures named; the rest go to the work folder, not guide/img)

It builds its own made-up world in <work folder> ("Sam the bookkeeper", from
tools/demo.py), starts Jeeves on it inside this program, and photographs it.
The chat is answered by tools/fake_claude.py, so no AI is called and no token
is spent. Nothing here reads your real vaults or your real ~/.claude.

It also draws the guide's diagrams and terminal pictures from HTML, and runs
install.py and start.py for real (in the work folder) so the terminal pictures
show their real words.

Needs the Python `playwright` package with Chromium installed
(pip install playwright && python -m playwright install chromium).
"""

import html
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

import demo  # noqa: E402

BRASS = "#c9a96a"
CSS_BASE = """
*{box-sizing:border-box} body{margin:0;background:#070809;color:#ececee;
font:18px/1.45 "Segoe UI Variable","Segoe UI",system-ui,Arial,sans-serif}
.wrap{padding:36px 44px} h1{font-size:30px;margin:0 0 6px;font-weight:600}
.sub{color:#a0a0a8;margin:0 0 26px} .brass{color:#c9a96a}
.box{background:#121316;border:1px solid #2b2c33;border-radius:14px;padding:16px 18px}
.box h3{margin:0 0 6px;font-size:13px;letter-spacing:1.4px;text-transform:uppercase;color:#c9a96a}
.muted{color:#a0a0a8} code{font:15px ui-monospace,Consolas,monospace;background:#191a1e;
border:1px solid #2b2c33;border-radius:6px;padding:1px 6px}
.term{background:#0c0c0c;border:1px solid #2b2c33;border-radius:12px;overflow:hidden}
.term .bar{background:#1b1c20;color:#a0a0a8;font-size:14px;padding:8px 14px}
.term pre{margin:0;padding:18px 20px;font:16px/1.5 ui-monospace,"Cascadia Mono",Consolas,monospace;
color:#d8d8dc;white-space:pre-wrap}
.term .cmd{color:#c9a96a} .term .note{color:#3ecf8e}
"""


def page_html(body, width=1500):
    return ("<!doctype html><html><head><meta charset='utf-8'><style>%s body{width:%dpx}</style>"
            "</head><body>%s</body></html>" % (CSS_BASE, width, body))


# ------------------------------------------------------------------ annotation
ANNOTATE_JS = """
(items) => {
  const old = document.getElementById('shoot-notes'); if (old) old.remove();
  const layer = document.createElement('div'); layer.id = 'shoot-notes';
  layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:99999';
  document.body.appendChild(layer);
  for (const it of items) {
    const el = document.querySelector(it.sel); if (!el) continue;
    const r = el.getBoundingClientRect();
    const box = document.createElement('div');
    box.style.cssText = `position:fixed;left:${r.left - 3}px;top:${r.top - 3}px;width:${r.width + 6}px;height:${r.height + 6}px;border:2px solid #f5c542;border-radius:8px;box-shadow:0 0 0 2px rgba(0,0,0,.6)`;
    layer.appendChild(box);
    const b = document.createElement('div');
    b.textContent = it.n;
    const x = it.at === 'left' ? r.left - 16 : it.at === 'right' ? r.right - 16 : r.left + r.width / 2 - 16;
    const y = it.at === 'below' ? r.bottom - 16 : r.top - 16;
    b.style.cssText = `position:fixed;left:${Math.max(4, x + (it.dx || 0))}px;top:${Math.max(4, y + (it.dy || 0))}px;width:32px;height:32px;border-radius:50%;background:#f5c542;color:#111;font:700 18px/32px Segoe UI,Arial;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.7)`;
    layer.appendChild(b);
  }
}
"""


def legend_png(page, shot, items, out, width):
    """Put a numbered key under a screenshot, so labels never cover the picture."""
    import base64
    data = base64.b64encode(Path(shot).read_bytes()).decode()
    rows = "".join("<div class='k'><span class='n'>%s</span><span>%s</span></div>"
                   % (html.escape(str(i["n"])), html.escape(i["label"])) for i in items)
    body = ("<img src='data:image/png;base64,%s' style='display:block;width:%dpx'>"
            "<div class='keys'>%s</div>" % (data, width, rows))
    css = ("<style>.keys{display:grid;grid-template-columns:1fr 1fr;gap:10px 30px;padding:18px 26px 22px;"
           "background:#0b0c0e;border-top:1px solid #2b2c33}.k{display:flex;gap:12px;align-items:flex-start;"
           "font-size:18px}.n{flex:0 0 30px;height:30px;border-radius:50%;background:#f5c542;color:#111;"
           "font-weight:700;text-align:center;line-height:30px}</style>")
    page.set_viewport_size({"width": width, "height": 800})
    page.set_content(page_html(css + body, width).replace("<div class='wrap'>", ""))
    page.evaluate("document.body.style.width='%dpx'" % width)
    time.sleep(0.2)
    page.screenshot(path=str(out), full_page=True)


def shoot_annotated(page, out, items, tmpdir, width):
    page.evaluate(ANNOTATE_JS, items)
    time.sleep(0.2)
    raw = Path(tmpdir) / ("raw-" + Path(out).name)
    page.screenshot(path=str(raw))
    page.evaluate("document.getElementById('shoot-notes') && document.getElementById('shoot-notes').remove()")
    return raw


def wait_ready(page):
    page.wait_for_function("window.__jeevesReady === true", timeout=15000)
    time.sleep(1.2)


def wait_idle(page):
    page.wait_for_function("!document.querySelector('.composer .send').disabled", timeout=30000)
    time.sleep(0.5)


# ------------------------------------------------------------------ terminal runs
def run(args, env, cwd=None, stdin=""):
    r = subprocess.run(args, input=stdin, capture_output=True, text=True, env=env, cwd=cwd,
                       timeout=120, creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
    return (r.stdout + r.stderr).rstrip()


def typed_enter(text):
    """Piped answers are not echoed, so the prompts run together. Show each Enter."""
    import re
    return re.sub(r"(\]: |\(y/N\): )", lambda m: m.group(1) + "(Enter)\n", text)


DEMO_HOME = r"C:\Users\sam"          # the made-up home folder the terminal pictures show
DEMO_JEEVES = r"C:\Users\sam\Downloads\outliers-ws-04-jeeves"


def plain_paths(text, work):
    """The installer runs in a throwaway work folder with a long test name. The picture shows the
    same words with that folder swapped for a plain made-up home, so nobody reads our test folder
    as a path they should have. Only the folder names change; every word the installer printed stays."""
    # The made-up world keeps its .claude folder at home/Documents/home, so show that as the home too.
    for real, shown in [(str(work / "home" / "Documents" / "home"), DEMO_HOME), (str(work / "home"), DEMO_HOME), (str(work / "install-run"), DEMO_JEEVES),
                        (str(ROOT), DEMO_JEEVES)]:
        text = text.replace(real, shown).replace(real.replace("\\", "/"), shown)
    return text


def port_free(port):
    import socket
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def terminal(title, blocks):
    """blocks: list of (command, output)."""
    parts = []
    for cmd, out in blocks:
        if cmd:
            parts.append("<span class='cmd'>&gt; %s</span>" % html.escape(cmd))
        if out:
            parts.append(html.escape(out))
    return ("<div class='term'><div class='bar'>%s</div><pre>%s</pre></div>"
            % (html.escape(title), "\n".join(parts)))


def main(work, out, only=None):
    from playwright.sync_api import sync_playwright
    from jeeves import sessions
    from jeeves.server import serve_in_thread

    # The made-up world points its Work board and FleetView at the real default ports (3020, 3010),
    # so the pictures match the guide. Nothing real is ever photographed: if something is
    # answering on those ports on this computer, the app check is made to say "not running",
    # which is what a member who has not started them sees.
    busy = [p_ for p_ in (3020, 3010) if not port_free(p_)]
    if busy:
        from jeeves import apps as _apps
        _apps.probe = lambda url, timeout=0.5: False
        print("  Something is answering on port %s here. The pictures show the member's case"
              % " and ".join(str(x) for x in busy))
        print("  (not running); nothing from the program on that port is photographed.")

    work = Path(work).resolve()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    tmp = work / "_raw"
    tmp.mkdir(parents=True, exist_ok=True)
    home = work / "home"
    docs = home / "Documents"
    env = dict(os.environ)
    env.update({"HOME": str(home), "USERPROFILE": str(home),
                "APPDATA": str(home / "AppData" / "Roaming"),
                "CLAUDE_CONFIG_DIR": str(docs / "home" / ".claude"),
                "JEEVES_STATE": str(work / "state"), "PYTHONIOENCODING": "utf-8"})
    os.environ.update({k: env[k] for k in ("JEEVES_STATE", "CLAUDE_CONFIG_DIR")})
    now = datetime.now()
    cfg_path = demo.build(docs, now=now)            # Second Brain and CRM under Documents
    sessions.clear_cache()
    shots = []

    def save(name):
        if only and name not in only:
            return str(tmp / name)
        shots.append(name)
        return str(out / name)

    # ---- the installer and start.py, for real, in the made-up home
    inst_cfg = work / "install-run" / "config.json"
    env_i = dict(env, JEEVES_CONFIG=str(inst_cfg))
    install_out = plain_paths(run([sys.executable, str(ROOT / "install.py")], env_i, stdin="\n\n\n\n\n"), work)
    again_out = plain_paths(run([sys.executable, str(ROOT / "install.py")], env_i, stdin="\n\n\n\n\n"), work)
    versions = [("python --version", run([sys.executable, "--version"], env)),
                ("claude --version", run([shutil.which("claude") or "claude", "--version"], env)
                 if shutil.which("claude") else "(Claude Code is not installed on this computer)"),
                ("git --version", run(["git", "--version"], env))]

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        draw = b.new_page()

        def drawn(name, body, width=1500):
            draw.set_viewport_size({"width": width, "height": 100})
            draw.set_content(page_html(body, width))
            time.sleep(0.2)
            draw.screenshot(path=save(name), full_page=True)

        # terminal pictures ---------------------------------------------------------
        drawn("terminal-checks.png", "<div class='wrap'>" + terminal(
            "Terminal: checking what Jeeves needs (%s)" % now.strftime("%Y-%m-%d"),
            versions) + "</div>", 1400)
        drawn("terminal-install.png", "<div class='wrap'>" + terminal(
            "Terminal: python install.py, pressing Enter 5 times (made-up folders; yours will be your own)",
            [("python install.py", typed_enter(install_out))]) + "</div>", 1400)
        drawn("terminal-install-again.png", "<div class='wrap'>" + terminal(
            "Terminal: running the installer a second time", [("python install.py", "...\n" + typed_enter(again_out[again_out.find("  config.json already"):]))]) + "</div>", 1400)

        # the app ------------------------------------------------------------------
        srv = serve_in_thread(0, str(cfg_path))
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        port = srv.server_address[1]
        env_s = dict(env)
        again = run([sys.executable, str(ROOT / "start.py"), "--no-open", "--port", str(port),
                     "--config", str(cfg_path)], env_s)
        drawn("terminal-already-running.png", "<div class='wrap'>" + terminal(
            "Terminal: starting Jeeves when it is already running",
            [("python start.py", again.replace(str(port), "4040"))]) + "</div>", 1400)

        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        pg = ctx.new_page()
        pg.goto(base + "/")
        pg.evaluate("localStorage.clear()")
        pg.goto(base + "/")
        wait_ready(pg)
        pg.screenshot(path=save("cockpit-start.png"))

        tour = [
            {"sel": "#brand-name", "n": 1, "at": "right", "dx": 30, "label": "The orb and the name. The grey line under the name says what Jeeves is doing."},
            {"sel": ".dv-tab:has(.dv-default-tab-content)", "n": 2, "at": "right", "dx": 60, "label": "Chat: ask anything about your notes and CRM. Enter sends."},
            {"sel": "[data-card=people]", "n": 3, "at": "left", "label": "Across everything: read this first. Click a heading to open its panel."},
            {"sel": ".vb", "n": 4, "at": "left", "label": "Vaults: both vaults, read-only. Agents, Work board and FleetView are tabs here."},
            {"sel": "#model", "n": 5, "at": "below", "dy": 8, "label": "Model: best (Claude Opus 5.5, the strongest), deep (Claude Sonnet 5, the middle one) or fast (Claude Haiku 4.5, the cheapest). Each is named in full so you know what you are running."},
            {"sel": "#layout-btn", "n": 6, "at": "below", "dy": 8, "label": "Layouts: 4 ready-made arrangements of all 10 panels, and your own."},
            {"sel": "#add-btn", "n": 7, "at": "below", "dy": 8, "label": "+ Panel: bring back any panel you closed, or pop one out."},
            {"sel": ".grp-actions", "n": 8, "at": "left", "dx": -18, "label": "Make a group fill the screen. Double-clicking a tab does the same; Esc puts it back."},
        ]
        raw = shoot_annotated(pg, None or str(out / "cockpit-tour.png"), tour, tmp, 1600)
        legend_png(draw, raw, tour, save("cockpit-tour.png"), 1600)

        # chat: a question, while it answers, then the answer
        os.environ["FAKE_CLAUDE_DELAY"] = "0.12"
        pg.fill(".composer textarea", "Who should I speak to first today, and why?")
        pg.click(".composer .send")
        pg.wait_for_function("document.querySelector('.msg.bot') && document.querySelector('.msg.bot').innerText.length > 60", timeout=30000)
        items = [
            {"sel": ".act", "n": 1, "at": "left", "dx": -12, "label": "An arrow line: a file Claude is reading, as it happens."},
            {"sel": ".composer .stop", "n": 2, "at": "left", "label": "Stop: ends the answer. Jeeves keeps what was written so far."},
            {"sel": ".chat-head .orb-big", "n": 3, "at": "below", "dy": 16, "label": "The orb brightens while the answer comes in."},
            {"sel": "#status-line", "n": 4, "at": "right", "dx": 60, "label": "The status line under the name: what Claude is doing right now, for example \"Read: Today.md\"."},
            {"sel": ".composer .send", "n": 5, "at": "left", "dx": -30, "label": "Send is greyed out until the answer finishes. Press Enter now and the reason appears at the bottom of the conversation, where you are looking."},
        ]
        raw = shoot_annotated(pg, "chat-answering.png", items, tmp, 1600)
        legend_png(draw, raw, items, save("chat-answering.png"), 1600)
        wait_idle(pg)
        os.environ["FAKE_CLAUDE_DELAY"] = "0.01"
        items = [
            {"sel": ".msg.bot p:last-child .wl", "n": 1, "at": "below", "dy": 20, "label": "A link to another note (a note name in double square brackets): click it and the note opens in Vaults."},
            {"sel": ".chat-head .sub", "n": 2, "at": "right", "dx": 30, "label": "What Chat may do: 3 tools, all of them reading. No commands, no file changes, no internet, unless you allow more in config.json."},
            {"sel": ".ptools .newchat", "n": 3, "at": "top", "dy": -24, "label": "New conversation: Claude forgets the conversation and starts fresh."},
        ]
        raw = shoot_annotated(pg, "cockpit-chat.png", items, tmp, 1600)
        legend_png(draw, raw, items, save("cockpit-chat.png"), 1600)

        # Stop
        os.environ["FAKE_CLAUDE_DELAY"] = "0.15"
        pg.fill(".composer textarea", "Draft a note to every client about the new prices")
        pg.click(".composer .send")
        pg.wait_for_function("document.querySelectorAll('.msg.bot')[1] && document.querySelectorAll('.msg.bot')[1].innerText.length > 40", timeout=30000)
        pg.click(".composer .stop")
        wait_idle(pg)
        os.environ["FAKE_CLAUDE_DELAY"] = "0.01"
        items = [{"sel": ".msg.note:last-of-type", "n": 1, "at": "right", "dx": 26, "dy": 16, "label": "After Stop: a grey line, not an error. The part above is kept."}]
        raw = shoot_annotated(pg, "chat-stopped.png", items, tmp, 1600)
        legend_png(draw, raw, items, save("chat-stopped.png"), 1600)

        # a login failure, with Try again
        os.environ["FAKE_CLAUDE_RESULT_ERROR"] = "Not logged in · Please run /login"
        pg.fill(".composer textarea", "What needs me today?")
        pg.click(".composer .send")
        wait_idle(pg)
        del os.environ["FAKE_CLAUDE_RESULT_ERROR"]
        pg.evaluate("document.querySelector('.msg.err details').open = true")
        items = [{"sel": ".msg.err", "n": 1, "at": "left", "label": "What went wrong, in plain words. Details shows Claude Code's own message. /login means: type claude in a terminal, then type /login."},
                 {"sel": ".msg.err .again", "n": 2, "at": "right", "dx": 30, "dy": 16, "label": "Try again sends the same message once you have fixed it."}]
        raw = shoot_annotated(pg, "chat-failed.png", items, tmp, 1600)
        legend_png(draw, raw, items, save("chat-failed.png"), 1600)

        # Layouts menu, and a maximised group
        pg.click("#layout-btn")
        time.sleep(0.4)
        pg.screenshot(path=save("layouts-menu.png"))
        pg.keyboard.press("Escape")
        pg.dblclick(".dv-tab >> text=Today")
        time.sleep(0.6)
        pg.screenshot(path=save("maximised.png"))
        pg.keyboard.press("Escape")
        time.sleep(0.3)
        ctx.close()

        # laptop
        lctx = b.new_context(viewport={"width": 1400, "height": 820})
        lp = lctx.new_page()
        lp.goto(base + "/")
        lp.evaluate("localStorage.clear()")
        lp.evaluate("localStorage.setItem('x','1')")
        lp.goto(base + "/")
        wait_ready(lp)
        lp.click("#layout-btn")
        lp.click("[data-layout=laptop]")
        time.sleep(0.8)
        lp.screenshot(path=save("layout-laptop.png"))
        # everything closed
        for _ in range(15):
            c = lp.locator(".dv-tab .dv-default-tab-action")
            if not c.count():
                break
            c.first.click(force=True)
            time.sleep(0.1)
        time.sleep(0.3)
        lp.screenshot(path=save("all-closed.png"))
        lctx.close()

        # each panel on its own, as a popped-out window shows it
        solo = b.new_context(viewport={"width": 1400, "height": 860})
        sp = solo.new_page()
        for name in ["vaults", "agents", "activity", "tokens", "overview", "today", "inbox", "board"]:
            sp.goto(base + "/?only=" + name)
            wait_ready(sp)
            if name == "vaults":
                sp.click(".vb-file >> text=Pricing review")
                time.sleep(0.8)
            if name == "board":
                sp.wait_for_selector(".pbody .empty, .pbody iframe", timeout=15000)
            sp.screenshot(path=save("panel-%s.png" % name))
        solo.close()

        # the orb, close up
        o = b.new_context(viewport={"width": 900, "height": 700}, device_scale_factor=2)
        op = o.new_page()
        op.goto(base + "/?only=chat")
        op.evaluate("localStorage.clear()")
        op.goto(base + "/?only=chat")
        wait_ready(op)
        op.evaluate("fetch('/api/chat/new',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})")
        op.goto(base + "/?only=chat")
        wait_ready(op)
        head = op.locator(".chat-head").bounding_box()
        chips = op.locator(".chips").bounding_box()
        top = head["y"] + 2
        op.screenshot(path=save("orb.png"), clip={"x": 0, "y": top, "width": 900,
                                                  "height": chips["y"] + chips["height"] + 12 - top})
        o.close()
        srv.shutdown()
        srv.server_close()

        # a brand-new member: no Today.md, no Recommendations file, no agents, no history
        fresh = work / "fresh"
        cfg2 = demo.build(fresh, now=now)
        (fresh / "CRM" / "Today.md").unlink()
        (fresh / "Second Brain" / "Inbox" / "Recommendations.md").unlink()
        c2 = json.loads(cfg2.read_text(encoding="utf-8"))
        c2["claude_home"] = str(fresh / "empty-claude")
        c2["claude_command"] = "not-installed-claude-xyz"
        cfg2.write_text(json.dumps(c2), encoding="utf-8")
        sessions.clear_cache()
        srv2 = serve_in_thread(0, str(cfg2))
        base2 = "http://127.0.0.1:%d" % srv2.server_address[1]
        n = b.new_context(viewport={"width": 1600, "height": 1000})
        np_ = n.new_page()
        np_.goto(base2 + "/")
        np_.evaluate("localStorage.clear()")
        np_.goto(base2 + "/")
        wait_ready(np_)
        items = [{"sel": ".banner", "n": 1, "at": "left", "label": "No Claude Code: Chat says so, lists the 3 steps and links to the download page. Every other panel works."},
                 {"sel": "[data-card=people]", "n": 2, "at": "left", "label": "No Today.md yet: it says so, with the command that builds it."},
                 {"sel": "[data-card=decide]", "n": 3, "at": "right", "label": "No Recommendations file yet: it names the file to create."}]
        raw = shoot_annotated(np_, "new-member.png", items, tmp, 1600)
        legend_png(draw, raw, items, save("new-member.png"), 1600)
        n.close()

        # the same setup, Chat on its own: the banner close up
        nc = b.new_context(viewport={"width": 1400, "height": 820})
        ncp = nc.new_page()
        ncp.goto(base2 + "/?only=chat")
        ncp.evaluate("localStorage.clear()")
        ncp.goto(base2 + "/?only=chat")
        wait_ready(ncp)
        items = [
            {"sel": ".banner a", "n": 1, "at": "right", "dx": 30, "label": "The address is a link: click it to open Claude Code's install page."},
            {"sel": ".composer textarea", "n": 2, "at": "left", "dx": 8, "dy": -6, "label": "The text box and Send are switched off, and say so. The suggested questions are put away, because they would only fill a box that cannot send."},
        ]
        raw = shoot_annotated(ncp, "no-claude.png", items, tmp, 1400)
        legend_png(draw, raw, items, save("no-claude.png"), 1400)
        nc.close()
        srv2.shutdown()
        srv2.server_close()

        # a folder that is not there: every panel says the same
        broken = json.loads(cfg_path.read_text(encoding="utf-8"))
        # A made-up path that really does not exist on this computer, so the picture
        # shows a member's folder name rather than the test folder this ran in.
        broken["second_brain"] = DEMO_HOME + r"\Documents\Second Brain (on the old laptop)"
        broken_path = work / "broken-config.json"
        broken_path.write_text(json.dumps(broken), encoding="utf-8")
        sessions.clear_cache()
        srv3 = serve_in_thread(0, str(broken_path))
        base3 = "http://127.0.0.1:%d" % srv3.server_address[1]
        bctx = b.new_context(viewport={"width": 1600, "height": 1000})
        bp = bctx.new_page()
        bp.goto(base3 + "/")
        bp.evaluate("localStorage.clear()")
        bp.goto(base3 + "/")
        wait_ready(bp)
        time.sleep(1.0)
        # the second-brain card sits under the CRM card in Today: bring it into view
        bp.evaluate("() => { const e = document.querySelector('.card > .empty.gone');"
                    " if (e) e.scrollIntoView({block: 'center'}); }")
        time.sleep(0.4)
        items = [
            {"sel": "[data-card=brain] .empty.gone", "n": 1, "at": "left", "label": "Across everything: no counts, because a folder that is not there cannot be counted."},
            {"sel": ".card > .empty.gone", "n": 2, "at": "left", "label": "Today: the folder it looked in, and the setting to correct."},
            {"sel": ".vb-tabs button", "n": 3, "at": "below", "dy": 10, "label": "Vaults: the tab says (missing) too. All 3 panels agree."},
        ]
        raw = shoot_annotated(bp, "folder-missing.png", items, tmp, 1600)
        legend_png(draw, raw, items, save("folder-missing.png"), 1600)
        bctx.close()
        srv3.shutdown()
        srv3.server_close()

        # ---- diagrams ------------------------------------------------------------
        drawn("diagram-why.png", DIAGRAM_WHY)
        drawn("diagram-timeline.png", DIAGRAM_TIMELINE)
        drawn("diagram-cost.png", DIAGRAM_COST)
        drawn("diagram-files.png", DIAGRAM_FILES)
        drawn("diagram-fit.png", DIAGRAM_FIT)
        drawn("diagram-download.png", DIAGRAM_DOWNLOAD)
        b.close()
    for s in shots:
        print(out / s)


def cards(items, cols):
    return ("<div style='display:grid;grid-template-columns:repeat(%d,1fr);gap:14px'>%s</div>"
            % (cols, "".join("<div class='box'><h3>%s</h3><div>%s</div></div>" % (t, d) for t, d in items)))


DIAGRAM_WHY = """<div class='wrap'><h1>Jeeves reads 5 places and shows them on 1 page</h1>
<p class='sub'>Jeeves only reads. Your CRM, your notes and Claude Code's own log files stay where they are.</p>
<div style='display:grid;grid-template-columns:1fr 90px 1fr;align-items:center;gap:10px'>
<div style='display:grid;gap:12px'>
<div class='box'><h3>Your CRM: a folder of notes about people</h3>who to speak to today (<code>Today.md</code>)</div>
<div class='box'><h3>Your second brain</h3>today's note, what changed, what is unticked</div>
<div class='box'><h3>Claude Code's log files</h3>what it did today, and how many tokens</div>
<div class='box'><h3>The folders your agents are kept in</h3>every agent (<code>.claude/agents</code>) and what it is for</div>
<div class='box'><h3>Your other apps</h3>ProjectForge and FleetView, if running</div></div>
<div style='font-size:64px;color:#c9a96a;text-align:center'>&rarr;</div>
<div class='box' style='padding:26px'><h3>Jeeves, 1 page in your browser</h3>
<p style='margin:6px 0 14px'>10 panels you can move, stack, close, bring back and pop out:</p>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:6px 18px' class='muted'>
<div>Chat</div><div>Across everything</div><div>Today</div><div>Recommendations</div>
<div>Vaults</div><div>Agents</div><div>Activity</div><div>Tokens</div><div>Work board</div><div>FleetView</div></div>
<p style='margin:16px 0 0'>Plus 1 place to ask: <span class='brass'>your own Claude Code</span>, which already knows your rulebook, agents and skills.</p></div>
</div></div>"""

DIAGRAM_TIMELINE = """<div class='wrap'><h1>How the original was built (June to July 2026), and this rebuild</h1>
<p class='sub'>From the build notes of the original. Green: kept in this download. Amber: tried and dropped.</p>
<div style='display:grid;gap:10px'>
%s</div></div>""" % "".join(
    "<div style='display:grid;grid-template-columns:190px 18px 1fr;gap:14px;align-items:start'>"
    "<div class='brass' style='text-align:right;font-weight:600'>%s</div>"
    "<div style='width:14px;height:14px;border-radius:50%%;margin-top:6px;background:%s'></div>"
    "<div>%s</div></div>" % (d, c, t) for d, c, t in [
        ("2026-06-13", "#3ecf8e", "Local server on 127.0.0.1, port 4040. Claude Code answered every question. First panels."),
        ("2026-06-13", "#e0a84a", "A copy of a narrator's voice, control of the mouse and keyboard, and a command window running inside the page. All 3 left out of this download."),
        ("2026-06-14 to 17", "#e0a84a", "A timer that started Claude every 15 minutes, and phone alerts (switched off the same day)."),
        ("2026-06-14 to 17", "#3ecf8e", "Lesson: fill each panel only once it is on screen. Default model back to the strongest."),
        ("2026-06-20", "#3ecf8e", "A calm, stripped-back redesign was rejected: Ashley wanted every job Jeeves does on screen, not 4 boxes. The Across everything panel was added instead."),
        ("2026-06-21", "#3ecf8e", "The orb, drawn by the page itself. A 3-column layout went live."),
        ("2026-07-08", "#e0a84a", "Paused: its timers kept starting Claude and using tokens."),
        ("2026-07-09", "#e0a84a", "Would not start: it needed a folder outside its own."),
        ("2026-09-22", "#3ecf8e", "This rebuild: no timers, nothing outside its folder, and a Chat that can only read your notes."),
        ("2026-09-23", "#3ecf8e", "Checked again: Chat given 3 reading tools and no others, models named in full, and a panel that cannot find a folder now names it."),
    ])

DIAGRAM_COST = """<div class='wrap'><h1>What costs tokens, and what does not</h1>
<p class='sub'>Tokens are the units your Claude subscription counts. Only 1 action in Jeeves uses them.</p>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:18px'>
<div class='box' style='border-color:#2f6b50'><h3 style='color:#3ecf8e'>0 tokens</h3>
<ul style='margin:6px 0;padding-left:1.2em;line-height:1.8'>
<li>Opening Jeeves and every reading panel</li><li>Today, Across everything, Recommendations</li>
<li>Vaults: opening, filtering, searching notes</li><li>Agents, Activity, Tokens</li>
<li>The automatic re-read of your files once a minute, while the Jeeves browser tab is on screen</li><li>Moving, closing and popping out panels</li></ul></div>
<div class='box' style='border-color:#6b5a2f'><h3>Uses tokens</h3>
<ul style='margin:6px 0;padding-left:1.2em;line-height:1.8'>
<li>Each message you send in Chat starts Claude Code once</li>
<li>Each run re-reads your rulebook (<code>CLAUDE.md</code>) and the conversation so far</li>
<li>The model you pick changes the price: <code>fast</code> (Claude Haiku 4.5) is cheapest, <code>deep</code> (Claude Sonnet 5) the middle, <code>best</code> (Claude Opus 5.5) strongest</li>
<li>Nothing else. There is no timer that starts Claude.</li></ul></div></div></div>"""

DIAGRAM_FILES = """<div class='wrap'><h1>What is in the folder, and what Jeeves writes</h1>
<p class='sub'>Everything Jeeves writes stays inside its own folder, except the start-by-itself file if you said yes to it. It never writes to your vaults.</p>
%s</div>""" % cards([
    ("You run these", "<code>install.py</code> asks 5 questions and writes the settings<br><code>install.py --copy</code> makes a copy to experiment on<br><code>start.py</code> starts, stops, or says it is already running"),
    ("Written by the installer", "<code>config.json</code>: every setting<br><code>config.json.bak-&lt;date&gt;</code>: your old settings, when an answer changes<br><code>Start Jeeves (hidden).vbs</code> (Windows): start with no window"),
    ("Written while it runs", "<code>state/chat-sessions.json</code>: the conversation number<br><code>state/jeeves.pid</code>: the ID of the running Jeeves, and its port<br><code>state/read-only-settings.json</code>: the 7 tools that act, written down as refused, so a second Claude cannot use them either"),
    ("Only if you said yes to starting by itself", "<code>Jeeves.vbs</code> in your Startup folder (Windows)<br>a launch file in <code>Library/LaunchAgents</code> (Mac)<br>Removed by <code>python install.py --uninstall</code>"),
    ("The program", "<code>jeeves/</code>: the server and the page<br><code>tests/</code>: 77 checks on made-up data (9 need Playwright)<br><code>tools/demo.py</code>: a made-up world to try first"),
    ("To read", "<code>README.md</code>, this guide in <code>guide/</code><br><code>WHAT-I-STOLE.md</code>: what it was built from, and the licences<br><code>config.example.json</code>: every setting with an example"),
], 3)

DIAGRAM_FIT = """<div class='wrap'><h1>Where each change goes</h1>
<p class='sub'>You ask your own Claude Code for the change; this is the file it will open.</p>
%s</div>""" % cards([
    ("config.json", "The assistant's name, the 2 lines of lettering around the circle of light, which Claude models to use, what Chat may do, your folders and your other apps' addresses. No code."),
    ("jeeves/static/app.js", "A new panel, buttons, the chat panel, the Layouts menu."),
    ("jeeves/server.py", "The code that fetches whatever a new panel shows, for example the drafts from your content engine."),
    ("Your second brain's CLAUDE.md", "How Claude behaves when it answers from Jeeves: where it may write, how it replies."),
    ("tests/", "A check for every change, on made-up data, so it cannot break quietly."),
    ("Nothing in your own note folders", "Jeeves reads them. Changes to your notes come from Claude (if allowed) or your agents."),
], 3)

DIAGRAM_DOWNLOAD = """<div class='wrap' style='text-align:center'><h1>Download Jeeves</h1>
<p class='sub'>https://github.com/OUTLIERS-ai/outliers-ws-04-jeeves</p>
<div class='term' style='text-align:left;max-width:1200px;margin:0 auto'><div class='bar'>Terminal</div>
<pre><span class='cmd'>&gt; git clone https://github.com/OUTLIERS-ai/outliers-ws-04-jeeves</span>
<span class='cmd'>&gt; cd outliers-ws-04-jeeves</span>
<span class='cmd'>&gt; python install.py</span>
<span class='cmd'>&gt; python start.py</span>
<span class='note'>  Jeeves is running at http://127.0.0.1:4040/  (Ctrl+C to stop)</span></pre></div></div>"""


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2],
         set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None)
