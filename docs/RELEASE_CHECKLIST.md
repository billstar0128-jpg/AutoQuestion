# Release Checklist — 0.1.0rc1

READY FOR MANUAL PUBLICATION REVIEW。不是自动发布许可。自动结果见 [Validation](VALIDATION_M13.md)，人工步骤见 [M13 Acceptance](MANUAL_ACCEPTANCE_M13.md)。下面未完成项不能靠推断勾选。

## Local evidence

M13 historical checks below remain recorded. M14 Phase A passed, including the user's foreground smoke (1 test, 9.441 s); see [M14 validation](VALIDATION_M14.md). The user reports M13 manual acceptance complete; individual real-provider checks were not rerun by the agent.

- [x] M14 offline URL / Model immediate validation and regression tests
- [x] M14 full pytest / unittest / compileall / pip check / Doctor
- [x] M14 visible browser smoke (user foreground run passed; earlier activation failures recorded)
- [ ] M14 Git tracked / staged / history publication preflight
- [ ] M14 real GitHub Actions green
- [ ] M14 fresh GitHub clone and remote secret audit
- [ ] M14 repository page audit
- [ ] M14 v0.1.0rc1 tag and Pre-release

- [x] All automated tests pass
- [x] pytest pass
- [x] unittest pass
- [x] compileall pass
- [x] pip check pass
- [x] Windows local smoke passes
- [x] AUTO normal startup does not open Demo (automated)
- [x] --open-demo DOM / Canvas / return flow passes (automated)
- [x] Secret audit passes
- [x] Audited public candidates contain no private screenshots / personal data
- [x] Clean-room install passes
- [x] README Quick Start verified in isolated source copy
- [x] Provider docs agree with implemented presets
- [x] Version consistent
- [x] Relative documentation links valid
- [x] CI configuration prepared

## User manual acceptance

- [ ] First-run Setup manually passes (default No and explicit Yes)
- [ ] DeepSeek real-provider manual test passes
- [ ] API Key masking / paste / backspace manually passes
- [ ] Windows Credential persistence manually passes
- [ ] Ordinary AUTO no Demo, direct READY
- [ ] --open-demo works
- [ ] DOM works
- [ ] Vision works
- [ ] Canvas fallback works
- [ ] Browser → WPS → Browser works
- [ ] single_choice works
- [ ] multiple_choice works
- [ ] true_false works
- [ ] BUSY / debounce / ESC / Ctrl+C and three restarts pass
- [ ] Second startup skips full Setup and Demo
- [ ] --show-config leaks no secret
- [ ] --doctor leaks no secret

## Publication gates — pending

- [x] License selected: Apache-2.0; standard text in [LICENSE](../LICENSE)
- [ ] Attribution and chosen license reviewed
- [x] Real repository URLs and private security contact supplied
- [ ] Staged-file and history secret audit completed before commit/push
- [ ] Local clone passes (requires a local commit; otherwise N/A)
- [x] User explicitly authorized M14 public push and RC pre-release
- [ ] CI later passes on GitHub
- [ ] Stable version / tag / GitHub Release separately decided

License selection complete: Apache-2.0. Other publication gates remain pending.
Repository: https://github.com/billstar0128-jpg/AutoQuestion
CI and publication results are recorded in the M14 validation document after execution.
