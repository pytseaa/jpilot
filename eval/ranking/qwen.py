"""Plumbing that lets the evaluation call the app's own functions (summarise, widen, check_jobs) over TACC.

CachedRunner batches many prompts into few TACC submissions and remembers every answer on disk, so a service that
expires mid-run costs only the unfinished part. Collector records the exact prompts a function would send, which is how
a whole stage is prefetched in one batch without copying the app's prompt building."""
import hashlib
import json
from pathlib import Path

# The model answered badly (after the client's own retry): that is a result. A service or network problem is not.
CACHEABLE_FAILURES = {"invalid_json", "missing_key", "bad_response"}


def key_of(item):
    blob = json.dumps([item["prompt"], item.get("max_tokens"), item.get("required_keys", [])], sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cacheable(record):
    return record["status"] == "ok" or record.get("error_type") in CACHEABLE_FAILURES


class CachedRunner:
    def __init__(self, real, path, chunk=40):
        self.real, self.path, self.chunk = real, Path(path), chunk
        self.cache = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.submissions = 0
        self.unresolved = set()  # prompts whose latest attempt failed for a service or network reason

    def __call__(self, prompts):
        todo = {}
        for item in prompts:
            if key_of(item) not in self.cache:
                todo.setdefault(key_of(item), item)
        fresh = {}
        keys = list(todo)
        for start in range(0, len(keys), self.chunk):  # the client job has 10 minutes, so batches stay small
            batch = keys[start:start + self.chunk]
            sent = [{**todo[k], "id": f"q{i}"} for i, k in enumerate(batch)]
            records = self.real(sent)
            self.submissions += 1
            for i, k in enumerate(batch):
                record = records[f"q{i}"]
                if _cacheable(record):
                    self.cache[k] = {"purpose": todo[k]["id"].split("-")[0], "record": record}
                    self.unresolved.discard(k)
                else:
                    fresh[k] = record
                    self.unresolved.add(k)
            self._save()
        return {item["id"]: self.cache[key_of(item)]["record"] if key_of(item) in self.cache else fresh[key_of(item)]
                for item in prompts}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.cache), encoding="utf-8")
        temporary.replace(self.path)

    def usage(self):
        """Calls, retries and tokens by purpose (cv, refine, check, b2), counting each distinct prompt once."""
        totals = {}
        for entry in self.cache.values():
            record = entry["record"]
            row = totals.setdefault(entry["purpose"], {"calls": 0, "retries": 0, "failed": 0,
                                                       "prompt_tokens": 0, "completion_tokens": 0})
            row["calls"] += 1
            row["retries"] += max(0, record.get("attempts", 1) - 1)
            row["failed"] += record["status"] != "ok"
            row["prompt_tokens"] += record.get("prompt_tokens", 0)
            row["completion_tokens"] += record.get("completion_tokens", 0)
        return totals


class Collector:
    """A runner that sends nothing: it keeps the prompts and answers each with a harmless stand-in."""

    def __init__(self, dummy):
        self.prompts, self.dummy = [], dummy

    def __call__(self, prompts):
        self.prompts.extend(prompts)
        return {p["id"]: {"status": "ok", "answer": self.dummy(p), "attempts": 1, "errors": [],
                          "prompt_tokens": 0, "completion_tokens": 0, "elapsed_seconds": 0} for p in prompts}
