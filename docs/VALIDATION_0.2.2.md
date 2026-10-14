# Native desktop App validation — 2026-10-14

Reported symptom: Windows RegisterHotKey failed with 1409 on F8.

Diagnosis found seven UI backends across source, installed copies and the user's portable test copy. PID 40376 in that test copy owned the active service. A native registration probe returned 1409 before graceful WM_QUIT of that AutoQuestion listener, then successfully registered/unregistered F8 afterward. No physical keystroke, screenshot or model request was generated. Only the confirmed AutoQuestion processes were closed; Chrome and other applications were left alone.

The permanent change adds one UI per Windows session/configuration and a native WebView2 window. Repeated launch activates the existing window. Title-bar close stops new work, shuts down HTTP, joins the runner and releases hotkeys; configuration and Windows credentials remain persistent. Active synchronous provider requests finish or time out during cleanup.

Source native acceptance passed with an isolated profile: actual embedded WebView2, first-run secure Windows credential save, own WM_HOTKEY producing a Fake answer, duplicate process reuse, title-bar close, HTTP closure and F8/ESC re-registration. Exact test credentials were deleted. No paid API request or private screenshot used.

Final local checks: pytest 283 passed, 411 subtests, 63.52 s; unittest 283 passed, 48.887 s, no skips. compileall, pip check, Doctor, metadata/version and candidate audit passed.

Frozen EXE acceptance passed after copying the complete bundle to a separate directory with Chinese characters/spaces and only Windows System32 on PATH. Actual native WebView2 configuration, secure save, Fake F8 result, second-process activation, title-bar close, HTTP shutdown and F8/ESC release passed. Process exit was 0. Runtime/build dependency licenses, Tcl terms and the matching WebView2 SDK's actual LICENSE/NOTICE are bundled. No empty project NOTICE was added.

The explicit native check is separate from visible managed-Chromium focus smoke and real provider/account acceptance; it does not claim those manual paths. Earlier 0.2.1 records remain historical. Real Windows GitHub checks are required before publishing the matching tag and binary.
