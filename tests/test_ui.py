# -*- coding: utf-8 -*-
"""The cockpit in a real (headless, invisible) browser, on made-up data.

Skipped when the Python `playwright` package or its Chromium is not installed:
members do not need it to use Jeeves, only to run these checks. Each of the 9 is
reported as skipped on its own, so `python -m pytest -q` says "9 skipped" whether
Playwright is missing altogether or only its Chromium is.
These guard the usability faults found on 2026-09-22 so they cannot come back.
"""
import time

import pytest

try:
    import playwright.sync_api as pw
except ImportError:
    pw = None
    pytestmark = pytest.mark.skip(
        reason="checks the page in a real browser: needs Playwright "
               "(pip install playwright, then python -m playwright install chromium)")


@pytest.fixture
def page(server, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_DELAY", "0.02")
    try:
        p = pw.sync_playwright().start()
        b = p.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001 - no Chromium: skip, do not fail
        pytest.skip("Chromium for playwright is not installed: %s" % exc)
    ctx = b.new_context(viewport={"width": 1366, "height": 768})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(server[0] + "/")
    pg.wait_for_function("window.__jeevesReady === true", timeout=15000)
    time.sleep(0.8)
    yield pg, errors
    b.close()
    p.stop()


def _send(pg, text):
    pg.fill(".composer textarea", text)
    pg.click(".composer .send")
    pg.wait_for_function("!document.querySelector('.composer .send').disabled", timeout=30000)


def test_text_box_stays_on_screen_after_3_replies_on_a_laptop(page):
    """Critic finding 1: after 1 reply at 1366x768 the Send button slid off the screen."""
    pg, errors = page
    for i in range(3):
        _send(pg, "Question %d?" % i)
    box = pg.locator(".composer .send").bounding_box()
    assert box["y"] + box["height"] <= 768
    assert not errors


def test_enter_while_answering_does_not_send(page, monkeypatch):
    pg, _ = page
    monkeypatch.setenv("FAKE_CLAUDE_DELAY", "0.05")
    pg.fill(".composer textarea", "slow")
    pg.click(".composer .send")
    time.sleep(0.3)
    pg.fill(".composer textarea", "impatient")
    pg.focus(".composer textarea")
    pg.keyboard.press("Enter")
    time.sleep(0.2)
    assert pg.evaluate("document.querySelectorAll('.msg.you').length") == 1
    assert "Still answering" in pg.inner_text("#status-line")
    pg.wait_for_function("!document.querySelector('.composer .send').disabled", timeout=30000)


def test_the_conversation_is_still_there_after_a_reload(page):
    pg, _ = page
    _send(pg, "Remember me")
    pg.reload()
    pg.wait_for_function("window.__jeevesReady === true", timeout=15000)
    time.sleep(0.5)
    assert "Remember me" in pg.inner_text(".log")
    assert "Carrying on the conversation" in pg.inner_text(".log")


def test_a_link_opens_in_the_vault_that_has_it_and_the_tab_agrees(server):
    """Critic finding 3: a [[link]] clicked with the CRM tab lit broke the Vaults panel."""
    try:
        p = pw.sync_playwright().start()
        b = p.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip("Chromium for playwright is not installed: %s" % exc)
    try:
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.goto(server[0] + "/")
        pg.wait_for_function("window.__jeevesReady === true", timeout=15000)
        time.sleep(0.8)
        pg.click(".vb-tabs button[data-k=crm]")
        time.sleep(0.3)
        pg.evaluate("""(() => { const s = document.createElement('span'); s.className = 'wl';
            s.dataset.note = 'Pricing review'; document.querySelector('.log').appendChild(s);
            s.dispatchEvent(new MouseEvent('click', {bubbles: true})); })()""")
        pg.wait_for_function("document.querySelector('.vb-path') && document.querySelector('.vb-path').innerText.includes('Pricing review')", timeout=5000)
        lit = pg.evaluate("[...document.querySelectorAll('.vb-tabs button.on')].map(b => b.dataset.k)")
        assert lit == ["brain"]
        pg.click(".vb-tabs button[data-k=crm]")
        time.sleep(0.3)
        pg.click(".vb-file >> text=Marcus Webb")
        pg.wait_for_function("document.querySelector('.vb-path').innerText.includes('Marcus Webb')", timeout=5000)
    finally:
        b.close()
        p.stop()


def test_every_panel_can_be_closed_and_the_empty_screen_says_what_to_do(page):
    pg, errors = page
    for _ in range(15):
        closers = pg.locator(".dv-tab .dv-default-tab-action")
        if not closers.count():
            break
        closers.first.click(force=True)
        time.sleep(0.1)
    assert pg.locator(".dv-watermark-jeeves").count() == 1
    pg.click(".dv-watermark-jeeves [data-reset]")
    time.sleep(0.5)
    assert pg.evaluate("document.querySelectorAll('.dv-tab').length") == 10
    assert not errors


# =================================================================== second audit
# The 4 faults the second teardown found on the screen itself, 2026-09-22.

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from jeeves.server import serve_in_thread  # noqa: E402


def _chrome():
    try:
        p = pw.sync_playwright().start()
        b = p.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001 - no Chromium: skip, do not fail
        pytest.skip("Chromium for playwright is not installed: %s" % exc)
    return p, b


class _Served:
    """The same made-up world, with 1 or 2 settings changed, on its own port."""

    def __init__(self, world, **changes):
        cfg = json.loads(Path(world).read_text(encoding="utf-8"))
        cfg.update(changes)
        self.path = Path(world).with_name("config-changed.json")
        self.path.write_text(json.dumps(cfg), encoding="utf-8")

    def __enter__(self):
        self.srv = serve_in_thread(0, str(self.path))
        return "http://127.0.0.1:%d" % self.srv.server_address[1]

    def __exit__(self, *_):
        self.srv.shutdown()
        self.srv.server_close()


def test_a_message_sent_from_a_popped_out_window_is_not_erased(server, monkeypatch):
    """Re-audit N2: both windows wrote their whole conversation over each other, so a
    message sent in the pop-out vanished from the saved record the moment the main
    window sent its next one."""
    monkeypatch.setenv("FAKE_CLAUDE_DELAY", "0.01")
    p, b = _chrome()
    try:
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        main = ctx.new_page()
        main.goto(server[0] + "/")
        main.wait_for_function("window.__jeevesReady === true", timeout=15000)
        _send(main, "main window message one")
        pop = ctx.new_page()                       # what the ⧉ button opens
        pop.goto(server[0] + "/?only=chat")
        pop.wait_for_function("window.__jeevesReady === true", timeout=15000)
        _send(pop, "pop-out window message two")
        _send(main, "main window message three")
        time.sleep(0.5)
        saved = json.loads(main.evaluate("localStorage.getItem('jeeves.chat.main')"))
        said = [i["text"] for i in saved if i["role"] == "you"]
        assert said == ["main window message one", "pop-out window message two",
                        "main window message three"], saved
        main.reload()
        main.wait_for_function("window.__jeevesReady === true", timeout=15000)
        time.sleep(0.5)
        assert "pop-out window message two" in main.inner_text(".log")
    finally:
        b.close()
        p.stop()


def test_send_looks_switched_off_while_an_answer_is_coming(page, monkeypatch):
    """Re-audit N3: Send was switched off but looked identical to a working button, and
    the reason sat 921 px away in the top bar."""
    pg, _ = page
    monkeypatch.setenv("FAKE_CLAUDE_DELAY", "0.08")
    pg.fill(".composer textarea", "slow one")
    pg.click(".composer .send")
    pg.wait_for_function("document.querySelector('.composer .send').disabled", timeout=10000)
    look = pg.evaluate("""(() => { const s = getComputedStyle(document.querySelector('.composer .send'));
        return {opacity: +s.opacity, cursor: s.cursor}; })()""")
    assert look["opacity"] < 0.9 and look["cursor"] == "not-allowed"
    pg.fill(".composer textarea", "impatient")
    pg.focus(".composer textarea")
    pg.keyboard.press("Enter")
    time.sleep(0.2)
    # the reason is beside the box, in the chat, not only in the top bar
    assert "Still answering" in pg.inner_text(".log")
    assert pg.evaluate("document.querySelectorAll('.msg.you').length") == 1
    pg.wait_for_function("!document.querySelector('.composer .send').disabled", timeout=30000)


def test_a_missing_second_brain_folder_is_said_on_every_panel(world):
    """Re-audit N1: Today read "Nothing has moved and nothing is left open" while Vaults,
    300 px below, said the folder did not exist."""
    cfg = json.loads(Path(world).read_text(encoding="utf-8"))
    gone = str(Path(cfg["second_brain"]).parent / "moved-this-folder")
    p, b = _chrome()
    try:
        with _Served(world, second_brain=gone) as base:
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg.goto(base + "/?only=today")
            pg.wait_for_function("window.__jeevesReady === true", timeout=15000)
            time.sleep(0.6)
            today = pg.inner_text(".pbody")
            assert "Nothing has moved" not in today
            assert "moved-this-folder" in today and "not there" in today.lower()
            pg.goto(base + "/?only=overview")
            pg.wait_for_function("window.__jeevesReady === true", timeout=15000)
            time.sleep(0.8)
            summary = pg.inner_text(".pbody")
            assert "Left unfinished" not in summary
            assert "not there" in summary.lower()
    finally:
        b.close()
        p.stop()


def test_with_no_claude_code_the_link_works_and_the_suggestions_go_quiet(world):
    """Re-audit N6: the install address was plain text, and the 4 suggestion buttons still
    filled a text box that was switched off."""
    p, b = _chrome()
    try:
        with _Served(world, claude_command="claude-is-not-installed-here") as base:
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            pg.goto(base + "/?only=chat")
            pg.wait_for_function("window.__jeevesReady === true", timeout=15000)
            time.sleep(0.5)
            href = pg.get_attribute(".banner a", "href")
            assert href == "https://code.claude.com/docs/en/setup"
            assert pg.locator(".chips .chip").count() == 0 or \
                not pg.locator(".chips").first.is_visible()
            assert pg.evaluate("document.querySelector('.composer textarea').disabled") is True
    finally:
        b.close()
        p.stop()
