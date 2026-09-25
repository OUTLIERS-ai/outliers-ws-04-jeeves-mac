# -*- coding: utf-8 -*-
"""The server's routes, against made-up vaults and fake session logs."""
import json
import urllib.error

import pytest

from conftest import events, get, get_json, post


def test_main_page_and_vendored_dockview(server):
    base, _ = server
    code, html = get(base + "/")
    assert code == 200 and "dockview.css" in html and "/static/app.js" in html
    code, js = get(base + "/static/vendor/dockview/dockview-core.esm.min.js")
    assert code == 200 and "createDockview" in js
    code, orb = get(base + "/static/orb.js")
    assert "JeevesOrb" in orb


def test_today_reads_the_crm_page_and_the_second_brain(server):
    d = get_json(server[0] + "/api/today")
    assert d["crm"]["found"] and "Priya Shah" in d["crm"]["text"]
    assert d["brain"]["daily"]["path"].startswith("Daily/")
    assert any("Pricing review" in m["path"] for m in d["brain"]["moved"])
    assert any("Draft the letter" in o["text"] for o in d["brain"]["open"])


def test_vault_tree_file_and_search(server):
    base = server[0]
    vs = get_json(base + "/api/vaults")
    assert [v["key"] for v in vs] == ["brain", "crm"] and all(v["exists"] for v in vs)
    tree = get_json(base + "/api/vault/tree?v=brain")
    paths = [f["path"] for f in tree["files"]]
    assert "Projects/Pricing review.md" in paths
    assert not any(p.startswith(".claude/") for p in paths), "agent files are not notes"
    note = get_json(base + "/api/vault/file?v=brain&p=Projects/Pricing%20review.md")
    assert "Books only" in note["text"]
    hits = get_json(base + "/api/vault/search?q=VAT")["hits"]
    assert {h["key"] for h in hits} == {"brain"} and len(hits) >= 2


@pytest.mark.parametrize("bad", ["../config.json", "..%2F..%2Fconfig.json", "CLAUDE.txt",
                                 "/etc/passwd", "..\\..\\x.md"])
def test_vault_file_refuses_anything_outside_the_vault(server, bad):
    d = get_json(server[0] + "/api/vault/file?v=brain&p=" + bad)
    assert "error" in d and "text" not in d


def test_agents_from_both_folders(server):
    d = get_json(server[0] + "/api/agents")
    names = {a["name"]: a for a in d["agents"]}
    assert {"invoice-chaser", "note-filer", "meeting-summariser"} <= set(names)
    assert names["invoice-chaser"]["where"] == "all projects"
    assert names["note-filer"]["where"] == "Second brain"
    assert "Never sends" in names["invoice-chaser"]["description"]


def test_activity_counts_turns_and_names_the_folder(server):
    d = get_json(server[0] + "/api/activity")
    rows = {r["title"]: r for r in d["sessions"]}
    r = rows["Clean up duplicate people in the CRM"]
    assert r["turns"] == 7 and r["folder_name"] == "CRM"
    assert d["sessions"][0]["title"] == "Draft the letter about new packages"  # newest first


def test_tokens_count_each_reply_once(server):
    d = get_json(server[0] + "/api/tokens")
    # The demo writes every reply twice, as Claude Code does. Counted once, the
    # 5-turn session alone is: input 40..44, output 600..800, cache write 3000 x5,
    # cache read 18000..34000.
    one = sum(40 + k + 600 + 50 * k + 3000 + 18000 + 4000 * k for k in range(5))
    assert d["today"]["total"] >= one
    assert d["by_model"]["opus"]["output"] == sum(600 + 50 * k for k in range(5)) + \
        sum(600 + 50 * k for k in range(3))
    assert d["ccusage"]["available"] is False  # switched off in the demo


def test_inbox_reads_the_recommendations_file(server):
    d = get_json(server[0] + "/api/inbox")
    assert d["found"] and d["path"] == "Inbox/Recommendations.md" and "Chase 2 unpaid" in d["text"]


def test_apps_not_running_says_so_with_the_link(server):
    d = get_json(server[0] + "/api/apps")
    assert d["projectforge"]["up"] is False
    assert d["projectforge"]["repo"].endswith("outliers-ws-03-projectforge")
    assert d["fleetview"]["repo"].endswith("outliers-ws-02-fleetview")


def test_wrong_host_is_refused(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server[0] + "/api/today", {"Host": "attacker.example"})
    assert e.value.code == 403


def test_chat_from_another_website_is_refused(server):
    code, body = post(server[0] + "/api/chat", {"message": "hi"}, {"Origin": "https://attacker.example"})
    assert code == 403


def test_chat_needs_json(server):
    code, _ = post(server[0] + "/api/chat", {"message": "hi"}, {"Content-Type": "text/plain"})
    assert code == 415


def test_config_hides_nothing_secret_and_reports_claude(server):
    d = get_json(server[0] + "/api/config")
    assert d["claude_found"] is True and set(d["models"]) == {"best", "deep", "fast"}
