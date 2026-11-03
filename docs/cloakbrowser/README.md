# CloakBrowser — Round 1 A+B

Status: source-level/static validation complete. **Docker and live Chromium have NOT been executed** in the assistant's environment, because Docker is unavailable. Run the tests below on your Docker host.

This version uses the original author's **changedetection.io-cloak-browser 0.1.1** plugin, and **cloakbrowser 0.7.0**. It still creates and closes a separate browser on every check. Shared BrowserManager, multiple tabs on one instance, persistent user profile and manual browser control belong to later rounds.

## Deploy from the repository root

After applying `payload/`:

```bash
cp .env.cloakbrowser.example .env
# Replace the license key in .env; do not commit this file.
mkdir -p datastore cloakbrowser-home
chmod 700 cloakbrowser-home
docker compose -f docker-compose.cloakbrowser.yml build --pull
docker compose -f docker-compose.cloakbrowser.yml run --rm changedetection python /app/scripts/cloakbrowser-smoke.py
docker compose -f docker-compose.cloakbrowser.yml run --rm changedetection python /app/scripts/cloakbrowser-smoke.py --browser
docker compose -f docker-compose.cloakbrowser.yml up -d
```

Open `http://127.0.0.1:5000` on the host. In a watch's Edit > Fetch select **CloakBrowser**. Test a normal webpage, a JavaScript-rendered site, a screenshot and Browser Steps manually.

The first real launch downloads a CloakBrowser Chromium binary from CloakHQ and needs network access and a valid license key. It is a third-party precompiled binary, not audited by changedetection.io's maintainer. The container mounts `cloakbrowser-home` only for downloaded binary/cache files; **it does not persist site logins or cookies**. The future persistent profile must be a separately mounted directory.

## Troubleshoot

```bash
docker compose -f docker-compose.cloakbrowser.yml logs --tail=150 changedetection
docker compose -f docker-compose.cloakbrowser.yml run --rm changedetection python -m cloakbrowser info --quick
```

The default web port binds to loopback; LAN access requires explicitly changing the port binding or using a reverse proxy with authentication. Do not expose debugging CDP endpoints to the Internet.

The plugin's `setup.py` requests a pip-installed changedetection.io distribution. The dedicated Dockerfile uses `--no-deps` so that upstream PyPI code cannot shadow your Fork, and separately installs `httpx`, while the base image supplies Playwright and cryptography. The dedicated image rejects a missing Playwright install.

On dependency updates, verify plugin entry point, actual Chromium binary, licenses and screenshot/browser-steps compatibility. For rollback, keep the original `Dockerfile` and `docker-compose.yml`; neither is modified.
