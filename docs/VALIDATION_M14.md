# M14 Validation / Publication Status

Phase A: PASS. The user ran the unchanged visible smoke in a foreground terminal: 1 test passed in 9.441 s.
Phase B: complete. v0.1.0rc1 was published as a source-only GitHub Pre-release after the gates below passed.
Version: 0.1.0rc1; Apache-2.0. Stable release is not authorized.
Repository: https://github.com/billstar0128-jpg/AutoQuestion (public).

## Reproduction and fix

Before the change, synthetic Setup input reproduced both cases without any credential access:
- Base URL = deepseek-flash advanced directly to the Model ID prompt with no validation message.
- Model ID = https://api.deepseek.com advanced directly to the Vision prompt with no validation message.

Root cause: Setup collected URL, model, Vision and input mode before constructing UserConfig.
LLMConfig checked URL structure only at that later boundary, and checked model only for non-empty text.
The hotfix adds shared local validators in config.py, current-field re-prompting in Console,
normalized saved-config validation and explicit reversed-field diagnostics.
First-run, --setup, presets, Custom, saved settings and merged runtime settings share these rules.
No network validation, /models calls, real Key tests or automatic swaps.
Existing local/internal endpoints and model identifiers containing slash, colon, dot, underscore or @ remain supported.

Changed implementation: config.py, setup_wizard.py, user_config.py, startup.py.
Added tests: tests/test_setup_validation.py (15 test methods).
Docs: README introduction uses the owner's exact approved text; First-run Setup and
CONFIGURATION troubleshooting explain URL vs Model ID. CHANGELOG records the hotfix.

## Actual local checks

| Check | PASS | FAIL | SKIP | Detail |
|---|---:|---:|---:|---|
| Setup / M12 / credential / Doctor / startup / LLM targeted suite | 107 | 0 | 0 | 174 subtests; 24.18 s |
| Full pytest | 235 | 0 | 0 | 365 subtests; 29.72 s |
| Full unittest | 235 | 0 | 0 | 28.172 s |
| Visible browser smoke, first attempt | 0 | 1 | 0 | Foreground activation protection; 6.615 s |
| Visible browser smoke, unchanged independent retry | 0 | 1 | 0 | Same protection; 1.817 s |
| Visible browser smoke, user foreground terminal | 1 | 0 | 0 | User-reported output; 9.441 s |

compileall: PASS. pip check: PASS. Doctor: PASS (metadata only; no Key value read).
Version command: AutoQuestion 0.1.0rc1.
Candidate audit before this report: PASS, 81 files, 0 findings.
Both visible smoke attempts stopped before analyzing any other window; no protection was weakened.
Full headless browser / Canvas / AUTO regressions passed. The separately reported foreground run resolves the visible smoke gate; previous failures remain recorded.

## Local manual continuation

Use an interactive Windows Terminal at the project root, with old instances closed:

```powershell
.\.venv-win\Scripts\python.exe -X utf8 tests/smoke_browser_window.py -v
```

Keep the newly opened test Chromium in front; do not switch to another application during the test.
The user completed this check successfully before publication began.

For the Setup hotfix:
1. Run main.py --setup and choose DeepSeek.
2. Enter deepseek-flash as Base URL. Expect immediate rejection and another Base URL prompt.
3. Enter https://api.deepseek.com. At Model ID, enter that URL again.
4. Expect immediate rejection and another Model ID prompt, without repeating Provider/Base URL.
5. Enter your actual available Model ID, continue Setup and reach READY.
6. Cancel or Ctrl+C during either re-prompt must exit without saving or starting the app.
No actual model/Key validity is checked by this structural validation.

## Publication prerequisites and copy

Continuation check (2026-09-25): Git and GitHub CLI are now installed and the active GitHub
account was verified. The CLI/tool availability blocker is resolved.
Git status, remote, diff, cached diff, ls-files and refs were checked: main has no commits,
no origin, no tracked files and an empty staging area. The 82 untracked public candidates
match the audited file inventory exactly. History scanning is N/A until commits exist;
staged and history checks must be repeated before publication.
Visible smoke also failed on the previous continuation (1.879 s) at the same foreground
activation protection. The subsequent user foreground run passed in 9.441 s.
No protection was weakened. Phase B began only after that result was supplied.
Never send credentials in chat or commit them.

The repository Description must be exactly:

Put a question on screen, press F8, get an answer. A Windows question assistant with Vision, local DOM support, and multi-provider setup.

README introduction matches the owner's approved copy exactly; all Quick Start and technical sections remain.
The public repository was created without generated files, the remote Description was verified against the exact text above,
and origin points to that repository. GitHub private vulnerability reporting was enabled as the security contact channel.
Release Notes remain separate from the introduction. Actions, fresh clone, remote/page audits and tag/release results will be recorded after execution.
The user reports M13 manual acceptance complete; real Provider tests were not rerun by the agent.

## Actual GitHub checks (2026-09-25)

Initial main commit: `699fc2834fb5805df7b9c29aaf5687cdc933ae6d`.
Staged audit: 82 allowed public files, zero findings. Two trailing blank lines were removed before commit.
README/URL update regression: 235 pytest tests and 365 subtests passed (42.44 s).
Main push succeeded without force.

[Initial GitHub Actions run](https://github.com/billstar0128-jpg/AutoQuestion/actions/runs/36117722201): all three Windows jobs passed on the first run; no CI fix was needed.

| CPython | pytest | unittest |
|---|---|---|
| 3.10.11 | 230 passed, 5 skipped, 362 subtests; 25.55 s | 235 run, 5 skipped; 22.444 s |
| 3.12.10 | 230 passed, 5 skipped, 362 subtests; 24.93 s | 235 run, 5 skipped; 21.845 s |
| 3.14.7 | 230 passed, 5 skipped, 362 subtests; 19.54 s | 235 run, 5 skipped; 16.449 s |

Each job also passed compileall, pip check, release audit, version and Doctor.
The five skips are the explicitly documented interactive desktop tests, not test failures.
The local full suite did not skip them; visible smoke evidence is separately attributed above.

GitHub page/API audit passed: remote Description and README source match approved local content;
rendered README HTML has headings, Chinese text and all technical sections; GitHub detects Apache-2.0.
SECURITY, PRIVACY, CONTRIBUTING, CHANGELOG, Actions, both Issue templates and the PR template exist.
Private vulnerability reporting is enabled. Relative links pass the candidate audit.

## Real GitHub fresh clone

Cloned the public HTTPS repository into a new temporary directory after CI passed, without reusing the
development tree, virtual environment, user configuration or credentials. New APPDATA, LOCALAPPDATA,
USERPROFILE and temporary directories were used. No real provider calls were made.

Actual main.py entrypoint (runpy bootstrap; only stdin isatty overridden for scripted input):
Offline Demo first-run Setup -> READY -> ESC -> STOPPED passed; second startup skipped Setup and
passed the same lifecycle; an AUTO override reached READY without opening a Demo, then exited normally.
These checks used a separate temporary configuration profile.

Fresh-clone URL/Model tests: all 15 unittest methods passed (0.632 s).
An additional real main.py --setup invocation rejected `model-name` at Base URL before the Model
prompt, rejected `https://example.com` at Model ID, then cancelled without saving or starting the app.
The temporary harness initially matched an earlier introductory mention of Model ID; its assertion
was corrected to match the exact field prompt. No product change was needed.

Visible fresh-clone main.py --open-demo passed with INPUT_MODE=dom and LLM_PROVIDER=fake:
real managed Chromium opened the local DOM Demo, a native F8 hotkey message produced the fake
answer, READY returned, and a native ESC hotkey message exited with STOPPED and code 0.
This was an automated hotkey-message test, not a claim of physical key presses or real-model accuracy.
Browser downloads used the fresh venv's private Playwright runtime; the slow CDN transfer was allowed
to finish by replacing the temporary orchestration wait, without changing product timeouts or reusing an old runtime.

Remote secret audit passed: 82 tracked public files, one complete initial commit, 82 historical file
versions, zero findings. Candidate inventory exactly matches tracked files. No private screenshots,
logs, user config, real credentials or .env are tracked. Only .env.example is public.
Scans use the project's limited patterns plus GitHub token patterns; they are not a guarantee against every possible secret format.

Fresh-clone full regression on local CPython 3.14.6: pytest 235 passed, 365 subtests passed, zero
failures/skips (32.57 s); unittest 235 passed, zero failures/skips (31.470 s).
The real headless Chromium AUTO --open-demo test verified DOM -> Canvas fallback to VISION -> DOM,
complete Canvas drawing, no selected answer inputs, and browser/thread cleanup.
First-run optional Demo No/Yes and subsequent normal startup also passed.
Runtime/development installs, editable metadata install, version, Doctor, --show-config,
compileall, pip check and release_audit.py all passed. The shared isolated profile remained free
of saved app configuration; dedicated CLI profiles contain only offline test configuration.

Release scope remains 0.1.0rc1, source-only, Pre-release and not Latest/Stable. No binaries or PyPI
publication. Final tag/release status is available on the repository's GitHub Releases page.

## Publication result

Release commit: `3f6b5b92a1d9e9af38203ae6bd5fc783f36dbf21`.
[Final release-commit CI](https://github.com/billstar0128-jpg/AutoQuestion/actions/runs/36151859299)
passed all three Python jobs. This commit changes only six Markdown documents relative to the
fully tested fresh clone at `699fc2834fb5805df7b9c29aaf5687cdc933ae6d`.

The initial real GitHub clone and full tests succeeded. A later attempt to fast-forward its
documentation hit two Git HTTPS connection resets and a bounded retry timeout. GitHub REST remained
available: the remote comparison confirmed unchanged program source; all six changed documents
were fetched, matched against audited local files and scanned; the full remote tree matched the
82-file allowed inventory. This documentation sync network issue did not invalidate the earlier
fresh-clone install or regression. No secrets were found, and no force push was used.

The lightweight v0.1.0rc1 tag was created through GitHub REST and locally at the exact release
commit. [GitHub Pre-release](https://github.com/billstar0128-jpg/AutoQuestion/releases/tag/v0.1.0rc1)
was created with prerelease=true and latest=false; it is not a draft and has no uploaded assets.
Its body exactly matches the separate Release Notes document. GitHub supplies the source archives.
No v0.1.0 Stable release was created. This completion record follows the immutable release commit;
it does not move or replace the RC tag.
