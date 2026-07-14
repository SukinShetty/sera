"""
engine/api.py — Anthropic API call policy for SERA (run-2 hardening).

Centralizes the two failure modes that confounded ablation run 1
(docs/evidence/p6.md):

    BillingError        Raised when the account is out of credits (HTTP 400
                        "credit balance is too low"). This is UNRECOVERABLE —
                        retrying only burns wall-clock. It is a distinct type
                        so callers can let it propagate all the way up and
                        HALT an entire ablation run instead of silently
                        recording bogus "failed" verdicts.

    Rate limits (429)   Transient. call_with_backoff() retries them with
                        exponential backoff. Everything else (and 429s that
                        survive every retry) is re-raised unchanged so the
                        caller can fail just that one unit of work.

Public API:
    BillingError
    is_billing_error(exc) -> bool
    is_rate_limit_error(exc) -> bool
    call_with_backoff(make_call, *, backoff=RATE_LIMIT_BACKOFF_SECONDS,
                      sleep=time.sleep) -> result

Detection is by message text and exception class NAME (not identity), so it
works both against the real `anthropic` SDK and against test doubles that
raise stand-in exceptions.
"""

import time

# Sleeps (seconds) inserted BEFORE each retry of a rate-limited call. Four
# entries => up to four retries after the initial attempt (5 total tries).
RATE_LIMIT_BACKOFF_SECONDS = (5, 15, 45, 120)

BILLING_SIGNAL = "credit balance is too low"


class BillingError(RuntimeError):
    """Unrecoverable credit-exhaustion error. Must abort the whole run."""


def is_billing_error(exc: BaseException) -> bool:
    """True for the credit-exhaustion 400 (or any error carrying its text)."""
    msg = f"{getattr(exc, 'message', '') or ''} {exc}".lower()
    if BILLING_SIGNAL in msg:
        return True
    if type(exc).__name__ == "BadRequestError" and ("credit" in msg or "billing" in msg):
        return True
    return False


def is_rate_limit_error(exc: BaseException) -> bool:
    """True for HTTP 429 rate-limit errors."""
    if type(exc).__name__ == "RateLimitError":
        return True
    return getattr(exc, "status_code", None) == 429


def call_with_backoff(make_call, *, backoff=RATE_LIMIT_BACKOFF_SECONDS, sleep=None):
    """
    Invoke `make_call()` (a zero-arg callable performing one Anthropic
    request) under SERA's retry policy.

    - Billing/credit errors -> raised as BillingError immediately (no retry).
    - Rate-limit (429) errors -> retried with exponential backoff; if every
      retry is exhausted, the last 429 is re-raised.
    - Any other error -> re-raised unchanged on the first occurrence.

    `sleep` defaults to time.sleep, resolved at call time (not bound as a
    default argument) so tests can monkeypatch engine.api.time.sleep.
    """
    if sleep is None:
        sleep = time.sleep
    attempt = 0
    while True:
        try:
            return make_call()
        except BillingError:
            raise
        except Exception as exc:  # noqa: BLE001 — classify then re-raise/convert
            if is_billing_error(exc):
                raise BillingError(str(exc)) from exc
            if is_rate_limit_error(exc) and attempt < len(backoff):
                sleep(backoff[attempt])
                attempt += 1
                continue
            raise
