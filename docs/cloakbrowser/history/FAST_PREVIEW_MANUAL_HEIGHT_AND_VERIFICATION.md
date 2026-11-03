> **Historical note — not current setup instructions.** For current behavior read [../README.md](../README.md), [../OPERATIONS.md](../OPERATIONS.md), [../MANUAL_BROWSER.md](../MANUAL_BROWSER.md) and [../VERIFICATION.md](../VERIFICATION.md).

# Shared CloakBrowser: full-height manual browser, fast preview and verification alerts

## What changed

1. Manual control is a flex column whose screenshot area fills the **remaining browser window height** below the changedetection.io controls. JavaScript computes the available space using the actual top offset, rather than restricting the frame to 75vh. ResizeObserver synchronizes only the manual Playwright Page viewport with the screen area; pointer mapping still uses the displayed image rectangle.
2. Add a Page Watch uses the existing browser-step navigation and screenshot sequence, **without** the additional `CLOAKBROWSER_PAGE_SETTLE_SECONDS` or `CLOAKBROWSER_CHALLENGE_WAIT_SECONDS` delays. The browser's existing navigation, browser-step and screenshot overhead still apply. Detected verification screenshots remain visible with a warning, but must not become a successful monitor baseline.
3. Scheduled **shared** CloakBrowser fetches keep the upstream and the watch-specific extract delay. After the upstream wait, before XPath/HTML extraction, the shared Page lease checks *visible* Google and Cloudflare verification messages; a recognized challenge is treated as a failed fetch. A fallback checks already-fetched HTML when CSS/XPath filters do not match. Other fetcher backends are unchanged.
4. First recognized verification queues an alert via the normal watch/tag/global Apprise channels, including Telegram where configured. Identical repeated verifications do not repeatedly notify. Alert queue state is tracked separately from detection state so missing notification settings can be retried when configured. Successful normal processing (or an unchanged successful checksum) clears the error state and queues one recovery alert if an initial alert was queued.

## Settings

`CLOAKBROWSER_PAGE_SETTLE_SECONDS` and `CLOAKBROWSER_CHALLENGE_WAIT_SECONDS` are no longer used by the Add Watch and shared-fetch paths. Their Compose and example .env entries are removed. Existing entries left in your private `.env` can be removed; they no longer influence these operations.

Upstream `WEBDRIVER_DELAY_BEFORE_CONTENT_READY` and the per-watch **Wait seconds before extracting text** are not modified.

## Important limitations

- Verification detection is intentionally conservative. Some website or language variants may be missed or trigger normal filter errors instead.
- An alert being **queued** does not prove that Telegram delivered it; check notification logs and the configured Apprise URL if delivery fails.
- A fetch that is rejected due to recognized verification does **not** permanently pause the watch. The scheduler retries at the configured interval, preserving successful history. Avoid excessive retry frequency on challenge-heavy websites.
- The new manual Page viewport resize is only for the human-control Page; other monitoring Pages and the persistent Profile remain unchanged.

## Apply and verify locally

Extract the ZIP `payload/` into the repository root (keep paths), then run:

```bash
docker compose build
docker compose up -d --force-recreate
```

Reload the webpage with Ctrl+Shift+R. Test screenshot pointer accuracy after resizing, fast Add Watch previews (normal and challenge pages), first Google/Cloudflare alerts, repeated failures and recovery notifications.
