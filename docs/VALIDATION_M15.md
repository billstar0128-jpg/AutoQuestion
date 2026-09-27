# M15 local validation — 0.2.0

Status: v0.2.0 Stable source Release published; required automatic gates complete. Chrome / Edge GUI acceptance is **NON-BLOCKING MANUAL FOLLOW-UP** by explicit owner decision on 2026-09-27.
The local results below predate the publication continuation. Final commit, CI, fresh-clone and publication evidence is recorded below.

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

## Manual follow-up and automatic gate policy

Follow [Browser DOM Setup](BROWSER_DOM_SETUP.md) and [M15 manual acceptance](MANUAL_ACCEPTANCE_M15.md).
Skipped before release by explicit user decision. Real Chrome / Edge GUI installation, physical F8, browser/desktop switching, disabled-extension fallback and real Canvas Vision remain recommended post-release checks.
The owner explicitly superseded the previous manual gate. The required automatic gates, all completed below, were: local tests, staged/history audit, main push, real GitHub Actions, true fresh GitHub clone/new venv, offline smoke and remote audit, then v0.2.0 **Stable** source-only Release.

Known limitations: semantic radio/checkbox groups only; custom widgets/select-only questions, Canvas, cross-origin frames, closed shadow and ambiguous/large pages may require Vision. Browser internal/restricted pages may deny injection. Pairing is memory-only and must be renewed after app restart/worker loss. If a paired browser disconnects during a request and original-tab identity cannot be proven, the task cancels rather than capturing a different tab. No guarantee of model accuracy or all-site support.

## Final publication evidence — 2026-09-27

- Release source commit: `ab390de5b57bc05ebc25a2248eb2e634f7e87d3f` (`Add general browser DOM support for v0.2.0`), pushed to existing origin/main without force.
- Final local pytest: 263 passed / 399 subtests, 35.24 s; unittest: 263 passed, 33.331 s; no local skips. compileall, pip check, Doctor and all version checks passed.
- Public inventory/staged audit: 107 reviewed files, zero findings; staged content matched the reviewed working files. Private configuration, logs, credentials, screenshots and browser binaries were not staged.
- [Real Windows GitHub Actions](https://github.com/billstar0128-jpg/AutoQuestion/actions/runs/36295257899): test (3.10), test (3.12), test (3.14) all success. CI explicitly skips five interactive desktop tests; it does not represent manual GUI acceptance.
- Fresh clone came from the public GitHub URL at the exact release commit, with a new Python venv, independently installed runtime/dev dependencies and isolated empty application profile. Version, editable metadata, extension and bridge inventory, actual main.py Offline/Fake hotkey path and clean tracked tree passed.
- Fresh full pytest: 263 passed, 399 subtests passed in 36.73s. Fresh unittest: 263 tests passed in 35.122 s. Fresh compileall, pip check and release audit passed. Doctor exited successfully with expected warnings: no API key configured and Fake has no Vision. No real API calls or user credentials were used.
- Fresh remote scan: Candidate/tracked/history audit PASS: 107 candidates, 107 tracked, 148 historical blobs; zero findings. This is a bounded static scan, not a guarantee that every possible secret format can be detected.
- Environment recovery: the official Chromium CDN repeatedly reset the connection and then stalled. Verification used the same-revision official Playwright browser cache copied into the new venv; browsers.json matched and every copied file's SHA256 was verified. No browser profile, Python package or user configuration was reused. GitHub CI independently downloaded its browser successfully.
- The first fresh pytest run passed 262 tests and failed only the release inventory check because the isolated pip installer generated a download-cache directory in source. The cache was moved outside source; the complete suite then passed. No application code, test assertion or audit rule was weakened. Original failure/download logs remain private local evidence.
- GitHub API verified public repository identity, Apache-2.0, README, LICENSE, SECURITY, PRIVACY, CONTRIBUTING, CHANGELOG, workflow, extension manifest and release notes against local reviewed content.
- Repository Description verified exactly: Put a question on screen, press F8, get an answer. Browser DOM when possible, Vision everywhere else.
- [AutoQuestion v0.2.0](https://github.com/billstar0128-jpg/AutoQuestion/releases/tag/v0.2.0): tag points to the tested source commit; published, latest, non-draft and **not Pre-release**. Body matches docs/RELEASE_NOTES_0.2.0.md. No uploaded binary assets, EXE/MSI or PyPI publication.
- Existing v0.1.0rc1 tag and Pre-release were preserved. Subsequent publication-record documentation does not move the v0.2.0 tag.
- Chrome / Edge manual validation: **Skipped before release by explicit user decision.** Post-release feedback remains recommended and non-blocking.
