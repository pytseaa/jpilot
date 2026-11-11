"""Send each prompt to the Qwen service and write one answer file.

prompts.json, in the client folder (the backend writes it, wording and all):
    {"prompts": [{"id": "check-7", "prompt": "<finished text>",
                  "required_keys": ["grade"],   # optional: the answer must hold these keys
                  "max_tokens": 2048}]}         # optional: reply limit for this prompt
Each id is one word and is unique.

Answer file, under TACC_USERDIR/jpilot-tacc-client/job-<SLURM_JOB_ID>.json:
    {"answers": {"check-7": {"status": "ok" | "failed",
                             "answer": <the parsed reply>,     # when ok
                             "error_type": "...",              # when failed
                             "attempts": 1 or 2,
                             "prompt_tokens": n, "completion_tokens": n,
                             "elapsed_seconds": s}}}           # totals over all attempts
error_type is one of http_error, timeout, unreachable, bad_response, invalid_json,
missing_key or client_error. A reply that is not usable is retried once; an HTTP error,
a timeout or an unreachable service is not.

The running log gets one "CALL_DONE <n> of <total>: <id> <outcome>" line per finished call,
and never any prompt or answer text.
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from qwen_client import CALL_TIMEOUT_SECONDS, QwenError, chat

MAX_ATTEMPTS = 2
MAX_PARALLEL_CALLS = 4
DEFAULT_MAX_TOKENS = 2048
# The first attempt is repeatable; a retry at 0 would usually just repeat the bad answer.
RETRY_TEMPERATURE = 0.3
# An unusable answer may come out differently next time. A refused or unreachable service won't.
RETRIED_ERRORS = {"bad_response", "invalid_json", "missing_key"}
# Ids appear in the progress log, one word each.
ID_PATTERN = re.compile(r"\S+")


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _usable(item):
    required_keys = item.get("required_keys", [])
    return (isinstance(item["id"], str) and ID_PATTERN.fullmatch(item["id"]) is not None
            and isinstance(item["prompt"], str)
            and isinstance(required_keys, list) and all(isinstance(k, str) for k in required_keys)
            and (item.get("max_tokens") is None or _is_count(item["max_tokens"])))


def load_prompts(path):
    """Read prompts.json: {"prompts": [{"id", "prompt", "required_keys"?, "max_tokens"?}]}."""
    try:
        with open(path, encoding="utf-8") as f:
            prompts = json.load(f)["prompts"]
        ids = [item["id"] for item in prompts]
        if len(set(ids)) != len(ids) or not all(_usable(item) for item in prompts):
            raise ValueError("a prompt is malformed or an id repeats")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            "prompts.json is missing or malformed. Expected "
            '{"prompts": [{"id": ..., "prompt": ...}]} with a different one-word id on each '
            "prompt, required_keys a list of names, and max_tokens a whole number."
        ) from exc
    return prompts


def _has_keys(answer, required_keys):
    if not required_keys:
        return True
    return isinstance(answer, dict) and all(key in answer for key in required_keys)


def _failed(error_type):
    return {"status": "failed", "error_type": error_type}


def _count(usage, name):
    value = usage.get(name) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _attempt(item, base_url, temperature, timeout):
    """Make one call. Return its outcome and the usage the reply reported."""
    try:
        result = chat([{"role": "user", "content": item["prompt"]}], base_url,
                      max_tokens=item.get("max_tokens") or DEFAULT_MAX_TOKENS,
                      temperature=temperature, timeout=timeout)
    except QwenError as exc:
        return _failed(exc.error_type), None
    usage = result.get("usage")
    try:
        answer = json.loads(result["choices"][0]["message"]["content"])
    except (ValueError, RecursionError):  # RecursionError: a runaway answer of open brackets
        return _failed("invalid_json"), usage
    if not _has_keys(answer, item.get("required_keys", [])):
        return _failed("missing_key"), usage
    return {"status": "ok", "answer": answer}, usage


def _ask(item, base_url, timeout):
    """Ask one prompt, retrying once on an unusable answer. Always return a record."""
    started = time.perf_counter()
    tokens = {"prompt_tokens": 0, "completion_tokens": 0}
    attempts = 0
    try:
        for attempts in range(1, MAX_ATTEMPTS + 1):
            outcome, usage = _attempt(item, base_url,
                                      0 if attempts == 1 else RETRY_TEMPERATURE, timeout)
            for name in tokens:
                tokens[name] += _count(usage, name)
            if outcome["status"] == "ok" or outcome["error_type"] not in RETRIED_ERRORS:
                break
    except Exception:  # a bug or an odd reply must cost only this call, never the others
        outcome = _failed("client_error")
    return {**outcome, "attempts": attempts, **tokens,
            "elapsed_seconds": round(time.perf_counter() - started, 3)}


def _log_done(done, total, item_id, record):
    """One line per finished call, ids only: the backend counts these lines in the running log."""
    detail = "ok" if record["status"] == "ok" else f"failed {record['error_type']}"
    print(f"CALL_DONE {done} of {total}: {item_id} {detail}", flush=True)


def run(prompts, answers_path, base_url, timeout=CALL_TIMEOUT_SECONDS):
    """Answer every prompt, at most MAX_PARALLEL_CALLS at once, and write the answer file."""
    records = {}
    lock = threading.Lock()

    def answer(item):
        record = _ask(item, base_url, timeout)
        with lock:
            records[item["id"]] = record
            _log_done(len(records), len(prompts), item["id"], record)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as pool:
        list(pool.map(answer, prompts))
    # ASCII-escaped, so no answer text can fail to encode and leave a half-written file.
    text = json.dumps({"answers": {item["id"]: records[item["id"]] for item in prompts}},
                      indent=2) + "\n"
    with open(answers_path, "w", encoding="utf-8") as f:
        f.write(text)
