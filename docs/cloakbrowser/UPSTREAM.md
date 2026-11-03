# Provenance and version matrix — Round 1 A+B

- Application: user's uploaded changedetection.io.zip (existing files reused unchanged, not fetched from GitHub). Baseline Dockerfile, compose, entrypoint and plugin interface inspected.
- Plugin: https://github.com/dgtlmoon/changedetection.io-cloak-browser , `changedetection.io-cloak-browser==0.1.1`, PyPI release 2026-03-17. Register entry point `changedetectionio:cloak_browser`. Source `fetcher.py` uses `launch_async()` and ends each watch by closing Page/Context/Browser. No BrowserManager yet.
- Browser wrapper: https://github.com/CloakHQ/CloakBrowser , `cloakbrowser==0.7.0` (PyPI latest verified 2026-11-02); its Chromium binary is downloaded separately and may vary by release channel. Confirm installed binary by `python -m cloakbrowser info`.
- Base application's Dockerfile: attempts `playwright~=1.56.0` with optional-failure behavior. Dedicated file checks installation and adds runtime Linux libraries.
- First round changes: seven **new** files. No modified/deleted existing files. No source vendoring or plugin code edits.
- Known untested areas: building Docker image, license activation, binary download, live Chromium execution, browser steps UI. Run deployment checks before production.
- Round 2 prerequisite: vendor complete upstream plugin files with Git blob/commit identification, then build a single BrowserManager-owned asyncio loop and persistent Context. Do not pass Playwright objects across different Worker loops or allow a watch to close the shared Context.
- Upgrade checklist: test entry point, check plugin package dependencies, browser wrapper version, Chromium binary version, image libraries, license policy, site cookies and browser steps. Pin tested versions in this document after host verification.
