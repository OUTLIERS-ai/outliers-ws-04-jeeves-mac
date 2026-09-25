# -*- coding: utf-8 -*-
"""The chat route, with a stand-in for Claude Code (tools/fake_claude.py). No AI is called."""
import json

from conftest import events, post


def _log(tmp_path, monkeypatch):
    p = tmp_path / "fake-claude-calls.jsonl"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(p))
    return p


def _calls(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def test_chat_streams_words_then_a_final_answer(server, tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)
    code, body = post(server[0] + "/api/chat", {"message": "Who first?", "model": "fast"})
    assert code == 200
    ev = events(body)
    kinds = [e["type"] for e in ev]
    assert kinds[0] == "activity" and "Read" in ev[0]["text"]
    assert kinds.count("delta") > 10 and kinds[-1] == "done"
    assert "Priya Shah" in ev[-1]["text"]
    call = _calls(log)[0]
    a = call["argv"]
    assert a[:1] == ["-p"] and "stream-json" in a and "--include-partial-messages" in a
    assert a[a.index("--model") + 1] == "claude-haiku-4-5"   # "fast" names the model in full
    assert a[a.index("--permission-mode") + 1] == "dontAsk"
    cfg = json.loads(server[1].read_text(encoding="utf-8"))
    assert a[a.index("--add-dir") + 1] == cfg["crm_vault"]
    assert "--session-id" in a and "--append-system-prompt" in a
    assert call["stdin"] == "Who first?"                   # the message goes in on stdin
    assert call["cwd"].replace("\\", "/").rstrip("/").lower() == \
        cfg["second_brain"].replace("\\", "/").rstrip("/").lower()


def test_second_message_resumes_the_same_session(server, tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)
    post(server[0] + "/api/chat", {"message": "one"})
    post(server[0] + "/api/chat", {"message": "two"})
    first, second = _calls(log)
    sid = first["argv"][first["argv"].index("--session-id") + 1]
    assert second["argv"][second["argv"].index("--resume") + 1] == sid
    assert "--append-system-prompt" not in second["argv"]
    # New conversation forgets it
    post(server[0] + "/api/chat/new", {})
    post(server[0] + "/api/chat", {"message": "three"})
    assert "--session-id" in _calls(log)[2]["argv"]


def test_failure_is_shown_and_not_remembered(server, tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_FAIL", "1")
    ev = events(post(server[0] + "/api/chat", {"message": "x"})[1])
    assert ev[-1]["type"] == "error" and "fake failure" in ev[-1]["text"]
    monkeypatch.delenv("FAKE_CLAUDE_FAIL")
    post(server[0] + "/api/chat", {"message": "y"})
    assert "--session-id" in _calls(log)[1]["argv"], "a failed first message must not be resumed"


def test_missing_claude_code_is_explained(tmp_path):
    from jeeves import chat, config
    cfg = config.load(str(tmp_path / "none.json"))
    cfg["claude_command"] = "definitely-not-a-real-program-xyz"
    ev = list(chat.stream(cfg, "hello"))
    assert len(ev) == 1 and ev[0]["type"] == "error" and ev[0]["code"] == "not_found"
    assert "not found" in ev[0]["text"]


def test_empty_message_never_starts_claude(tmp_path, monkeypatch):
    from jeeves import chat, config
    log = _log(tmp_path, monkeypatch)
    ev = list(chat.stream(config.load(str(tmp_path / "none.json")), "   "))
    assert ev[0]["type"] == "done" and not log.exists()
