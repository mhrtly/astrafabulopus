#!/usr/bin/env python3
"""In-process HTTPS endpoint stub for Jev CLI tests; no network sockets are opened."""
import io
import json
import os
import sys
from urllib.error import HTTPError, URLError
from unittest.mock import patch

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(REPO, "lib"))

from astrafab import council, decide  # noqa: E402

mode, body_path, auth_path, command, spec_path = sys.argv[1:6]
extra = sys.argv[6:]


class Headers(dict):
    pass


class Response:
    def __init__(self, value, code=200):
        self.raw = json.dumps(value).encode("utf-8")
        self.offset = 0
        self.code = code
        self.headers = Headers({"x-request-id": "header-request-id"})

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        if limit < 0:
            limit = len(self.raw) - self.offset
        value = self.raw[self.offset:self.offset + limit]
        self.offset += len(value)
        return value

    def getcode(self):
        return self.code


def fake_urlopen(request, timeout=None):
    assert request.full_url == os.environ["AF_JEV_ENDPOINT"]
    assert timeout is not None
    body = json.loads(request.data.decode("utf-8"))
    with open(body_path, "w") as fh:
        json.dump(body, fh)
    key = request.get_header("Authorization") or ""
    sources = {
        "Bearer env-key-sentinel": "env",
        "Bearer trailing-key-sentinel": "env",
        "Bearer op-key-sentinel": "op",
        "Bearer keychain-key-sentinel": "keychain",
        "Bearer error-key-sentinel": "env",
        "Bearer timeout-key-sentinel": "env",
        "Bearer council-key-sentinel": "env",
        "Bearer worker-key-sentinel": "env",
    }
    with open(auth_path, "w") as fh:
        fh.write(sources.get(key, "unknown"))
    if mode == "500":
        raise HTTPError(request.full_url, 500, "stub error", {}, io.BytesIO(b"must not be shown"))
    if mode == "value-error":
        raise ValueError("Invalid header value: " + key)
    if mode == "timeout":
        raise URLError(TimeoutError("timed out"))
    if mode == "302":
        return Response({}, 302)
    lanes = body["questions"]["lane"]["criteria"]
    efforts = body["questions"]["effort"]["criteria"]
    lane = "routine" if "routine" in lanes else next(iter(lanes))
    effort = "high" if "high" in efforts else next(iter(efforts))
    echoed = key.removeprefix("Bearer ") if mode == "metadata-echo" else None
    response = Response({
        "model": echoed or "jev-test-1",
        "request_id": echoed or "body-request-id",
        "answers": {
            "lane": {"type": "choice", "choice": lane,
                     "probabilities": {key: (0.82 if key == lane else 0.18 / max(1, len(lanes) - 1))
                                       for key in lanes}},
            "effort": {"type": "choice", "choice": effort,
                       "probabilities": {key: (0.88 if key == effort else 0.06) for key in efforts}},
            "spec_complete": {"type": "noul", "noul": 0.91},
        },
        "usage": {"input_tokens": 100, "output_tokens": 0},
    })
    if echoed:
        response.headers["x-request-id"] = echoed
    return response


class FakeOpener:
    def open(self, request, timeout=None):
        return fake_urlopen(request, timeout)


with patch("astrafab.jev.build_opener", lambda *_handlers: FakeOpener()):
    if command == "decide":
        result = decide.main(["lane", spec_path] + extra)
    elif command == "council":
        result = council.main(["recommend", "--spec", spec_path] + extra)
    else:
        raise SystemExit("unknown stub command")
raise SystemExit(result)
