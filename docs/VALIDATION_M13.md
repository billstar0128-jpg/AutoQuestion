# M13 Local Validation

## Baseline before release edits

Windows CPython 3.14.6. pytest: 205 PASS, 280 subtests PASS, 0 FAIL, 0 SKIP (125.95 s).
unittest: 205 PASS, 0 FAIL, 0 SKIP (120.245 s).
M12 Setup / Credential / SecretSafety: 49 PASS, 44 subtests PASS, 0 FAIL, 0 SKIP.
compileall / pip check / Doctor: PASS. Baseline version: 0.1.0.dev1.

Visible smoke initially failed safely when Windows refused foreground activation.
Same unchanged test rerun in an interactive terminal: 1 PASS, 0 FAIL, 0 SKIP (3.207 s).
No identity-protection relaxation or arbitrary-window capture.

Startup UX implementation checkpoint: pytest 214 PASS, 294 subtests PASS, 0 FAIL, 0 SKIP (150.20 s).

## Final results — 2026-09-23

| Check | PASS | FAIL | SKIP | Evidence |
|---|---:|---:|---:|---|
| Workspace pytest | 220 | 0 | 0 | 304 subtests PASS; 188.43 s |
| Workspace unittest | 220 | 0 | 0 | 188.822 s |
| Local CI-mode pytest | 215 | 0 | 5 | 301 subtests PASS; 176.13 s |
| Local CI-mode unittest | 215 | 0 | 5 | 220 discovered; 166.594 s |
| Clean-room pytest | 220 | 0 | 0 | 304 subtests PASS; 198.79 s |
| Clean-room unittest | 220 | 0 | 0 | 196.708 s |
| Final visible smoke rerun | 1 | 0 | 0 | 3.133 s; interactive terminal |

Final visible smoke first attempt again failed foreground activation safely. Independent unchanged rerun passed.
The failures are recorded, not counted as a first-attempt PASS; no tests or protection rules were relaxed.

compileall (main.py, src, tests, tools): PASS.
pip check: PASS, no broken requirements.
Workspace Doctor: PASS, exit 0. Version: AutoQuestion 0.1.0rc1.
show-config: PASS, public settings and credential state only; no Key output or credential value read.
Local CI mode deliberately excludes five interactive desktop tests, described in [Development](DEVELOPMENT.md).
GitHub Actions has not run online; Python 3.10 / 3.12 remain unverified locally.

The default Windows pipe output used by the final local unittest displayed Chinese incorrectly in the tool transcript.
The isolated UTF-8 run rendered Chinese correctly; source UTF-8 audit passed.
Use Windows Terminal and Python -X utf8 when collecting redirected output; no corrupted source was introduced.

## Clean-room install

PASS: all 15 sequential steps exited 0 in a newly created directory outside the project:
new venv, runtime dependencies, Chromium, version, Doctor, show-config, development dependencies,
editable metadata install, metadata version equality, full pytest, full unittest, compileall, pip check,
candidate audit and installed-version inventory.
New APPDATA / LOCALAPPDATA / USERPROFILE and sanitized subprocess environment were used.
No application config remained in the shared isolated profile.
Doctor returned WARNINGS with exit 0 because the clean profile uses Offline Fake without real Vision credentials; this is expected.
Every one of the 79 candidate files matched the tested copy before final validation/checklist documentation updates.
Logs and results.json remain in the isolated directory for local review; no logs were added to release candidates.
This is a source-copy install, not a Git clone or standalone wheel test.

## Candidate, privacy and dependency audit

79 public candidate files; 0 findings. UTF-8, no BOM/replacement markers, local Markdown links and version checks PASS.
No private screenshots, embedded image data, real credentials, personal absolute user paths or unexpected binaries
were found in the public candidate set. Private/excluded files were not opened by the candidate scanner.
This is a limited static-pattern and candidate review, not proof that every possible secret can be detected.
Known synthetic fixtures and retained official-document references are intentional.
No third-party source or full official documentation was vendored; attribution/license review must be repeated
before redistribution in the chosen distribution format.

Runtime requirements unchanged: pydantic, openai, mss, Pillow, python-dotenv and playwright.
pytest stays development-only; setuptools is the optional metadata build backend.
No new runtime dependencies, bulk upgrade or dependency vendoring.
pip check verifies consistency, not vulnerabilities.
CLI/banner and editable package metadata agree on the source version 0.1.0rc1.
legacy_main.py was not changed or included; original SHA256:
3DB1204B2A6DB90BB0702BDD1A3DD8EC130A37B48CC1CE21DDA24AEC51F7FAF3.

## Git and publication state

After candidate audit and tests, an empty local Git repository was initialized on main.
Git-visible untracked files exactly match the 79 audited candidates.
Actual git check-ignore confirms .env, private env variants, virtual environments, logs, screenshots,
config.json and legacy_main.py are excluded; .env.example and application source remain candidates.
No staging, local commits, tags, remotes, push or public upload.
Local history secret scan: N/A, no commits/history exist; current candidate audit is not a history audit.
Local clone: N/A, no local commit. Apache-2.0 has now been selected; no RC commit was created.
Future staging/history audits are still required before any public push.

## Changed-file inventory

Runtime / startup: src/autoquestion/{__init__,app,cli,startup}.py and .env.example.
Tests: new test_startup_ux.py and test_release.py; updates to test_setup.py, test_router.py,
test_entrypoint.py, test_windows_hotkeys.py, test_reliability.py and test_doctor.py.
Release root: README.md, SECURITY.md, PRIVACY.md, CONTRIBUTING.md, CHANGELOG.md,
pyproject.toml, .gitignore, .gitattributes and .editorconfig.
Docs: ARCHITECTURE, CONFIGURATION, DEVELOPMENT, SECURITY_MODEL, TECHNICAL_NOTES,
RELEASE_NOTES_0.1.0rc1, MANUAL_ACCEPTANCE_M13, RELEASE_CHECKLIST and this VALIDATION_M13.
GitHub preparation: Windows workflow, bug/feature issue templates and PR template.
Tools: release_audit.py and clean_room.py.
Existing Demo files and Router behavior were retained.

## Boundaries and remaining gates

Automatic model calls use Fake / MockTransport; images are synthetic; credentials use fake backends or mocked Win32 API.
No real provider request, credential export, or real screenshot was used for these tests.
Doctor/show-config may inspect saved public config and credential metadata, never Key values.
Real terminal masking, provider accuracy, WPS Vision and Windows credential persistence remain manual acceptance.
License follow-up (2026-09-24): the owner selected Apache-2.0; the unmodified official license is in [LICENSE](../LICENSE).
The license-selection blocker is resolved. Other manual acceptance and publication gates remain pending.
No public repository URL or private security contact invented.
M13 implementation and automated verification are complete; user manual acceptance remains unchecked.
Follow [A–X manual acceptance](MANUAL_ACCEPTANCE_M13.md) and [Release Checklist](RELEASE_CHECKLIST.md).
