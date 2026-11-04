"""Shared desktop viewport dimensions for watch pages, dry runs and manual fixed mode."""
import os


def desktop_viewport():
    def read(key, default, low, high):
        try:
            value = int(os.environ.get(key, str(default)))
        except (TypeError, ValueError):
            value = default
        return max(low, min(high, value))
    return {
        'width': read('CLOAKBROWSER_VIEWPORT_WIDTH', 1366, 320, 2560),
        'height': read('CLOAKBROWSER_VIEWPORT_HEIGHT', 900, 240, 1800),
    }
