# -*- coding: utf-8 -*-
"""A stand-in for `claude -p`, used by the tests and the demo. It never calls any AI.

It reads the message from standard input and prints the same kind of event
stream Claude Code prints with --output-format stream-json, one word at a time,
so the chat panel can be tested and photographed without spending a token.
It also records the command line it was given, so a test can check the flags.
"""
import json
import os
import sys
import time

msg = sys.stdin.read()
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": sys.argv[1:], "stdin": msg, "cwd": os.getcwd()}) + "\n")

if os.environ.get("FAKE_CLAUDE_FAIL"):
    sys.stderr.write("fake failure for the test\n")
    sys.exit(3)

# Claude Code reports some failures as a finished run marked as an error, for
# example "Not logged in" or "No conversation found with session ID ...".
if os.environ.get("FAKE_CLAUDE_RESULT_ERROR"):
    text = os.environ["FAKE_CLAUDE_RESULT_ERROR"]
    sys.stdout.write(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": text}]}}) + "\n")
    sys.stdout.write(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                                 "result": text}) + "\n")
    sys.stdout.flush()
    sys.exit(1)

# An npm install runs claude.cmd, which starts the real Claude as a CHILD program.
# FAKE_CLAUDE_CHILD=<file> copies that shape: the work runs in a child that writes
# its process number to <file> and keeps working, so a test can check Stop ends it.
if os.environ.get("FAKE_CLAUDE_CHILD"):
    import subprocess
    code = ("import os,sys,time\n"
            "open(sys.argv[1],'w').write(str(os.getpid()))\n"
            "time.sleep(60)\n")
    child = subprocess.Popen([sys.executable, "-c", code, os.environ["FAKE_CLAUDE_CHILD"]],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    child.wait()
    sys.exit(0)

reply = os.environ.get("FAKE_CLAUDE_REPLY") or (
    "Three people are worth your morning, in this order:\n\n"
    "1. **Priya Shah** (Priya Shah Design) replied yesterday asking about month-end help. "
    "A reply goes off fastest, so she comes first.\n"
    "2. **Tom Reyes** booked a call for Thursday. Read [[Tom Reyes]] before then; "
    "he mentioned VAT twice last time.\n"
    "3. **Hannah Cole** changed role to finance lead at a 12-person agency.\n\n"
    "In your second brain, *Pricing review* is still open with 2 unticked items. "
    "I read `Today.md` in your CRM and your note [[Pricing review]].")

def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

out({"type": "system", "subtype": "init", "model": "fake"})
out({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Read", "input": {"file_path": "Today.md"}}]}})
delay = float(os.environ.get("FAKE_CLAUDE_DELAY", "0.01"))
for word in reply.split(" "):
    out({"type": "stream_event", "event": {"type": "content_block_delta",
         "delta": {"type": "text_delta", "text": word + " "}}})
    time.sleep(delay)
out({"type": "result", "subtype": "success", "is_error": False, "result": reply})
