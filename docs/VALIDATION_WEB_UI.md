# Web UI validation — 2026-10-13

Scope: an actual Windows loopback web console, double-click launcher and provider examples. Uses the current F8/ESC, TaskRunner, DOM/AUTO/Vision and secure settings implementation. Version remains 0.2.0; additions are on main under Unreleased. Existing release tags are unchanged.

## Local evidence

- Final full pytest: 276 passed, 411 subtests, 47.80 s.
- Final full unittest: 276 tests passed in 45.319 s, no local skips.
- compileall (including AutoQuestion.pyw/main/src/tests/tools), pip check, Doctor and version: PASS.
- Real headless browser exercised first-run config, provider/model chips, session-only save, blank Key after save, actual callback answer display, stop, refresh authentication, settings locks and narrow-screen layouts. No browser JavaScript errors; no horizontal overflow at 390 px.
- Native Windows test posted real WM_HOTKEY messages to the application's own thread: F8 produced the Fake answer, ESC released the service, and a second start/F8/ESC worked. No physical keystrokes sent to user windows.
- HTTP tests covered missing token, incorrect Host, foreign Origin, non-JSON requests, oversized requests, duplicate JSON keys, safe credential reuse/rollback and rejected fields without echoing secrets.
- HTML-looking synthetic question/answer strings stayed plain text; no script or markup execution.
- Static preview contained exactly index.html, app.js, style.css and public providers.json. It disabled Key entry and made no local /api/ calls.
- Desktop settings, workspace, answer and 390 px screenshots were inspected. Only synthetic data used; screenshots and logs remain ignored local artifacts.
- Launcher check verifies handoff to project pythonw.exe and direct UI startup after dependency detection. First dependency installation is a user-confirmed graphical action; this session already had dependencies, so no real first-install acceptance is claimed.

All automated model traffic is Fake/synthetic. No real API call, Windows credential write, private page dump or user screenshot is part of these tests. Examples were verified against official documentation, not billed integration requests. Initially failing tests were fixed without weakening source validation, CSP or secret scanning: synthetic credential strings now use explicit test placeholders, and browser waits use functions compatible with strict CSP.

## GitHub verification

The Windows source workflow runs all suites on Python 3.10 / 3.12 / 3.14; six interactive desktop tests are explicitly skipped on CI. Pages exports only fixed public assets after a successful main push workflow. Public preview cannot run Windows capture or send API requests. Final CI and deployment evidence is available in the repository Actions history.
