"""A stub of the Qwen service's /v1/chat/completions endpoint, for client tests."""
import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROMPT_TOKENS = 10
COMPLETION_TOKENS = 5


_NORMAL_USAGE = object()


@dataclass(frozen=True)
class Reply:
    content: str = ""
    status: int = 200
    delay: float = 0.0
    cut_short: bool = False
    usage: object = _NORMAL_USAGE


def ok(content, delay=0.0, usage=_NORMAL_USAGE):
    """A normal chat completion whose answer text is `content`."""
    return Reply(content=content, delay=delay, usage=usage)


def http_error(status, delay=0.0):
    return Reply(status=status, delay=delay)


def cut_short():
    """A reply whose body ends before its declared length, as when the service dies mid-reply."""
    return Reply(cut_short=True)


class StubQwen:
    """Replies are scripted per prompt text, consumed in order; the last one repeats."""

    def __init__(self):
        self._scripts = {}
        self._calls = {}
        self._lock = threading.Lock()
        self._in_flight = 0
        self._stopped = False
        self.peak_in_flight = 0
        self.requests = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.stub = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self._server.server_port}/v1"

    def script(self, prompt, *replies):
        self._scripts[prompt] = list(replies)

    def call_count(self, prompt):
        return self._calls.get(prompt, 0)

    def start(self):
        self._thread.start()

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self._server.shutdown()
        self._server.server_close()

    def begin(self, body):
        """Record a request and return the scripted reply for its prompt."""
        prompt = body["messages"][-1]["content"]
        with self._lock:
            self.requests.append(body)
            self._in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
            index = self._calls.get(prompt, 0)
            self._calls[prompt] = index + 1
            replies = self._scripts.get(prompt)
            if not replies:
                return Reply(status=500)
            return replies[min(index, len(replies) - 1)]

    def end(self):
        with self._lock:
            self._in_flight -= 1


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        stub = self.server.stub
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reply = stub.begin(body)
        time.sleep(reply.delay)
        # Leave the in-flight count before replying, so the peak never overcounts.
        stub.end()
        if reply.status != 200:
            self.send_error(reply.status)
            return
        usage = {"prompt_tokens": PROMPT_TOKENS,
                 "completion_tokens": COMPLETION_TOKENS,
                 "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS}
        payload = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": reply.content}}],
            "usage": usage if reply.usage is _NORMAL_USAGE else reply.usage,
        }).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload[:10] if reply.cut_short else payload)
        except OSError:
            pass  # the client gave up (timeout) before the reply was ready

    def log_message(self, format, *args):
        pass
