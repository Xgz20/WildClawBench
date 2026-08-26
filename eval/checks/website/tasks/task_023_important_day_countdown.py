from __future__ import annotations

from datetime import date, timedelta

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_content_editing", "c03_rule_settlement",
    "c04_rule_settlement", "c05_rule_settlement", "c06_rule_settlement",
    "c07_content_editing", "c08_form_validation", "c11_rule_settlement",
]
VISUAL_KEYS = ["c09_page_layout", "c10_responsive_layout"]


async def _add(page, name, offset):
    await fill_any_named(page, ["名称", "日子名称", "重要日子"], name)
    target = (date.today() + timedelta(days=offset)).isoformat()
    dates = page.locator('input[type="date"]')
    if not await dates.count(): raise AssertionError("日期输入框不存在")
    await dates.first.fill(target)
    await click_named_any(page, ["记下来", "添加", "保存"])
    return target


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def initial():
        await reset_page(page)
        await _add(page, "体检", 30); await _add(page, "交房租", 1)
        return await contains_texts(page, ["重要日子", "名称", "日期", "体检", "30", "交房租", "1"])
    await r.check("c01_information_organization", initial)

    async def thirty():
        await reset_page(page); target = await _add(page, "体检", 30)
        return await contains_texts(page, ["体检", target, "30"])
    await r.check("c02_content_editing", thirty)

    async def today_check():
        await reset_page(page); await _add(page, "今天这件事", 0)
        text = await page.locator("body").inner_text()
        return "今天这件事" in text and ("就是今天" in text or "0 天" in text or "0天" in text)
    await r.check("c03_rule_settlement", today_check)

    async def tomorrow_and_thirty():
        await reset_page(page); await _add(page, "明天", 1); await _add(page, "体检", 30)
        return await contains_texts(page, ["明天", "1", "体检", "30"])
    await r.check("c04_rule_settlement", tomorrow_and_thirty)

    async def yesterday():
        await reset_page(page); await _add(page, "昨天的事", -1)
        return await contains_texts(page, ["昨天的事", "过去", "1"])
    await r.check("c05_rule_settlement", yesterday)

    async def long_date():
        await reset_page(page); await _add(page, "远期计划", 400)
        return await contains_texts(page, ["远期计划", "400"])
    await r.check("c06_rule_settlement", long_date)

    async def deletion():
        await reset_page(page)
        await _add(page, "保留甲", 10); await _add(page, "删掉我", 20); await _add(page, "保留乙", 30)
        row = page.locator("li, article, [class*='item'], [class*='card']").filter(has_text="删掉我").first
        await row.get_by_role("button", name="删除", exact=False).click()
        body = await page.locator("body").inner_text()
        return "删掉我" not in body and "保留甲" in body and "保留乙" in body
    await r.check("c07_content_editing", deletion)

    async def validation():
        await reset_page(page)
        dates = page.locator('input[type="date"]')
        await dates.first.fill(date.today().isoformat())
        await click_named_any(page, ["记下来", "添加", "保存"])
        missing_name = await contains_texts(page, ["名称"])
        await dates.first.fill("")
        await fill_any_named(page, ["名称", "日子名称"], "没有日期")
        await click_named_any(page, ["记下来", "添加", "保存"])
        body = await page.locator("body").inner_text()
        return missing_name and "日期" in body and "没有日期" not in body
    await r.check("c08_form_validation", validation)

    async def countdowns_reconcile():
        await reset_page(page)
        tomorrow = await _add(page, "明天", 1)
        later = await _add(page, "三十天后", 30)
        body = await page.locator("body").inner_text()
        return (
            await contains_texts(page, ["明天", tomorrow, "1", "三十天后", later, "30"])
            and not any(value in body for value in ["NaN", "Infinity", "undefined", "Invalid Date"])
        )
    await r.check("c11_rule_settlement", countdowns_reconcile)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    await _add(page, "体检", 30); await _add(page, "生日", 100); await _add(page, "交房租", 1)
    shots = [await capture(page, screenshot_dir, "desktop-countdowns", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-countdowns", full_page=True))
    return shots
