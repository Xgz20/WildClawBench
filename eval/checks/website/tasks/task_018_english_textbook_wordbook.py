from __future__ import annotations

import re

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_cross_region_linkage", "c03_lists_tables",
    "c04_lists_tables", "c05_lists_tables", "c06_operation_feedback", "c07_detail_display",
    "c08_rule_settlement", "c09_rule_settlement", "c10_rule_settlement",
    "c11_rule_settlement", "c12_operation_feedback", "c13_information_organization",
    "c14_detail_display", "c15_rule_settlement", "c16_rule_settlement",
    "c17_lists_tables", "c18_lists_tables", "c19_state_persistence",
]
VISUAL_KEYS = ["c20_page_layout", "c21_visual_style", "c22_component_style", "c23_responsive_layout"]


async def _select_with(page, text):
    selects = page.locator("select")
    for i in range(await selects.count()):
        options = await selects.nth(i).locator("option").all_text_contents()
        match = next((option for option in options if text in option), None)
        if match:
            await selects.nth(i).select_option(label=match)
            return True
    return False


async def _start_learn(page, book="必修一", unit="Unit 1"):
    await click_named_any(page, ["进入单词学习", "开始学习", "单词学习"])
    await _select_with(page, book); await _select_with(page, unit)
    await click_named_any(page, ["开始学这一组", "开始学习"])


async def _answer(page, label, count):
    seen = []
    for _ in range(count):
        body = await page.locator("body").inner_text()
        seen.append(body)
        await click_named_any(page, [label])
        try:
            await click_named_any(page, ["下一个", "继续"])
        except AssertionError:
            pass
    return seen


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def initial():
        await reset_page(page)
        body = await page.locator("body").inner_text()
        nums = [int(x) for x in re.findall(r"\b\d{3,}\b", body)]
        return await contains_texts(page, ["课本单词本", "已掌握", "学习中", "待学习", "单词学习", "单词考察", "考察记录"]) and any(n >= 500 for n in nums)
    await r.check("c01_information_organization", initial)

    async def books_units():
        await reset_page(page); await click_named_any(page, ["进入单词学习", "开始学习", "单词学习"])
        first = " ".join(await page.locator("option").all_text_contents())
        await _select_with(page, "必修二")
        second = " ".join(await page.locator("option").all_text_contents())
        return "Welcome Unit" in first and all(f"Unit {i}" in first for i in range(1, 6)) and "Welcome Unit" not in second and all(f"Unit {i}" in second for i in range(1, 6))
    await r.check("c02_cross_region_linkage", books_units)

    async def todo_list():
        await reset_page(page); await click_named_any(page, ["待学习"])
        return await contains_texts(page, ["单元", "音标"])
    await r.check("c03_lists_tables", todo_list)

    async def words_one():
        await reset_page(page); await click_named_any(page, ["待学习"])
        return await contains_texts(page, ["teenager", "/ˈtiːneɪdʒə(r)/", "青少年", "architecture", "建筑设计", "heritage", "遗产", "habitat", "栖息地"])
    await r.check("c04_lists_tables", words_one)

    async def words_two():
        await reset_page(page); await click_named_any(page, ["待学习"])
        return await contains_texts(page, ["species", "/ˈspiːʃiːz/", "物种", "illegal", "不合法", "athlete", "运动员", "fluent", "流利"])
    await r.check("c05_lists_tables", words_two)

    async def reveal():
        await reset_page(page); await _start_learn(page)
        before = await page.locator("body").inner_text()
        await click_named_any(page, ["认识"])
        after = await page.locator("body").inner_text()
        return "认识" in before and "不认识" in before and len(after) > len(before) and any(t in after for t in ["例句", "释义", "下一个"])
    await r.check("c06_operation_feedback", reveal)

    async def details():
        await reset_page(page); await _start_learn(page); await click_named_any(page, ["认识"])
        return await contains_texts(page, ["例句", "释义"]) and await page.locator("[class*='phonetic'], [class*='meaning'], [class*='example']").count() >= 2
    await r.check("c07_detail_display", details)

    async def first_round():
        await reset_page(page); await _start_learn(page); await _answer(page, "认识", 10)
        await click_named_any(page, ["回到首页", "返回首页"])
        return await contains_texts(page, ["已掌握", "0", "学习中", "10", "待学习"])
    await r.check("c08_rule_settlement", first_round)

    async def second_round():
        await reset_page(page); await _start_learn(page); await _answer(page, "认识", 10)
        await click_named_any(page, ["回到首页", "返回首页"]); await _start_learn(page); await _answer(page, "认识", 10)
        await click_named_any(page, ["回到首页", "返回首页"])
        return await contains_texts(page, ["已掌握", "10", "学习中", "0"])
    await r.check("c09_rule_settlement", second_round)

    async def unknown_review():
        await reset_page(page); await _start_learn(page)
        await click_named_any(page, ["不认识"])
        try: await click_named_any(page, ["下一个", "继续"])
        except AssertionError: pass
        await _answer(page, "认识", 9)
        return await contains_texts(page, ["再考", "1"])
    await r.check("c10_rule_settlement", unknown_review)

    async def repeated_unknown():
        await reset_page(page); await _start_learn(page)
        await click_named_any(page, ["不认识"])
        try: await click_named_any(page, ["下一个", "继续"])
        except AssertionError: pass
        await _answer(page, "认识", 9)
        before = await page.locator("body").inner_text()
        await click_named_any(page, ["不认识"])
        try: await click_named_any(page, ["下一个", "继续"])
        except AssertionError: pass
        after = await page.locator("body").inner_text()
        return "再考" in before and "再考" in after and "完成" not in after
    await r.check("c11_rule_settlement", repeated_unknown)

    async def completion():
        await reset_page(page); await _start_learn(page); await _answer(page, "认识", 10)
        return await contains_texts(page, ["完成"]) and await page.get_by_role("button", name=re.compile("回到首页|再来一组")).count() > 0
    await r.check("c12_operation_feedback", completion)

    async def quiz_scope():
        await reset_page(page); await click_named_any(page, ["进入单词考察", "单词考察", "开始考察"])
        await _select_with(page, "必修一"); await _select_with(page, "Unit 5")
        before = await contains_texts(page, ["41"])
        await click_named_any(page, ["开始考察"])
        return before and await contains_texts(page, ["1", "41"])
    await r.check("c13_information_organization", quiz_scope)

    async def quiz_options():
        await reset_page(page); await click_named_any(page, ["进入单词考察", "单词考察"]); await _select_with(page, "Unit 5"); await click_named_any(page, ["开始考察"])
        options = page.get_by_role("button").filter(has_not_text=re.compile("首页|返回"))
        texts = [t.strip() for t in await options.all_text_contents() if t.strip()]
        return len(set(texts)) >= 4 and await page.locator("body").inner_text() != ""
    await r.check("c14_detail_display", quiz_options)

    async def complete_quiz_structure():
        await reset_page(page); await click_named_any(page, ["进入单词考察", "单词考察"]); await _select_with(page, "Unit 5")
        return await contains_texts(page, ["41", "百分", "考察"])
    await r.check("c15_rule_settlement", complete_quiz_structure)

    async def progress_mapping():
        await reset_page(page); await click_named_any(page, ["进入单词考察", "单词考察"]); await _select_with(page, "Unit 5"); await click_named_any(page, ["开始考察"])
        before = await page.locator("body").inner_text()
        buttons = page.get_by_role("button")
        for i in range(await buttons.count()):
            if await buttons.nth(i).is_visible() and (await buttons.nth(i).inner_text()).strip() not in ("返回首页", "先回首页"):
                await buttons.nth(i).click(); break
        after = await page.locator("body").inner_text()
        return before != after and ("2" in after or "下一" in after)
    await r.check("c16_rule_settlement", progress_mapping)

    async def record_area():
        await reset_page(page)
        return await contains_texts(page, ["考察记录", "平均分"])
    await r.check("c17_lists_tables", record_area)

    async def record_detail():
        await reset_page(page)
        return await contains_texts(page, ["考察记录"]) and await page.locator("table, ol, ul, [class*='record']").count() > 0
    await r.check("c18_lists_tables", record_detail)

    async def persistence():
        await reset_page(page); await _start_learn(page); await click_named_any(page, ["认识"])
        await page.reload(wait_until="domcontentloaded")
        return await contains_texts(page, ["课本单词本", "我的进度"])
    await r.check("c19_state_persistence", persistence)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900}); await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-wordbook", full_page=True)]
    try:
        await _start_learn(page); shots.append(await capture(page, screenshot_dir, "desktop-word-card", full_page=False))
    except Exception: pass
    await page.set_viewport_size({"width": 375, "height": 812}); await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-wordbook", full_page=True))
    return shots
