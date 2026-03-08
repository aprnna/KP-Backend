---
trigger: always_on
---

1. Jobs must always end in a terminal state.

Allowed states:

pending

running

finished

failed

2. System startup must recover stale jobs.

If the server restarts while a job is running, the job must be marked as failed.

3. Errors from external APIs must not crash the entire scraping job unless unrecoverable.

4. Retry logic must implement exponential backoff.

5. Scraping jobs must produce enough logs to debug failures.
