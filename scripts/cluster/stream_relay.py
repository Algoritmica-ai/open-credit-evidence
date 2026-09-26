#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Algoritmica GmbH
"""Streamed tool calls for the judge NIM, for agent runtimes that always stream.

The Nano judge NIM parsed tool calls with the parser packaged with its model
(``nemotron_json``), which works only on complete replies: a streamed request
that offered tools was refused with "Tool calling is not supported in streaming
mode!". OpenClaw, the agent runtime inside NemoClaw, streams every request. The
judge is now the Nemotron 3 Super NIM; the relay stays in front of it so that
an agent gets its tool calls whichever parser the judge NIM ships with.

This relay sits between the two. A streamed chat request that offers tools is
sent to the NIM unstreamed; the complete reply, tool calls parsed, is then
replayed to the caller as a stream of chunks in the OpenAI format, ending in
``data: [DONE]``. Every other request, streamed or not, is passed through
unchanged. The caller waits for the whole reply before the first chunk, which
an agent turn does anyway before it can run a tool.

The evidence engine does not use the relay: it calls the judge NIM directly,
unstreamed. servers.sbatch starts the relay next to the models on the judge's
port + 2 and stops it with them.

    python3 stream_relay.py --upstream http://127.0.0.1:8201 --port 8203

More than one judge server: list the others, one URL per line, in the upstreams
file (``--upstreams-file``, default ``~/.config/stream-relay/upstreams``). The
file is read again whenever it changes, so a second judge joins without a restart.
Requests take turns across the servers; one that refuses a connection is left out
for ``DOWN_S`` seconds.

Standard library only: the node has Python 3 and nothing else.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

TIMEOUT = 900  # an agent turn with a long context can take minutes
DOWN_S = 30  # a server that refused a connection is skipped this long
DEFAULT_UPSTREAMS_FILE = "~/.config/stream-relay/upstreams"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy


def needs_relay(body: dict[str, Any]) -> bool:
    """A streamed request that offers tools: the NIM would refuse it."""
    return bool(body.get("stream")) and bool(body.get("tools"))


def unstreamed(body: dict[str, Any]) -> dict[str, Any]:
    """The same request, asking for the complete reply."""
    return {k: v for k, v in body.items() if k not in ("stream", "stream_options")} | {
        "stream": False}


def chunks(reply: dict[str, Any], include_usage: bool = False) -> Iterator[dict[str, Any]]:
    """A complete chat completion as the chunks a streaming server would have sent."""
    head = {"id": reply.get("id", "relay"), "object": "chat.completion.chunk",
            "created": reply.get("created", int(time.time())), "model": reply.get("model")}
    for choice in reply.get("choices", []):
        i = choice.get("index", 0)
        msg = choice.get("message") or {}
        first: dict[str, Any] = {"role": msg.get("role", "assistant"),
                                 "content": msg.get("content") or ""}
        if msg.get("reasoning_content"):
            first["reasoning_content"] = msg["reasoning_content"]
        yield head | {"choices": [{"index": i, "delta": first, "finish_reason": None}]}
        calls = msg.get("tool_calls") or []
        if calls:
            yield head | {"choices": [{"index": i, "finish_reason": None, "delta": {"tool_calls": [
                {"index": k, "id": c.get("id"), "type": c.get("type", "function"),
                 "function": {"name": (c.get("function") or {}).get("name"),
                              "arguments": (c.get("function") or {}).get("arguments") or ""}}
                for k, c in enumerate(calls)]}}]}
        yield head | {"choices": [{"index": i, "delta": {},
                                   "finish_reason": choice.get("finish_reason")
                                   or ("tool_calls" if calls else "stop")}]}
    if include_usage and reply.get("usage"):
        yield head | {"choices": [], "usage": reply["usage"]}


def sse(reply: dict[str, Any], include_usage: bool = False) -> bytes:
    """The replayed stream as bytes, ``data: [DONE]`` last."""
    out = [f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks(reply, include_usage)]
    return ("".join(out) + "data: [DONE]\n\n").encode("utf-8")


def reassemble(stream: bytes) -> dict[str, Any]:
    """The message a client builds from a stream: content and tool calls. For tests."""
    content, reasoning, calls, finish = "", "", {}, None
    for line in stream.decode("utf-8").splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        for ch in json.loads(line[6:]).get("choices", []):
            d = ch.get("delta") or {}
            content += d.get("content") or ""
            reasoning += d.get("reasoning_content") or ""
            for tc in d.get("tool_calls") or []:
                c = calls.setdefault(tc["index"], {"id": None, "type": "function",
                                                   "function": {"name": "", "arguments": ""}})
                c["id"] = tc.get("id") or c["id"]
                f = tc.get("function") or {}
                c["function"]["name"] += f.get("name") or ""
                c["function"]["arguments"] += f.get("arguments") or ""
            finish = ch.get("finish_reason") or finish
    return {"content": content, "reasoning_content": reasoning or None,
            "tool_calls": [calls[k] for k in sorted(calls)], "finish_reason": finish}


class Upstreams:
    """The judge servers behind the relay: the one given on the command line and any
    listed in the upstreams file. Each request starts at the next server in turn."""

    def __init__(self, primary: str, file: str | None = None) -> None:
        self.primary = primary.rstrip("/")
        self.file = os.path.expanduser(file) if file else None
        self._seen: float | None = None
        self._extra: list[str] = []
        self._next = 0
        self._down: dict[str, float] = {}
        self._lock = threading.Lock()

    def all(self) -> list[str]:
        if self.file:
            try:
                changed = os.stat(self.file).st_mtime
            except OSError:
                changed = None
            if changed != self._seen:
                self._seen = changed
                self._extra = [] if changed is None else [
                    x.strip().rstrip("/") for x in open(self.file, encoding="utf-8")
                    if x.strip() and not x.lstrip().startswith("#")]
        return [self.primary] + [u for u in self._extra if u != self.primary]

    def order(self) -> list[str]:
        """Every server, starting with the next in turn; those marked down go last."""
        with self._lock:
            ups = self.all()
            self._next = (self._next + 1) % len(ups)
            turn = ups[self._next:] + ups[:self._next]
            now = time.time()
            return ([u for u in turn if self._down.get(u, 0) <= now]
                    + [u for u in turn if self._down.get(u, 0) > now])

    def mark_down(self, url: str) -> None:
        with self._lock:
            self._down[url] = time.time() + DOWN_S


def _refused(e: BaseException) -> bool:
    """The server is not there: safe to send the request to another one."""
    reason = getattr(e, "reason", e)
    return isinstance(reason, (ConnectionRefusedError, ConnectionResetError))


def make_handler(upstream: str | Upstreams, log=print) -> type[BaseHTTPRequestHandler]:
    ups = upstream if isinstance(upstream, Upstreams) else Upstreams(upstream)

    class Relay(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # one response per connection; the stream ends at close

        def log_message(self, *_: Any) -> None:  # one line per request, below
            pass

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _open(self, method: str, data: bytes | None,
                  headers: dict[str, str]) -> Any:
            """Open the request on the next server in turn, moving on from one that is not
            there. An HTTP error is the server's answer and is returned, not retried."""
            last: BaseException | None = None
            for url in ups.order():
                req = urllib.request.Request(url + self.path, data=data, method=method,
                                             headers=headers)
                try:
                    return _OPENER.open(req, timeout=TIMEOUT)
                except urllib.error.HTTPError:
                    raise
                except (urllib.error.URLError, OSError) as e:
                    last = e
                    if not _refused(e):
                        raise
                    ups.mark_down(url)
            raise urllib.error.URLError(f"no judge server answered: {last}")

        def _forward(self, method: str, data: bytes | None) -> None:
            """Pass the request through, streaming the response as it arrives."""
            try:
                resp = self._open(method, data, self._headers())
            except urllib.error.HTTPError as e:
                resp = e
            except (urllib.error.URLError, OSError) as e:
                self._send(502, json.dumps({"error": f"relay: upstream unreachable: {e}"})
                           .encode(), "application/json")
                return
            with resp:
                self.send_response(resp.status)
                for k in ("Content-Type", "Content-Length"):
                    if resp.headers.get(k):
                        self.send_header(k, resp.headers[k])
                self.end_headers()
                while block := resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536):
                    self.wfile.write(block)
                    self.wfile.flush()
            self.status = resp.status

        def _headers(self) -> dict[str, str]:
            # Header names are case-insensitive: OpenShell's router sends them in lower
            # case. A body with no type would go out as a form, which the NIM refuses.
            keep = {"content-type": "Content-Type", "authorization": "Authorization",
                    "accept": "Accept"}
            out = {keep[k.lower()]: v for k, v in self.headers.items() if k.lower() in keep}
            if self.command == "POST":
                out.setdefault("Content-Type", "application/json")
            return out

        def _handle(self, method: str) -> None:
            t0, self.status, how = time.time(), 0, "pass"
            try:
                if self.path == "/relay/health":
                    self._send(200, json.dumps({"ok": True, "upstream": ups.primary,
                                                "upstreams": ups.all()}).encode(),
                               "application/json")
                    self.status = 200
                    return
                n = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(n) if n else None
                body: dict[str, Any] = {}
                if data and self.path.endswith("/chat/completions"):
                    try:
                        body = json.loads(data)
                    except ValueError:
                        body = {}
                if method == "POST" and needs_relay(body):
                    how = "relay"
                    try:
                        with self._open("POST", json.dumps(unstreamed(body)).encode(),
                                        self._headers() | {"Content-Type":
                                                           "application/json"}) as r:
                            reply = json.loads(r.read())
                    except urllib.error.HTTPError as e:  # the NIM's own error, as it sent it
                        self.status = e.code
                        self._send(e.code, e.read(), e.headers.get("Content-Type")
                                   or "application/json")
                        return
                    except (urllib.error.URLError, OSError, ValueError) as e:
                        self.status = 502
                        self._send(502, json.dumps({"error": f"relay: {e}"}).encode(),
                                   "application/json")
                        return
                    usage = bool((body.get("stream_options") or {}).get("include_usage"))
                    self.status = 200
                    self._send(200, sse(reply, usage), "text/event-stream")
                else:
                    self._forward(method, data)
            except (BrokenPipeError, ConnectionResetError):
                how += " (client left)"
            finally:
                log(f"{time.strftime('%H:%M:%S')} {method} {self.path} {how} {self.status} "
                    f"{time.time() - t0:.1f}s")

        def do_GET(self) -> None:  # noqa: N802 — http.server's naming
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

    return Relay


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--upstream", default="http://127.0.0.1:8201",
                    help="the judge NIM, without /v1")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8203)
    ap.add_argument("--upstreams-file", default=os.environ.get("RELAY_UPSTREAMS_FILE",
                                                               DEFAULT_UPSTREAMS_FILE),
                    help="more judge servers, one URL per line (read again when it changes)")
    a = ap.parse_args()
    ups = Upstreams(a.upstream, a.upstreams_file)
    server = ThreadingHTTPServer((a.host, a.port), make_handler(
        ups, log=lambda s: print(s, file=sys.stderr, flush=True)))
    print(f"relay on {a.host}:{a.port} -> {', '.join(ups.all())}", file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
