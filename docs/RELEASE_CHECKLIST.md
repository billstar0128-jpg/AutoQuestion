# Release Checklist — 0.1.0rc1

M14 publication checks。用户已明确授权公开 main push 和 v0.1.0rc1 Pre-release；Stable 不在本轮范围内。历史自动结果见 [Validation](VALIDATION_M13.md)，人工步骤见 [M13 Acceptance](MANUAL_ACCEPTANCE_M13.md)。下面未完成项不能靠推断勾选。

## Local evidence

M13 historical checks below remain recorded. M14 Phase A passed, including the user's foreground smoke (1 test, 9.441 s); see [M14 validation](VALIDATION_M14.md). The user reports M13 manual acceptance complete; individual real-provider checks were not rerun by the agent.

- [x] M14 offline URL / Model immediate validation and regression tests
- [x] M14 full pytest / unittest / compileall / pip check / Doctor
- [x] M14 visible browser smoke (user foreground run passed; earlier activation failures recorded)
- [x] M14 Git tracked / staged / history publication preflight
- [x] M14 real GitHub Actions green
- [x] M14 fresh GitHub clone and remote secret audit
- [x] M14 repository page audit
- [x] M14 v0.1.0rc1 tag and Pre-release

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

## Publication gates

- [x] License selected: Apache-2.0; standard text in [LICENSE](../LICENSE)
- [x] Attribution and chosen license reviewed (standard Apache-2.0; no bundled third-party source requiring NOTICE)
- [x] Real repository URLs and private security contact supplied
- [x] Staged-file audit before initial commit/push and complete remote history audit passed
- [x] Real GitHub fresh clone passes (supersedes the historical local-copy check)
- [x] User explicitly authorized M14 public push and RC pre-release
- [x] CI passes on GitHub: Windows CPython 3.10.11 / 3.12.10 / 3.14.7
- [x] RC tag / Pre-release authorized; Stable remains a separate future user decision

M14 publication gates complete. License: Apache-2.0. The historical user-manual checklist above remains attributed to the user's acceptance, not agent reruns.
Repository: https://github.com/billstar0128-jpg/AutoQuestion
Release: [v0.1.0rc1 Pre-release](https://github.com/billstar0128-jpg/AutoQuestion/releases/tag/v0.1.0rc1).
CI and publication results are recorded in the M14 validation document. Stable remains unpublished.
