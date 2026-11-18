"""Helpers the search tests share."""
import time


def wait_until_finished(client, base):
    """Poll the status until the search is done or failed. Return the status."""
    deadline = time.monotonic() + 5
    while client.get(f"{base}/status").json()["stage"] not in ("done", "failed") and time.monotonic() < deadline:
        time.sleep(0.01)
    return client.get(f"{base}/status").json()
