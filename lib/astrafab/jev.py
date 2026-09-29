"""Small, advisory client for TypeSafe AI's Jev System One endpoint.

Python 3.9 and the standard library only. API keys are resolved in memory and are never included
in command arguments, diagnostics, or ledger records.
"""
import json
import hashlib
import math
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeout
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import core

DEFAULTS = {
    "enabled": False,
    "endpoint": "https://api.typesafe.ai/v1/systemone",
    "model": "jev-latest",
    "min_probability": 0.8,
    "timeout_s": 5,
    "key_ref": None,
    "keychain_service": "typesafe-api-key",
}
LANES = ("routine", "complex", "frontier", "local")
LANE_CRITERIA = {
    "routine": "Small, clear, low-risk work with a narrow implementation scope.",
    "complex": "Substantial implementation, debugging, or coordinated multi-file work.",
    "frontier": "Unusually difficult work with high uncertainty or repeated failed attempts.",
    "local": "Work that specifically requires the configured local model lane.",
}


class _RedirectRefused(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _RedirectRefused()


class Unavailable(Exception):
    """A safe-to-display reason a Jev suggestion could not be obtained."""


def _request_error(exc):
    """Classify request failures without reading exception text, which may contain headers."""
    if isinstance(exc, (TimeoutError, FutureTimeout)):
        return "timeout"
    if isinstance(exc, (_RedirectRefused, HTTPError, HTTPException, ValueError)):
        return "http error"
    if isinstance(exc, URLError):
        if isinstance(getattr(exc, "reason", None), (TimeoutError, FutureTimeout)):
            return "timeout"
        return "network error"
    if isinstance(exc, OSError):
        return "network error"
    return "internal error"


def config(root=None):
    lanes, _ = core.load_lanes(root)
    result = dict(DEFAULTS)
    value = lanes.get("jev")
    if isinstance(value, dict):
        result.update(value)
    env_endpoint = os.environ.get("AF_JEV_ENDPOINT")
    if env_endpoint:
        result["endpoint"] = env_endpoint
    try:
        result["min_probability"] = float(result.get("min_probability", 0.8))
        result["timeout_s"] = float(result.get("timeout_s", 5))
    except (TypeError, ValueError):
        raise Unavailable("invalid Jev configuration")
    if (not math.isfinite(result["min_probability"]) or not 0 <= result["min_probability"] <= 1 or
            not math.isfinite(result["timeout_s"]) or result["timeout_s"] <= 0):
        raise Unavailable("invalid Jev configuration")
    return result


def resolve_key(settings):
    """Return (secret, source) without ever disclosing command output or error text."""
    def checked(value, source):
        key = value.strip()
        if not key or any(ord(char) < 0x21 or ord(char) > 0x7e for char in key):
            raise Unavailable("invalid key format")
        return key, source

    env_key = os.environ.get("TYPESAFE_API_KEY")
    if env_key and env_key.strip():
        return checked(env_key, "env")

    key_ref = settings.get("key_ref")
    if key_ref and shutil.which("op"):
        try:
            result = subprocess.run(["op", "read", str(key_ref)], capture_output=True, text=True,
                                    timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return checked(result.stdout, "op")
        except (OSError, subprocess.SubprocessError):
            pass

    service = settings.get("keychain_service") or DEFAULTS["keychain_service"]
    if shutil.which("security"):
        try:
            result = subprocess.run(["security", "find-generic-password", "-s", str(service), "-w"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return checked(result.stdout, "keychain")
        except (OSError, subprocess.SubprocessError):
            pass
    return None, None


def key_status(settings):
    if not settings.get("enabled"):
        return "disabled", None
    key, source = resolve_key(settings)
    return ("found", source) if key else ("missing", None)


def enabled_lanes(lanes, models_cfg):
    models = models_cfg.get("models") or {}
    selected = {}
    for name in LANES:
        lane = lanes.get(name) or {}
        if not isinstance(lane, dict) or not lane.get("model") or lane.get("enabled", True) is False:
            continue
        model_id, model = _find_model(models, lane.get("model"))
        description = lane.get("description") or lane.get("_note") or _FALLBACK_LANE_DESCRIPTIONS.get(name, name)
        if model:
            talents = model.get("talent") or {}
            talent_text = ", ".join("%s %.1f/10" % (dim, float(talents[dim]))
                                    for dim in ("architecture", "implementation", "debugging")
                                    if talents.get(dim) is not None)
            if talent_text:
                description += " Talent profile: " + talent_text + "."
        selected[name] = {"description": description, "model": model_id or lane.get("model")}
    return selected


_FALLBACK_LANE_DESCRIPTIONS = {
    "routine": "Routine, well-specified implementation and wiring.",
    "complex": "Complex implementation, debugging, and multi-file changes.",
    "frontier": "The hardest one-off after strong attempts have failed.",
    "local": "Local experimental work when the local lane is enabled.",
}


def _find_model(models, key):
    for model_id, model in models.items():
        if key in (model_id, model.get("slug")) or key in (model.get("aliases") or []):
            return model_id, model
    return None, None


def make_questions(lanes, models_cfg):
    available = enabled_lanes(lanes, models_cfg)
    if not available:
        raise Unavailable("no enabled lanes")
    lane_criteria = {name: LANE_CRITERIA[name] for name in available}
    effort_criteria = {
        "medium": "Routine work with clear interfaces, narrow changes, or documentation.",
        "high": "Meaningful implementation or debugging that benefits from careful reasoning.",
        "xhigh": "Broad, difficult, high-risk, or repeatedly resisted work that needs maximum reasoning.",
    }
    return {
        "lane": {"type": "choice", "instructions": "Which enabled implementation lane best fits this spec?",
                 "criteria": lane_criteria},
        "effort": {"type": "choice", "instructions": "What Codex reasoning effort best fits this spec?",
                   "criteria": effort_criteria},
        "spec_complete": {"type": "noul",
                          "instructions": "Does the spec fully determine the intended outcome, interfaces, constraints, and verification, without leaving a material implementation decision unresolved?"},
    }, available


def _probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Unavailable("invalid response")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise Unavailable("invalid response")
    return number


def parse_answers(response, questions):
    answers = response.get("answers")
    if not isinstance(answers, dict):
        raise Unavailable("invalid response")
    result = {}
    for name, question in questions.items():
        answer = answers.get(name)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise Unavailable("invalid response")
        if question["type"] == "choice":
            choice = answer.get("choice")
            probs = answer.get("probabilities")
            if (not isinstance(choice, str) or choice not in question["criteria"] or
                    not isinstance(probs, dict) or choice not in probs):
                raise Unavailable("invalid response")
            result[name] = {"answer": choice, "probability": _probability(probs[choice]),
                            "probabilities": {k: _probability(v) for k, v in probs.items()
                                              if k in question["criteria"]}}
        else:
            result[name] = {"answer": _probability(answer.get("noul"))}
    return result


def request(spec_text, lanes, models_cfg, settings=None):
    settings = dict(DEFAULTS, **(settings or {}))
    if not settings.get("enabled"):
        raise Unavailable("disabled")
    key, _source = resolve_key(settings)
    if not key:
        raise Unavailable("no key found")
    questions, available = make_questions(lanes, models_cfg)
    endpoint = settings.get("endpoint") or DEFAULTS["endpoint"]
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise Unavailable("invalid endpoint")
    payload = {"model": settings.get("model") or DEFAULTS["model"],
               "state": spec_text, "questions": questions}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(endpoint, data=data, headers={"Authorization": "Bearer " + key,
                                                "Content-Type": "application/json",
                                                "Accept": "application/json"}, method="POST")
    timeout = settings.get("timeout_s", 5)
    started = time.monotonic()
    deadline = started + timeout

    def perform_request():
        opener = build_opener(_NoRedirect())
        with opener.open(req, timeout=max(0.001, deadline - time.monotonic())) as response:
            if 300 <= response.getcode() < 400:
                raise _RedirectRefused()
            chunks = []
            total = 0
            read = getattr(response, "read1", None) or response.read
            while total <= 2 * 1024 * 1024:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk = read(min(4096, 2 * 1024 * 1024 + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            return b"".join(chunks), response.headers

    future = Future()

    def worker():
        try:
            future.set_result(perform_request())
        except BaseException as exc:
            future.set_exception(Unavailable(_request_error(exc)))

    thread = threading.Thread(target=worker, name="jev-request", daemon=True)
    thread.start()
    try:
        raw, headers = future.result(timeout=max(0, deadline - time.monotonic()))
    except FutureTimeout:
        raise Unavailable("timeout")
    except Unavailable:
        raise
    except BaseException as exc:
        raise Unavailable(_request_error(exc))
    if time.monotonic() > deadline:
        raise Unavailable("timeout")
    latency_ms = round((time.monotonic() - started) * 1000, 1)
    if len(raw) > 2 * 1024 * 1024:
        raise Unavailable("invalid response")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise Unavailable("invalid response")
    if not isinstance(decoded, dict):
        raise Unavailable("invalid response")
    parsed_answers = parse_answers(decoded, questions)
    request_id = (headers.get("x-request-id") or headers.get("request-id") or
                  headers.get("x-amzn-requestid") or decoded.get("request_id"))
    request_id = _safe_metadata(request_id, key)
    model = _safe_metadata(decoded.get("model") or payload["model"], key)
    return {"answers": parsed_answers, "available_lanes": available,
            "model": model or "jev-latest", "request_id": request_id,
            "latency_ms": latency_ms, "spec_sha256": hashlib.sha256(spec_text.encode("utf-8")).hexdigest()[:12]}


def _safe_metadata(value, key):
    if not isinstance(value, str) or key in value:
        return None
    return re.sub(r"[^A-Za-z0-9._:-]", "", value)[:128]


def log_suggestion(result):
    decision_id = core.new_run_id("jev")
    entry = {
        "id": decision_id, "ts": core.iso(), "kind": "jev", "model": result["model"],
        "request_id": result.get("request_id"), "latency_ms": result["latency_ms"],
        "answers": result["answers"], "actual_choice": None, "run_grade": None,
        "spec_sha256": result["spec_sha256"],
    }
    core.ledger_append(entry)
    return decision_id


def render_lines(result, minimum):
    answers = result["answers"]
    lines = []
    for key in ("lane", "effort"):
        item = answers[key]
        p = item["probability"]
        suffix = "confident" if p >= minimum else "uncertain"
        lines.append("DECISION: %s=%s p=%.3f %s" % (key, item["answer"], p, suffix))
    p = answers["spec_complete"]["answer"]
    suffix = "confident" if p >= minimum else "uncertain"
    lines.append("DECISION: spec_complete p=%.3f %s" % (p, suffix))
    return lines
