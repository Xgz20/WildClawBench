from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_lists_tables", "c03_form_validation",
    "c04_content_editing", "c05_rule_settlement", "c06_rule_settlement",
    "c07_rule_settlement", "c08_rule_settlement", "c09_rule_settlement",
    "c10_rule_settlement", "c11_rule_settlement", "c12_rule_settlement",
    "c13_rule_settlement", "c14_popup_overlay", "c15_state_persistence",
    "c19_form_validation",
]
VISUAL_KEYS = ["c16_page_layout", "c17_visual_style", "c18_responsive_layout"]


async def _fill_trip(page, city="上海", grade="普通员工", depart="2026-03-09T09:30", back="2026-03-11T15:00"):
    await fill_any_named(page, ["目的地城市", "目的地"], city)
    selects = page.locator("select")
    for i in range(await selects.count()):
        options = await selects.nth(i).locator("option").all_text_contents()
        if grade in options:
            await selects.nth(i).select_option(label=grade)
            break
    fields = page.locator('input[type="datetime-local"]')
    if await fields.count() < 2:
        raise AssertionError("出发和返程时间输入框不完整")
    await fields.nth(0).fill(depart)
    await fields.nth(1).fill(back)
    await fields.nth(1).press("Tab")


async def _add(page, kind, date, note, amount, mode=None):
    selects = page.locator("select")
    for i in range(await selects.count()):
        options = await selects.nth(i).locator("option").all_text_contents()
        if any(kind in option for option in options):
            await selects.nth(i).select_option(label=next(option for option in options if kind in option))
            break
    if mode:
        for i in range(await selects.count()):
            options = await selects.nth(i).locator("option").all_text_contents()
            if any(mode in option for option in options):
                await selects.nth(i).select_option(label=next(option for option in options if mode in option))
                break
    await page.locator('input[type="date"]').last.fill(date)
    await fill_any_named(page, ["说明", "用途", "备注"], note)
    await fill_any_named(page, ["金额（元）", "金额", "申报金额"], str(amount))
    await click_named_any(page, ["添加明细", "添加票据", "记一笔"])


async def _seed_two(page):
    await reset_page(page)
    await _fill_trip(page)
    await _add(page, "住宿", "2026-03-09", "酒店住宿", 720)
    await _add(page, "交通", "2026-03-09", "高铁往返", 553)


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def initial():
        await reset_page(page)
        return await contains_texts(page, ["差旅核算助手", "目的地城市", "出差人职级", "出发时间", "返程时间", "添加明细", "本次汇总", "还没有"])
    await r.check("c01_information_organization", initial)

    async def two_rows():
        await _seed_two(page)
        return await contains_texts(page, ["住宿", "2026-03-09", "酒店住宿", "720", "可报", "600", "超标", "120", "高铁往返", "553"])
    await r.check("c02_lists_tables", two_rows)

    async def trip_validation():
        await reset_page(page)
        await page.locator('input[type="datetime-local"]').first.focus()
        await page.locator("body").click(position={"x": 1, "y": 1})
        empty = await contains_texts(page, ["请填写目的地", "请填写出发时间", "请填写返程时间"])
        await _fill_trip(page, back="2026-03-09T09:30", depart="2026-03-11T15:00")
        invalid = await contains_texts(page, ["返程时间不能早于出发时间"])
        return empty and invalid
    await r.check("c03_form_validation", trip_validation)

    async def add_hotel():
        await reset_page(page)
        await _fill_trip(page)
        await _add(page, "住宿", "2026-03-10", "酒店住宿", 550)
        return await contains_texts(page, ["2026-03-10", "酒店住宿", "550", "可报", "超标", "0"])
    await r.check("c04_content_editing", add_hotel)

    async def full_days():
        await reset_page(page)
        await _fill_trip(page)
        return await contains_texts(page, ["3 天", "450", "600", "一类城市"])
    await r.check("c05_rule_settlement", full_days)

    async def half_days():
        await reset_page(page)
        await _fill_trip(page, depart="2026-03-09T14:00")
        return await contains_texts(page, ["2.5 天", "375"])
    await r.check("c06_rule_settlement", half_days)

    async def same_day():
        await reset_page(page)
        await _fill_trip(page, depart="2026-03-09T08:00", back="2026-03-09T21:00")
        return await contains_texts(page, ["1 天", "150"])
    await r.check("c07_rule_settlement", same_day)

    async def hotel_caps():
        await reset_page(page)
        await _fill_trip(page)
        await _add(page, "住宿", "2026-03-09", "酒店一", 720)
        await _add(page, "住宿", "2026-03-10", "酒店二", 550)
        return await contains_texts(page, ["720", "600", "120", "550", "1150"])
    await r.check("c08_rule_settlement", hotel_caps)

    async def voucher():
        await reset_page(page)
        await _fill_trip(page)
        await _add(page, "交通", "2026-03-10", "出租车", 128, "出租车")
        before = await contains_texts(page, ["支付凭证", "可报", "0"])
        await page.get_by_role("checkbox", name="已附支付凭证", exact=False).check()
        return before and await contains_texts(page, ["可报", "128"])
    await r.check("c09_rule_settlement", voucher)

    async def personal():
        await reset_page(page)
        await _fill_trip(page)
        await _add(page, "交通", "2026-03-11", "出租车", 45, "出租车")
        await page.get_by_role("checkbox", name="个人事项", exact=False).check()
        return await contains_texts(page, ["个人事项", "45", "可报", "0"])
    await r.check("c10_rule_settlement", personal)

    async def totals():
        await reset_page(page)
        await _fill_trip(page)
        for args in [("住宿", "2026-03-09", "酒店一", 720, None), ("住宿", "2026-03-10", "酒店二", 550, None), ("交通", "2026-03-09", "高铁往返", 553, None), ("交通", "2026-03-10", "出租车一", 128, "出租车"), ("交通", "2026-03-11", "出租车二", 45, "出租车")]:
            await _add(page, *args)
        boxes = page.get_by_role("checkbox", name="已附支付凭证", exact=False)
        if await boxes.count(): await boxes.first.check()
        return await contains_texts(page, ["申报合计", "1996", "不可报合计", "120", "实际可报", "2326"])
    await r.check("c11_rule_settlement", totals)

    async def manager():
        await reset_page(page); await _fill_trip(page)
        await _add(page, "住宿", "2026-03-09", "酒店一", 720)
        await _add(page, "住宿", "2026-03-10", "酒店二", 550)
        await _fill_trip(page, grade="管理岗")
        return await contains_texts(page, ["800", "申报合计", "1270", "不可报合计", "0", "实际可报", "1720"])
    await r.check("c12_rule_settlement", manager)

    async def hefei():
        await reset_page(page); await _fill_trip(page)
        await _add(page, "住宿", "2026-03-09", "酒店一", 720)
        await _add(page, "住宿", "2026-03-10", "酒店二", 550)
        await fill_any_named(page, ["目的地城市", "目的地"], "合肥")
        return await contains_texts(page, ["350", "370", "200", "不可报合计", "570", "实际可报", "1150"])
    await r.check("c13_rule_settlement", hefei)

    async def deletion():
        await _seed_two(page)
        row = page.locator("li, tr, article, [class*='item']").filter(has_text="高铁往返").first
        await row.get_by_role("button", name="删除", exact=False).click()
        dialog = page.get_by_role("dialog")
        opened = await dialog.is_visible()
        await click_named_any(page, ["取消"])
        kept = await contains_texts(page, ["高铁往返"])
        await row.get_by_role("button", name="删除", exact=False).click()
        await click_named_any(page, ["确认删除", "确认"])
        return opened and kept and not await page.get_by_text("高铁往返", exact=True).count()
    await r.check("c14_popup_overlay", deletion)

    async def persistence():
        await _seed_two(page)
        await page.reload(wait_until="domcontentloaded")
        return await contains_texts(page, ["上海", "酒店住宿", "720", "高铁往返", "553", "本次汇总"])
    await r.check("c15_state_persistence", persistence)

    async def entry_validation():
        await reset_page(page)
        await click_named_any(page, ["添加明细", "添加票据", "记一笔"])
        missing_date = await contains_texts(page, ["请填写日期"])
        await page.locator('input[type="date"]').last.fill("2026-03-09")
        await fill_any_named(page, ["金额（元）", "金额"], "88")
        await click_named_any(page, ["添加明细", "添加票据", "记一笔"])
        missing_note = await contains_texts(page, ["请填写说明"])
        await fill_any_named(page, ["说明", "备注"], "酒店住宿")
        await fill_any_named(page, ["金额（元）", "金额"], "0")
        await click_named_any(page, ["添加明细", "添加票据", "记一笔"])
        return missing_date and missing_note and await contains_texts(page, ["金额必须大于 0", "还没有"])
    await r.check("c19_form_validation", entry_validation)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await _seed_two(page)
    shots = [await capture(page, screenshot_dir, "desktop-travel-expenses", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-travel-expenses", full_page=True))
    return shots
