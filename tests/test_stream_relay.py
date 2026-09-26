# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""The streaming relay for NemoClaw, against a fake NIM that refuses streamed tool calls."""

import importlib.util
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cluster" / "stream_relay.py"
spec = importlib.util.spec_from_file_location("stream_relay", SCRIPT)
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)

REPLY = {
    "id": "chatcmpl-1", "object": "chat.completion", "created": 1790000000, "model": "nano-judge",
    "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": "Looking it up.", "reasoning_content": "need the file",
        "tool_calls": [
            {"id": "call_a", "type": "function",
             "function": {"name": "read_file", "arguments": "{\"path\": \"case.md\"}"}},
            {"id": "call_b", "type": "function",
             "function": {"name": "grep", "arguments": "{\"pattern\": \"DTI\"}"}}]}}],
    "usage": {"prompt_tokens": 900, "completion_tokens": 40, "total_tokens": 940},
}
PLAIN_STREAM = (b'data: {"choices":[{"index":0,"delta":{"role":"assistant","content":"Hel"}}]}\n\n'
                b'data: {"choices":[{"index":0,"delta":{"content":"lo"},"finish_reason":"stop"}]}'
                b'\n\ndata: [DONE]\n\n')


class FakeNIM(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *_):
        pass

    def _send(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self._send(200, json.dumps({"data": [{"id": "nano-judge"}]}).encode())

    def do_POST(self):  # noqa: N802
        if self.headers.get("Content-Type") != "application/json":  # as the NIM does
            self._send(415, b'{"message": "Unsupported media type"}')
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeNIM.seen.append(body)
        if body.get("stream") and body.get("tools"):
            self._send(400, b'{"error": "Tool calling is not supported in streaming mode!"}')
        elif body.get("stream"):
            self._send(200, PLAIN_STREAM, "text/event-stream")
        else:
            self._send(200, json.dumps(REPLY).encode())


def _serve(handler):
    s = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


@pytest.fixture
def servers():
    FakeNIM.seen = []
    nim = _serve(FakeNIM)
    rel = _serve(relay.make_handler(f"http://127.0.0.1:{nim.server_port}", log=lambda s: None))
    yield f"http://127.0.0.1:{rel.server_port}", f"http://127.0.0.1:{nim.server_port}"
    rel.shutdown()
    nim.shutdown()


def _post(url, body):
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, r.headers.get("Content-Type"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type"), e.read()


TOOLS = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]


def test_replayed_stream_rebuilds_the_complete_reply():
    msg = relay.reassemble(relay.sse(REPLY))
    want = REPLY["choices"][0]["message"]
    assert msg["content"] == want["content"]
    assert msg["reasoning_content"] == want["reasoning_content"]
    assert msg["tool_calls"] == want["tool_calls"]
    assert msg["finish_reason"] == "tool_calls"
    lines = relay.sse(REPLY, include_usage=True).decode().strip().split("\n\n")
    assert lines[-1] == "data: [DONE]" and '"usage"' in lines[-2]


def test_the_nim_refuses_what_the_relay_serves(servers):
    rel, nim = servers
    body = {"model": "nano-judge", "stream": True, "tools": TOOLS,
            "stream_options": {"include_usage": True}, "messages": [{"role": "user",
                                                                     "content": "hi"}]}
    status, _, _ = _post(nim, body)
    assert status == 400  # what OpenClaw saw before the relay
    status, ctype, data = _post(rel, body)
    assert status == 200 and ctype == "text/event-stream"
    assert relay.reassemble(data)["tool_calls"][1]["function"]["name"] == "grep"
    sent = FakeNIM.seen[-1]
    assert sent["stream"] is False and "stream_options" not in sent and sent["tools"] == TOOLS


def test_everything_else_passes_through_unchanged(servers):
    rel, _ = servers
    plain = {"model": "nano-judge", "stream": True, "messages": [{"role": "user",
                                                                  "content": "hi"}]}
    status, ctype, data = _post(rel, plain)
    assert (status, ctype, data) == (200, "text/event-stream", PLAIN_STREAM)
    assert FakeNIM.seen[-1] == plain
    whole = {"model": "nano-judge", "tools": TOOLS, "messages": [{"role": "user",
                                                                  "content": "hi"}]}
    status, _, data = _post(rel, whole)
    assert status == 200 and json.loads(data) == REPLY and FakeNIM.seen[-1] == whole
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(rel + "/v1/models", timeout=10) as r:
        assert json.loads(r.read())["data"][0]["id"] == "nano-judge"
    with opener.open(rel + "/relay/health", timeout=10) as r:
        assert json.loads(r.read())["ok"]


def test_header_names_in_any_case_reach_the_nim(servers):
    import http.client

    rel, _ = servers
    host, port = rel.removeprefix("http://").split(":")
    body = json.dumps({"model": "nano-judge", "messages": [{"role": "user",
                                                            "content": "hi"}]}).encode()
    for name in ("content-type", "Content-Type", None):  # the router sends lower case
        c = http.client.HTTPConnection(host, int(port), timeout=10)
        c.putrequest("POST", "/v1/chat/completions")
        if name:
            c.putheader(name, "application/json")
        c.putheader("Content-Length", str(len(body)))
        c.endheaders(body)
        r = c.getresponse()
        assert r.status == 200, (name, r.read())
        r.read()


def test_requests_take_turns_across_judge_servers_and_skip_one_that_is_gone(tmp_path):
    hits = {"a": 0, "b": 0}

    def named(name):
        class Named(FakeNIM):
            def do_POST(self):  # noqa: N802
                hits[name] += 1
                super().do_POST()
        return Named

    a, b = _serve(named("a")), _serve(named("b"))
    extra = tmp_path / "upstreams"
    ups = relay.Upstreams(f"http://127.0.0.1:{a.server_port}", str(extra))
    rel = _serve(relay.make_handler(ups, log=lambda s: None))
    url = f"http://127.0.0.1:{rel.server_port}"
    try:
        for _ in range(2):  # one server until the file names the second
            assert _post(url, {"messages": []})[0] == 200
        assert hits == {"a": 2, "b": 0}
        extra.write_text(f"# the second judge\nhttp://127.0.0.1:{b.server_port}\n")
        for _ in range(4):
            assert _post(url, {"messages": [], "stream": True, "tools": TOOLS})[0] == 200
        assert hits["a"] == 4 and hits["b"] == 2  # alternating, streamed tool calls included
        b.shutdown()
        b.server_close()
        for _ in range(3):  # the second is gone: every request still answered, by the first
            assert _post(url, {"messages": []})[0] == 200
        assert hits["a"] == 7
    finally:
        rel.shutdown()
        a.shutdown()
