from __future__ import annotations

import re
from pathlib import Path
from typing import Awaitable, Callable


CheckBody = Callable[[], Awaitable[object]]


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).replace(",", "").replace("，", "")


async def body_text(scope) -> str:
    if callable(getattr(scope, "locator", None)):
        body = scope.locator("body")
        if await body.count():
            return await body.inner_text()
    return await scope.inner_text()


async def contains_texts(page, expected: list[str]) -> bool:
    actual = normalized(await body_text(page))
    return all(normalized(item) in actual for item in expected)


async def element_contains_texts(page, anchor: str, expected: list[str]) -> bool:
    locator = page.get_by_text(anchor, exact=False)
    if not await locator.count():
        return False
    value = normalized(await locator.first.inner_text())
    return all(normalized(item) in value for item in expected)


async def ancestor_contains_texts(page, anchor: str, expected: list[str]) -> bool:
    """Check the nearest bounded content region around an anchor label."""
    locator = page.get_by_text(anchor, exact=False)
    if not await locator.count():
        return False
    actual = await locator.first.evaluate(
        """(node) => {
            const values = [];
            let current = node.parentElement || node;
            for (let depth = 0; current && depth < 7; depth += 1) {
                if (['BODY', 'HTML'].includes(current.tagName)) break;
                values.push(current.innerText || current.textContent || '');
                current = current.parentElement;
            }
            return values;
        }"""
    )
    candidates = actual if isinstance(actual, list) else [actual]
    return any(
        all(normalized(item) in normalized(str(candidate or "")) for item in expected)
        for candidate in candidates
    )


async def visualization_contains_texts(page, anchor: str, expected: list[str]) -> bool:
    """Read labels rendered as DOM/SVG text or captured Canvas text near a heading."""
    locator = page.get_by_text(anchor, exact=False)
    if not await locator.count():
        return False
    actual = await locator.first.evaluate(
        """(node) => {
            let current = node;
            for (let depth = 0; current && depth < 8; depth += 1) {
                if (current.tagName === 'BODY' || current.tagName === 'HTML') break;
                const visuals = current.querySelectorAll(
                    'canvas, svg, figure, [role="img"]'
                );
                if (visuals.length) {
                    const parts = [current.innerText || current.textContent || ''];
                    for (const visual of visuals) {
                        if (visual.tagName === 'CANVAS') {
                            parts.push(...(visual.__wildclawbenchRenderedTexts || []));
                        } else {
                            parts.push(visual.textContent || '');
                        }
                    }
                    return parts.join('\\n');
                }
                current = current.parentElement;
            }
            return '';
        }"""
    )
    value = normalized(str(actual or ""))
    return all(normalized(item) in value for item in expected)


async def text_absent(page, expected: list[str]) -> bool:
    actual = normalized(await body_text(page))
    return all(normalized(item) not in actual for item in expected)


async def click_named(page, name: str) -> None:
    for role in ("button", "link", "tab", "checkbox", "radio"):
        locator = page.get_by_role(role, name=name, exact=True)
        if await locator.count():
            await locator.first.click()
            return
    exact_text = page.get_by_text(name, exact=True)
    if await exact_text.count():
        await exact_text.first.click()
        return
    partial_text = page.get_by_text(name, exact=False)
    if await partial_text.count():
        await partial_text.first.click()
        return
    raise AssertionError(f"EVALUATOR_AMBIGUOUS_LOCATOR: no control named {name!r}")


async def fill_named(page, name: str, value: str) -> None:
    locator = page.get_by_label(name, exact=False)
    if not await locator.count():
        locator = page.get_by_placeholder(name, exact=False)
    if not await locator.count():
        raise AssertionError(f"EVALUATOR_AMBIGUOUS_LOCATOR: no field named {name!r}")
    await locator.first.fill(value)


async def fill_any_named(page, names: list[str], value: str) -> None:
    # Exact semantic matches win so a generic page search field cannot shadow a modal field.
    for name in names:
        for getter in (page.get_by_label, page.get_by_placeholder):
            locator = getter(name, exact=True)
            if await locator.count():
                await locator.first.fill(value)
                return
    for name in names:
        for getter in (page.get_by_label, page.get_by_placeholder):
            locator = getter(name, exact=False)
            if await locator.count():
                await locator.first.fill(value)
                return
    raise AssertionError(
        f"EVALUATOR_AMBIGUOUS_LOCATOR: no field matching {names!r}"
    )


async def select_named(page, label: str, value: str) -> None:
    locator = page.get_by_label(label, exact=False)
    if await locator.count():
        tag = await locator.first.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            try:
                await locator.first.select_option(label=value)
            except Exception:
                await locator.first.select_option(value=value)
            return
    await click_named(page, value)


async def reset_page(page, *, clear_storage: bool = True) -> None:
    await page.goto("http://127.0.0.1:4173", wait_until="domcontentloaded")
    if clear_storage:
        await page.evaluate(
            """async () => {
                localStorage.clear();
                sessionStorage.clear();
                if (indexedDB.databases) {
                    for (const db of await indexedDB.databases()) {
                        if (db.name) indexedDB.deleteDatabase(db.name);
                    }
                }
            }"""
        )
        await page.reload(wait_until="domcontentloaded")


class CheckRecorder:
    def __init__(self, page, screenshot_dir: Path):
        self.page = page
        self.screenshot_dir = screenshot_dir
        self.results: dict[str, dict] = {}

    async def check(self, key: str, body: CheckBody) -> None:
        try:
            raw = await body()
            passed = bool(raw)
            evidence = raw if isinstance(raw, dict) else {"assertion": passed}
            self.results[key] = {"score": 1.0 if passed else 0.0, "evidence": evidence}
            if not passed:
                raise AssertionError("assertion returned false")
        except Exception as exc:
            screenshot = self.screenshot_dir / f"failure-{key}.png"
            try:
                await self.page.screenshot(path=str(screenshot), full_page=True)
            except Exception:
                screenshot = None
            self.results[key] = {
                "score": 0.0,
                "error": f"{type(exc).__name__}: {exc}",
                "evidence": {"screenshot": screenshot.name if screenshot else ""},
            }


async def capture(page, screenshot_dir: Path, name: str, *, full_page: bool = True) -> dict:
    path = screenshot_dir / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full_page)
    return {"name": name, "path": f"screenshots/{path.name}", "mime_type": "image/png"}
