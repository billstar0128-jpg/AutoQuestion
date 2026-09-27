# M15 local validation — 0.2.0

Status: local implementation and automated checks complete. Chrome / Edge GUI acceptance is **NON-BLOCKING MANUAL FOLLOW-UP** by explicit owner decision on 2026-09-27.
The local results below predate the publication continuation. New commit, CI, clone and release evidence is recorded separately as each automatic gate completes.

## Baseline and scope

Read current source, tests, examples, public documentation, requirements, metadata and CI before implementation.
The initial checkout was clean at 4a6fbba. Live main was ahead; fast-forwarded to 6a79bcd, preserving the owner's new novice Quick Start.
Baseline: pytest 235 tests / 365 subtests passed; unittest 235 passed; compileall, pip check and candidate audit passed.
The existing public v0.1.0rc1 remains a Pre-release. Its tag has not been moved.

M15 adds only optional Chrome / Edge DOM, loopback pairing, foreground routing, tests and documentation.
No answer clicking, selecting, submitting, next-question automation, OCR, native Anthropic, fill-blank/short-answer implementation or M16 work.

## Actual local results — 2026-09-27

Windows CPython 3.14.6, project .venv-win. Full suites run sequentially without AUTOQUESTION_CI.

| Check | PASS | FAIL | SKIP | Detail |
|---|---:|---:|---:|---|
| pytest | 263 | 0 | 0 | 399 subtests; 35.28 s |
| unittest | 263 | 0 | 0 | 33.669 s |
| Visible Windows smoke | 1 | 0 | 0 | 1.732 s; real HWND/PID/focus, owned windows only |

compileall (main/src/tests/tools), pip check, Doctor and version: PASS.
Source, editable installation metadata and extension manifest all report **0.2.0**.
README novice Quick Start block compared against Git HEAD: unchanged byte-for-byte.
git diff --check: PASS. Git reports expected existing CRLF-to-LF normalization notices for three files; no whitespace errors.
Candidate secret/UTF-8/local-link audit: PASS, 107 public candidates, zero findings including this record.
No new NOTICE: no bundled third-party source requiring one was introduced. websockets is installed as a dependency, not vendored.

Local logs are in ignored logs/m15_pytest.log, m15_unittest.log, m15_doctor.log and m15_smoke.log; not publication candidates.

## What automation actually exercised

- Protocol contract test first reproduced the missing module, then passed after implementation.
- Real loopback WebSocket round trips: token/Origin/path rejection, malformed and oversized payloads, request IDs, timeout, reconnect, ambiguous sessions, Chrome/Edge identity selection and cleanup.
- Native Win32 process creation identity and TCP ownership; real extension connection matched independently to the owned Chromium browser PID.
- Exact shipped extension JS in a temporary Chromium profile: handshake, process matching, DOM question, Canvas unavailable, metadata-only original-tab check, stale tab cancellation and no selected inputs.
- The integration harness grants only the synthetic localhost site in its temporary manifest. It does **not** claim the original manifest's Chrome/Edge permission dialog or GUI installation was manually accepted.
- Real extractor on synthetic single/multiple/true-false/no-letter/noise fixtures, ARIA/nested labels, disabled options, hidden/input/editable field exclusion, SPA refresh, same-origin iframe, open shadow, opaque-origin frame and closed-shadow fallback, partial-viewport rejection.
- Router tests cover desktop direct Vision, normal browser DOM, missing extension/acquisition fallback, strict DOM, target change cancellation and provider errors without a second image request.
- Existing managed four-question Demo, idle Canvas drawing/navigation, DOM → Canvas → desktop window → DOM, hotkeys, BUSY/debounce, setup, credentials and provider regressions remain covered.

All model/API calls in automation use Fake or synthetic transports; screenshots in smoke are synthetic. No actual WPS question, personal page dump, real Provider call or API credential is used as test data.

## Fixes during implementation

Older tests expecting DOM mode to automatically open an unbound background Demo were updated to the new explicit --open-demo and foreground policy. Native/managed regression coverage remains; identity checks were not relaxed.
The extension integration initially attempted a browser permission request without a user gesture; Chromium correctly refused it. The test harness now uses a temporary synthetic-only host grant and leaves GUI permission acceptance to the user.
An integration cancellation was traced to a pending tabs.onUpdated complete event. The harness now waits for that event and exact published epoch, rather than sleeping or weakening target checks.
A duplicate JS declaration introduced during editing caused a full-suite failure and was removed. Final full suites above passed afterward.
Partly offscreen options and editable text nested in option labels were additionally covered, avoiding incomplete questions or collection of typed fields.

## Remaining release gates

Follow [Browser DOM Setup](BROWSER_DOM_SETUP.md) and [M15 manual acceptance](MANUAL_ACCEPTANCE_M15.md).
Skipped before release by explicit user decision. Real Chrome / Edge GUI installation, physical F8, browser/desktop switching, disabled-extension fallback and real Canvas Vision remain recommended post-release checks.
The owner explicitly superseded the previous manual gate. Required automatic gates remain: local tests, staged/history audit, main push, real GitHub Actions, true fresh GitHub clone/new venv, offline smoke and remote audit, then v0.2.0 **Stable** source-only Release.

Known limitations: semantic radio/checkbox groups only; custom widgets/select-only questions, Canvas, cross-origin frames, closed shadow and ambiguous/large pages may require Vision. Browser internal/restricted pages may deny injection. Pairing is memory-only and must be renewed after app restart/worker loss. If a paired browser disconnects during a request and original-tab identity cannot be proven, the task cancels rather than capturing a different tab. No guarantee of model accuracy or all-site support.
