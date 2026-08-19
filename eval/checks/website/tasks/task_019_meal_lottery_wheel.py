from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_realtime_auto_progress", "c03_rule_settlement",
    "c04_rule_settlement", "c05_rule_settlement",
]
VISUAL_KEYS = ["c06_page_layout", "c07_responsive_layout"]


async def _rotation(page):
    return await page.locator("svg g, canvas, [class*='wheel']").first.evaluate(
        "el => getComputedStyle(el).transform + '|' + (el.getAttribute('transform') || '')"
    )


async def _spin(page):
    await click_named_any(page, ["开始抽签", "再抽一次", "开始", "抽签"])
    await page.wait_for_timeout(4000)


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def wheel_content():
        await reset_page(page)
        labels = [x.strip() for x in await page.locator("svg text, [class*='sector'], [class*='slice']").all_text_contents() if x.strip()]
        forbidden = {"A", "B", "C", "选项 1", "选项 2", "待定"}
        return len(set(labels)) >= 3 and not any(x in forbidden for x in labels)
    await r.check("c01_information_organization", wheel_content)

    async def movement():
        await reset_page(page); before = await _rotation(page)
        await click_named_any(page, ["开始抽签", "开始", "抽签"]); await page.wait_for_timeout(350)
        moving = await _rotation(page)
        await page.wait_for_timeout(3900); stopped = await _rotation(page); await page.wait_for_timeout(400)
        stable = await _rotation(page)
        return before != moving and stopped == stable
    await r.check("c02_realtime_auto_progress", movement)

    async def result_matches():
        await reset_page(page); await _spin(page)
        body = await page.locator("body").inner_text()
        labels = [x.strip() for x in await page.locator("svg text, [class*='sector'], [class*='slice']").all_text_contents() if x.strip()]
        return sum(name in body for name in set(labels)) >= 1 and await contains_texts(page, ["吃"])
    await r.check("c03_rule_settlement", result_matches)

    async def repeated():
        await reset_page(page); results = []
        for _ in range(5):
            await _spin(page)
            result = page.locator("[class*='result'] strong, [class*='winner'], [aria-live] strong")
            results.append((await result.last.inner_text()).strip() if await result.count() else "")
        return all(results) and len(set(results)) >= 2
    await r.check("c04_rule_settlement", repeated)

    async def double_click():
        await reset_page(page)
        button = page.get_by_role("button", name="开始抽签", exact=False)
        await button.click(); disabled = await button.is_disabled()
        if not disabled:
            await button.click()
        await page.wait_for_timeout(4200)
        visible_results = page.locator("[class*='result'] strong:visible, [aria-live] strong:visible")
        return await visible_results.count() == 1 and (await visible_results.first.inner_text()).strip() != ""
    await r.check("c05_rule_settlement", double_click)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900}); await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-wheel", full_page=False)]
    await page.set_viewport_size({"width": 375, "height": 812}); await reset_page(page, clear_storage=False)
    try: await _spin(page)
    except Exception: pass
    shots.append(await capture(page, screenshot_dir, "mobile-wheel-result", full_page=False))
    return shots
