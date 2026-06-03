from typing import Dict, Any
import asyncio

from ezply.services.autofill import load_autofill_profile


class PlaywrightNotAvailable(RuntimeError):
    pass


async def _safe_import_playwright():
    try:
        from playwright.async_api import async_playwright

        return async_playwright
    except Exception as e:
        raise PlaywrightNotAvailable("Playwright is not installed or browser binaries missing") from e


async def assisted_apply_greenhouse(job_url: str, passphrase: str, confirm_submit: bool = False) -> Dict[str, Any]:
    """Attempt to open a Greenhouse job apply page and pre-fill common fields using saved autofill data.

    This implementation does NOT submit by default. It returns the mapping of fields it filled and a `ready_to_submit` flag.
    If Playwright is not available, raises PlaywrightNotAvailable.
    """
    async_playwright = await _safe_import_playwright()
    profile = await load_autofill_profile(passphrase)

    # Use async Playwright API
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)

        filled: Dict[str, Any] = {}

        # try common selectors
        selectors = {
            "name": ["input[name='name']", "input[id*='name']", "input[placeholder*='Name']"],
            "email": ["input[type='email']", "input[name='email']", "input[id*='email']"],
            "phone": ["input[name='phone']", "input[id*='phone']", "input[placeholder*='Phone']"],
        }

        for key, sels in selectors.items():
            value = profile.get(key) or (profile.get("phone") if key == "phone" else profile.get(key))
            if not value:
                continue
            for sel in sels:
                try:
                    handle = await page.query_selector(sel)
                    if handle:
                        await page.fill(sel, str(value))
                        filled[sel] = value
                        break
                except Exception:
                    continue

        ready_to_submit = False
        # We do not auto-submit unless confirm_submit is True. If True, attempt a click on submit buttons.
        if confirm_submit:
            try:
                submit_handle = await page.query_selector("button[type='submit']")
                if submit_handle:
                    await submit_handle.click()
                    ready_to_submit = True
            except Exception:
                ready_to_submit = False

        await browser.close()

    return {"filled": filled, "ready_to_submit": ready_to_submit, "job_url": job_url}
