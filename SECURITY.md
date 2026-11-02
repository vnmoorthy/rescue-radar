# Security policy

Rescue Radar handles posts written by people in danger. We treat security and privacy bugs as top priority.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Report it privately through GitHub's
[private vulnerability reporting](https://github.com/vnmoorthy/rescue-radar/security/advisories/new)
("Report a vulnerability" on the Security tab). Include:

- what the problem is and where (file, endpoint, view),
- steps to reproduce, ideally with a minimal input,
- the impact you expect (data exposure, denial of service, wrong routing of a rescue request, ...).

We aim to acknowledge a report within 3 working days and to share a fix or a mitigation plan within 14 days.
We will credit you in the release notes unless you ask us not to.

## In scope

- Leaks of API keys or other secrets (the `.env` file, logs, error messages, the static export).
- PII redaction bypasses in `rr/scrub.py`: personal data that reaches the console unredacted.
- Injection or access-control problems in the HTTP API (`rr/server.py`) or the queue store (`rr/store.py`).
- Cross-site scripting or unsafe rendering of post text in the console (`web/`, `docs/`).
- Prompt-injection in a post that changes how other posts are routed.

## Out of scope

- Misclassification of an individual post. That is a model-quality issue: please open a regular issue with the
  post text (redacted) and the expected category.
- Findings that require a compromised machine or a leaked API key to begin with.

## Supported versions

Only the `main` branch is supported. This is a research prototype built at a hackathon: do not deploy it as
the only channel for emergency requests, and keep a human in the loop.

## Handling secrets

Secrets live only in a git-ignored `.env` file and are read only through `rr.env.load_env()`. Run
`python scripts/check_secrets.py` before pushing; it fails if a tracked file contains an API key. If a key is
ever committed, rotate it immediately with its provider, then remove it from history.
