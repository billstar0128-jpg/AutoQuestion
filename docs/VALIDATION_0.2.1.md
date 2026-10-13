# Windows App validation — 2026-10-13

The reported failure was reproduced from the public site: the former GitHub Pages home was deliberately a preview, with API Key disabled and no config persistence. This was an inadequate main entry for a usable application. The home is now an App download page; configuration occurs in the actual Windows App.

- Windows x64 portable EXE built with a clean packaging venv and PyInstaller 6.22.3; no personal config, credentials, browser profiles or installed Chromium cache collected.
- Local pytest: 278 passed, 411 subtests, 55.54 s. unittest: 278 passed, 51.644 s. compileall, pip check, source inventory/secret audit passed.
- Executable self-test passed: native capture imports/TLS (no screenshot), real SDK against a synthetic loopback API, compiled WebSocket bridge bind/cleanup, authenticated HTTP save/redaction, own F8 messages producing Fake answers, ESC cleanup and a second run.
- Actual EXE copied into a separate directory containing spaces and Chinese characters. Launched with only Windows System32 on PATH and an isolated AppData, so no project/system Python was used at runtime.
- Real headless browser opened the EXE's own server, completed first-run config, saved a test Key using the actual Windows Credential Manager, confirmed the Key was cleared and absent from config, started to READY, stopped and exited. The exact temporary test credential was removed afterward; existing credentials and settings were unchanged.
- No real service API request, private question, user screenshot or user Key used in acceptance. Paid requests: zero. This validates the App/configuration path, not account balance or every model's behavior.
- Source and extension versions are 0.2.1. Existing 0.2.0 / 0.1.0rc1 tags preserved. App is unsigned; Windows may display publisher warnings. Does not request administrator privileges.
- Archive includes Apache-2.0 plus actual runtime/build dependency licenses, CPython/Tk terms and Tcl 8.6.15's upstream notice. No new empty project NOTICE.

Public site ships only dist/site, with its App download page and a separate preview/. Windows binaries remain in dist/windows and are distributed through Release assets. The site's former preview no longer presents itself as usable online configuration.
