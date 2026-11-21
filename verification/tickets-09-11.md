# Tickets 09–11 verification

## Expected behaviour (written before running the tests)

| Case | Expected candidate outcome |
| --- | --- |
| Sparse CV | A verified fit, or an empty list explaining that the CV may be too brief; never pad with grade 0. |
| Unreadable CV | Reject with a text-based PDF instruction before any Qwen call. Retain a failed trace. |
| Conflicting constraints | Empty list pointing to employment types on the form. |
| No suitable jobs | Every checked job grades 0; empty list explains that no evidenced fit was found. |
| Invalid model output | Two invalid JSON replies for one job; skip only that job, report the count, retain the others. |
| Failed submission | Failed status with an error; no partial list; delete CV and require a fresh upload. |
| Unreachable service | Ask to restart Qwen and update server-url.txt, then upload again. |
| Short list | Explain that only verified fits are shown and grade 0 never fills the list. |

## Privacy and trace design

The uploaded PDF stream is closed after intake. CV text and summary live only in memory while the request is active. The backend clears them, the keywords and target role before publishing a terminal status. Review data is cleared from React state at the terminal outcome. Verified claims remain in the transient results so that the candidate can read the required quotes; they are never stored in SQLite or the trace.

TACC prompt files are removed in `finally`; downloaded answer files live in a temporary directory that is removed on either outcome. **Copies of CV-bearing prompt and answer files may remain in the course's TACC storage under the team's account. Ticket 09 does not remove remote copies (Q35).**

Traces live at `backend/data/traces/<request-id>.json` and survive CV deletion and backend restart. Failed uploads return `X-Request-ID` so their trace can be found too. Only generated prompt IDs, stored job IDs, fixed stage/error labels, timings, counts, grades and indexed quote-check decisions are written. Raw exceptions, CV text, summaries, keywords, prompts, answers and quote text are excluded.

`elapsed_seconds` is active processing time (intake plus search), excluding the human review pause. Each stage and submission has UTC timestamps and duration. Call records have attempts, retries, token totals, elapsed time and error types from the client. Totals distinguish `scheduled_calls` (prompts submitted to the runner) from `calls` (returned call records); `attempts` counts known model attempts, including retries. A submission failure before answers return has zero known attempts/tokens, and `not_returned` identifies missing telemetry. Fake-runner token counts are synthetic zeroes.

Read completed traces and calculate median/P95 from the backend directory:

```python
from app.trace import latency_summary
print(latency_summary("data"))
```

## Execution results — 2026-11-21

- Backend after the follow-up review: **250 passed**, using the full `python -m pytest backend -q -W error::pytest.PytestUnhandledThreadExceptionWarning` suite (temporary files placed under `.ignore/review-full` for this run).
- The invalid-output API test runs the real standard-library client against a local HTTP stub: exactly two invalid replies, one skipped job, another job retained, both attempts' token counts in the trace, and no CV marker in backend files.
- Marker scans pass after success and failure. The CV fields are empty in request state, the database and retained traces contain no marker, and local prompt/download files are removed. A failed request cannot be restarted without uploading again.
- Refinement traces cover both rounds. Stored traces can be read after creating a new app instance, and median/P95 aggregation is checked across multiple requests.
- TACC runner tests cover failed submissions, missing/malformed/incomplete answers, an unreachable service, bounded polling and local prompt cleanup. The Qwen client tests exercise retry behaviour against the HTTP stub.
- Frontend after the follow-up review: **8 component tests passed** with `npm test`. They cover failed result loading and retry, lost requests, terminal failures, worker-start failure, temporary status errors, backend restart before result retrieval, and accepted/unaccepted searches whose start response was lost. **`npm run build` passed**, including TypeScript checking and the Vite production build. Dependency installation reported no vulnerabilities. The component tests use jsdom and do not replace browser acceptance.
- One dependency warning remains: the installed Starlette version deprecates its `httpx` TestClient integration. It did not fail any test.
- **Browser acceptance remains unverified.** Computer Use was attempted but stopped because it could not reliably identify the current Chrome URL on Windows. No browser screenshot or visual-pass result is claimed. Ticket 11's browser-check checkbox remains open.
- No real Qwen/GPU run was performed. These tickets are covered with the fake runner, local HTTP stub and fake `tcloud`; any future GPU verification must use the course TACC platform.

## Follow-up review

- Worker startup and trace-write failures now end the request safely, clear CV data, and allow a subsequent upload/search. Failure reporting cannot escape as a worker traceback if writing the final trace also fails. An unwritable trace directory returns a safe upload error; persistence is necessarily unavailable while storage is broken.
- TACC submission, command, timeout, download and malformed-answer failures have distinct trace labels. Only confirmed unreachable Qwen calls show the restart/address instruction. A nonzero download exit is rejected even when a seemingly valid answer file was left behind, and local files are removed.
- A completed search clears review data before fetching results. A failed results fetch can be retried without starting another search. Missing/expired requests end polling and require a new upload; temporary status connection errors continue polling. If the start response is lost, status polling determines whether the backend accepted the search; an unaccepted search restores the retry button.
- An empty display no longer claims that no job fits when checks failed; the backend explanation and skipped count provide the reason. Before Search, the status endpoint explicitly returns `stage: null`.

## Remaining browser acceptance check

Start the backend with `JPILOT_RUNNER=fake` and the frontend as described in the README. Use a synthetic, text-based PDF. Check that the review disappears on a terminal outcome, the backend explanation and skipped count appear, the failure error asks for a new upload, and Search is no longer offered for the completed request. The API tests define reproducible short/empty/failed scenarios; the default empty database exercises the form-directed empty explanation. Confirm the short-list, grade-0, invalid-output and unreachable-service scenarios against the same canned answers before marking the remaining browser checkbox complete.
