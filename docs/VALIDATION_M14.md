# M14 Validation / Publication Status

Phase A: PASS. The user ran the unchanged visible smoke in a foreground terminal: 1 test passed in 9.441 s.
Phase B: publication in progress; CI and fresh GitHub clone gates remain pending until recorded below.
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
