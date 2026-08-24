from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_content_editing", "c03_content_editing",
    "c04_content_editing", "c05_rule_settlement", "c06_rule_settlement",
    "c07_content_editing", "c08_form_validation", "c09_form_validation",
    "c12_rule_settlement",
]
VISUAL_KEYS = ["c10_page_layout", "c11_responsive_layout"]
PEOPLE = ["阿明", "小林", "阿德", "晓晓"]


async def _add_people(page):
    for name in PEOPLE:
        await fill_any_named(page, ["成员姓名", "再加一个人", "姓名"], name)
        await click_named_any(page, ["加入", "添加成员"])


async def _set_payer(page, payer):
    select = page.get_by_label("垫付人", exact=False)
    if not await select.count():
        selects = page.locator("select")
        select = selects.first
    await select.select_option(label=payer)


async def _set_sharers(page, names):
    wanted = set(names)
    for name in PEOPLE:
        boxes = page.get_by_role("checkbox", name=name, exact=False)
        if not await boxes.count():
            continue
        if name in wanted: await boxes.first.check()
        else: await boxes.first.uncheck()


async def _add_expense(page, payer, note, amount, sharers):
    await _set_payer(page, payer)
    await fill_any_named(page, ["花在什么上", "住宿、门票", "用途", "说明"], note)
    await fill_any_named(page, ["金额（元）", "金额", "0.00"], str(amount))
    await _set_sharers(page, sharers)
    await click_named_any(page, ["记一笔", "添加款项", "添加"])


async def _seed(page):
    await reset_page(page); await _add_people(page)
    await _add_expense(page, "阿明", "酒店费", 1200, PEOPLE)
    await _add_expense(page, "小林", "冰淇淋", 60, ["阿德", "晓晓"])


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def initial():
        await reset_page(page)
        return await contains_texts(page, ["分账", "同行", "谁垫", "金额", "谁分", "垫付", "结算", "谁该给谁"])
    await r.check("c01_information_organization", initial)

    async def people():
        await reset_page(page); await _add_people(page)
        return await contains_texts(page, PEOPLE) and await page.get_by_role("checkbox").count() == 4
    await r.check("c02_content_editing", people)

    async def hotel():
        await reset_page(page); await _add_people(page); await _add_expense(page, "阿明", "酒店费", 1200, PEOPLE)
        return await contains_texts(page, ["阿明", "1200", "酒店费", "阿明", "小林", "阿德", "晓晓"])
    await r.check("c03_content_editing", hotel)

    async def icecream():
        await _seed(page)
        row = page.locator("li, tr, article, [class*='item']").filter(has_text="冰淇淋").first
        text = await row.inner_text()
        return all(x in text for x in ["小林", "60", "阿德", "晓晓"]) and "阿明" not in text
    await r.check("c04_content_editing", icecream)

    async def shares():
        await _seed(page)
        return await contains_texts(page, ["阿明", "应摊 300", "小林", "应摊 300", "阿德", "应摊 330", "晓晓", "应摊 330", "1260"])
    await r.check("c05_rule_settlement", shares)

    async def settlement():
        await _seed(page)
        settle = page.locator("section, aside, [class*='settle']").filter(has_text="谁该给谁").last
        text = await settle.inner_text()
        return "阿明" in text and all(name in text for name in ["小林", "阿德", "晓晓"]) and all(amount in text for amount in ["240", "330"])
    await r.check("c06_rule_settlement", settlement)

    async def deletion():
        await _seed(page)
        row = page.locator("li, tr, article, [class*='item']").filter(has_text="冰淇淋").first
        await row.get_by_role("button", name="删除", exact=False).click()
        body = await page.locator("body").inner_text()
        return "冰淇淋" not in body and "1200" in body and body.count("应摊 300") >= 4 and "60" not in body
    await r.check("c07_content_editing", deletion)

    async def amount_validation():
        await reset_page(page); await _add_people(page)
        await fill_any_named(page, ["花在什么上", "用途", "说明"], "错误款项")
        await fill_any_named(page, ["金额（元）", "金额"], "")
        await click_named_any(page, ["记一笔", "添加款项"])
        empty = await contains_texts(page, ["金额", "不能空"])
        await fill_any_named(page, ["金额（元）", "金额"], "-1")
        await click_named_any(page, ["记一笔", "添加款项"])
        body = await page.locator("body").inner_text()
        return empty and "大于 0" in body and "错误款项" not in body
    await r.check("c08_form_validation", amount_validation)

    async def sharer_validation():
        await reset_page(page); await _add_people(page)
        await _set_payer(page, "阿明")
        await fill_any_named(page, ["花在什么上", "用途", "说明"], "无人分摊")
        await fill_any_named(page, ["金额（元）", "金额"], "100")
        await _set_sharers(page, [])
        await click_named_any(page, ["记一笔", "添加款项"])
        body = await page.locator("body").inner_text()
        return "至少" in body and "一个人" in body and "无人分摊" not in body
    await r.check("c09_form_validation", sharer_validation)

    async def all_amounts_reconcile():
        await _seed(page)
        body = await page.locator("body").inner_text()
        return (
            await contains_texts(page, [
                "1260", "阿明", "应摊 300", "小林", "应摊 300",
                "阿德", "应摊 330", "晓晓", "应摊 330", "240", "330",
            ])
            and not any(value in body for value in ["NaN", "Infinity", "undefined"])
        )
    await r.check("c12_rule_settlement", all_amounts_reconcile)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900}); await _seed(page)
    shots = [await capture(page, screenshot_dir, "desktop-aa-split", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-aa-split", full_page=True))
    return shots
