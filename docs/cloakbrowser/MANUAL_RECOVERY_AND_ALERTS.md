# Manual browser recovery and verification state alerts

## Behavior

- A transient screenshot or status HTTP 500 during navigation causes retry, not immediate local session deletion. Explicit session revocation (401/403/404/409) still disconnects.
- The **Browsers** sidebar item links to authenticated manual control on `/manual-browser/`. It is the same persistent CloakBrowser, not a second container.
- On first recognized Cloudflare or Google verification in a scheduled shared-browser watch, persist `manual_attention_reason`, preserve normal watch history and enqueue one notification via existing watch/tag/global Apprise URLs (Telegram included when configured).
- Repeated failures with the same verification reason do not repeatedly notify. The regular scheduler remains enabled; it is not a permanent pause.
- The next successful check clears the marker and enqueues one recovery notification. Notification-muted watches do not alert.
- An Add Watch visual preview displays the verification page screenshot and a warning, but never stores challenge HTML as a temporary successful watch baseline; use **人工操作** and retry after manual verification.
- Recognition is conservative: unknown challenge pages may not be detected, so check actual website behavior.

## Deployment and testing

Apply this ZIP's `payload/` entries to your repository root:

```bash
docker compose build
docker compose up -d --force-recreate
```

Test a normal website and a known challenge page, manual navigation and page reload, recovery after transient status errors, a first verification alert, no repeat alert during continued verification, and a later recovery alert. No cookies or login tokens are sent in notifications.
