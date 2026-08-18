from __future__ import annotations

try:
    from ..common import (
        CheckRecorder, capture, click_named, click_named_any, contains_any_texts,
        contains_texts, fill_any_named,
        fill_named, reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, click_named_any, contains_any_texts,
        contains_texts, fill_any_named,
        fill_named, reset_page,
    )


RUNTIME_KEYS = [
    "criterion_01_basic_content", "criterion_02_lists_and_tables",
    "criterion_03_content_creation_and_editing", "criterion_04_form_filling_and_validation",
    "criterion_05_form_filling_and_validation", "criterion_06_content_switching",
    "criterion_07_content_creation_and_editing", "criterion_08_form_filling_and_validation",
    "criterion_09_information_organization", "criterion_10_content_creation_and_editing",
    "criterion_11_content_creation_and_editing", "criterion_12_content_creation_and_editing",
    "criterion_13_content_switching", "criterion_14_content_creation_and_editing",
    "criterion_15_state_persistence", "criterion_16_content_creation_and_editing",
    "criterion_17_content_switching", "criterion_18_file_upload_and_download",
    "criterion_19_state_persistence",
]
VISUAL_KEYS = ["criterion_20_page_layout"]


async def _select_value(page, value: str) -> bool:
    selects = page.locator("select")
    for index in range(await selects.count()):
        options = await selects.nth(index).locator("option").all_text_contents()
        if value in options:
            await selects.nth(index).select_option(label=value)
            return True
    return False


async def _fill_date_inputs(page, start: str, end: str) -> bool:
    dates = page.locator('input[type="date"]')
    if await dates.count() < 2:
        return False
    await dates.nth(0).fill(start)
    await dates.nth(1).fill(end)
    return True


async def _create_trip(page, *, start: str = "2026-10-03", end: str = "2026-10-05") -> bool:
    await reset_page(page)
    city_ok = await _select_value(page, "成都市")
    date_ok = await _fill_date_inputs(page, start, end)
    if not city_ok:
        try:
            await fill_any_named(page, ["目的地城市", "选择目的地", "城市"], "成都市")
            city_ok = True
        except Exception:
            pass
    if city_ok and date_ok:
        try:
            await click_named_any(page, ["进入规划", "创建行程"])
        except Exception:
            return False
    return city_ok and date_ok


async def _select_day(page, day_number: int, date: str) -> bool:
    labels = [f"第 {day_number} 天", f"第{day_number}天", date]
    try:
        await click_named_any(page, labels)
        return True
    except AssertionError:
        return False


async def _add_destination(page, name: str, kind: str = "景点", time: str = "09:30", note: str = "上午拍照") -> None:
    await fill_any_named(page, ["目的地名称", "输入目的地", "目的地", "名称"], name)
    await _select_value(page, kind)
    times = page.locator('input[type="time"]')
    if await times.count():
        await times.last.fill(time)
    else:
        try:
            await fill_any_named(page, ["时间", "安排时间"], time)
        except Exception:
            pass
    try:
        await fill_any_named(page, ["备注", "补充说明"], note)
    except Exception:
        pass
    await click_named(page, "添加到当天")


async def _open_home(page) -> None:
    for label in ("返回首页", "首页"):
        try:
            await click_named(page, label)
            return
        except Exception:
            continue


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def basic_content():
        await reset_page(page)
        return (
            await contains_texts(page, ["行迹 Planner", "目的地", "开始日期", "结束日期"])
            and await contains_any_texts(page, ["旅行", "行程"])
            and await contains_any_texts(page, ["进入规划", "创建行程"])
        )
    await recorder.check("criterion_01_basic_content", basic_content)

    async def history_empty():
        await reset_page(page)
        return await contains_texts(page, ["历史行程"]) and await contains_any_texts(
            page, ["还没有保存的行程", "还没有保存过行程", "暂无保存的行程", "暂无行程"]
        )
    await recorder.check("criterion_02_lists_and_tables", history_empty)

    async def enter_planner():
        ok = await _create_trip(page)
        return ok and await contains_texts(page, ["成都市", "2026-10-03", "2026-10-05", "保存", "导出"])
    await recorder.check("criterion_03_content_creation_and_editing", enter_planner)

    async def missing_city():
        await reset_page(page)
        selects = page.locator("select")
        if await selects.count():
            await selects.first.select_option(index=0)
        await click_named_any(page, ["进入规划", "创建行程"])
        return await contains_texts(page, ["选择目的地城市"]) and not await page.get_by_text("行程规划", exact=True).count()
    await recorder.check("criterion_04_form_filling_and_validation", missing_city)

    async def invalid_date():
        await reset_page(page)
        city_ok = await _select_value(page, "成都市")
        if not city_ok:
            try:
                await fill_any_named(page, ["目的地城市", "选择目的地", "城市"], "成都市")
                city_ok = True
            except AssertionError:
                pass
        await _fill_date_inputs(page, "2026-10-05", "2026-10-03")
        await click_named_any(page, ["进入规划", "创建行程"])
        return city_ok and await contains_texts(page, ["结束日期不能早于开始日期"])
    await recorder.check("criterion_05_form_filling_and_validation", invalid_date)

    async def day_switch():
        ok = await _create_trip(page)
        dates = await contains_texts(page, ["2026-10-03", "2026-10-04", "2026-10-05"])
        empty = await contains_texts(page, ["这一天还没有目的地"])
        return ok and dates and empty
    await recorder.check("criterion_06_content_switching", day_switch)

    async def add_card():
        if not await _create_trip(page):
            return False
        await _add_destination(page, "宽窄巷子")
        return (
            await contains_texts(page, ["1", "宽窄巷子", "景点", "09:30", "上午拍照"])
            and not await contains_any_texts(page, ["这一天还没有目的地", "暂无目的地"])
        )
    await recorder.check("criterion_07_content_creation_and_editing", add_card)

    async def empty_destination():
        if not await _create_trip(page):
            return False
        await click_named(page, "添加到当天")
        return await contains_texts(page, ["请输入目的地名称"])
    await recorder.check("criterion_08_form_filling_and_validation", empty_destination)

    async def destination_types():
        if not await _create_trip(page):
            return False
        for value in ["住宿", "交通", "景点", "吃饭", "购物", "其他"]:
            if not await _select_value(page, value):
                return False
        return True
    await recorder.check("criterion_09_information_organization", destination_types)

    async def reorder():
        if not await _create_trip(page):
            return False
        await _add_destination(page, "宽窄巷子")
        await _add_destination(page, "酒店入住", "住宿", "18:00", "办理入住")
        first = page.get_by_text("酒店入住", exact=True).last
        second = page.get_by_text("宽窄巷子", exact=True).last
        try:
            await first.drag_to(second)
        except Exception:
            return False
        return await contains_texts(page, ["酒店入住", "宽窄巷子"])
    await recorder.check("criterion_10_content_creation_and_editing", reorder)

    async def edit_destination():
        if not await _create_trip(page):
            return False
        await _add_destination(page, "宽窄巷子")
        try:
            await page.get_by_text("宽窄巷子", exact=True).last.click()
            await click_named(page, "编辑")
            await fill_any_named(page, ["目的地名称", "目的地", "名称"], "人民公园")
            await _select_value(page, "吃饭")
            times = page.locator('input[type="time"]')
            if await times.count():
                await times.last.fill("12:00")
            await fill_any_named(page, ["备注", "补充说明"], "午饭后散步")
            await click_named(page, "保存")
        except Exception:
            return False
        return await contains_texts(page, ["人民公园", "吃饭", "12:00", "午饭后散步"])
    await recorder.check("criterion_11_content_creation_and_editing", edit_destination)

    async def delete_destination():
        if not await _create_trip(page):
            return False
        await _add_destination(page, "宽窄巷子")
        await _add_destination(page, "酒店入住", "住宿", "18:00", "办理入住")
        try:
            await page.get_by_text("宽窄巷子", exact=True).last.click()
            await click_named(page, "删除")
            for label in ("确认删除", "确定"):
                try:
                    await click_named(page, label)
                    break
                except Exception:
                    continue
        except Exception:
            return False
        return await page.get_by_text("宽窄巷子", exact=True).count() == 0 and await contains_texts(page, ["酒店入住"])
    await recorder.check("criterion_12_content_creation_and_editing", delete_destination)

    async def date_isolation():
        if not await _create_trip(page):
            return False
        await _add_destination(page, "第一天安排")
        if not await _select_day(page, 2, "2026-10-04"):
            return False
        await _add_destination(page, "春熙路")
        second_day_only = (
            await contains_texts(page, ["春熙路"])
            and not await page.get_by_text("第一天安排", exact=True).count()
        )
        if not await _select_day(page, 1, "2026-10-03"):
            return False
        return second_day_only and await contains_texts(page, ["第一天安排"]) and not await page.get_by_text("春熙路", exact=True).count()
    await recorder.check("criterion_13_content_switching", date_isolation)

    async def save_feedback():
        if not await _create_trip(page):
            return False
        try:
            await fill_any_named(page, ["行程名称", "行程名"], "成都亲子慢游")
            await click_named(page, "保存行程")
        except Exception:
            return False
        return await contains_texts(page, ["成都亲子慢游"]) and await contains_texts(page, ["保存成功", "已保存"])
    await recorder.check("criterion_14_content_creation_and_editing", save_feedback)

    async def history_record():
        if not await _create_trip(page):
            return False
        try:
            await fill_any_named(page, ["行程名称", "行程名"], "成都亲子慢游")
            await click_named(page, "保存行程")
            await _open_home(page)
        except Exception:
            return False
        return await contains_texts(page, ["成都亲子慢游", "成都市", "2026-10-03", "2026-10-05"])
    await recorder.check("criterion_15_state_persistence", history_record)

    async def update_existing():
        if not await _create_trip(page):
            return False
        await fill_any_named(page, ["行程名称", "行程名"], "成都亲子慢游")
        await click_named(page, "保存行程")
        await _open_home(page)
        try:
            await click_named(page, "继续编辑")
            await fill_any_named(page, ["行程名称", "行程名"], "成都亲子慢游")
            await click_named(page, "保存行程")
            await _open_home(page)
        except Exception:
            return False
        return await page.get_by_text("成都亲子慢游", exact=True).count() == 1
    await recorder.check("criterion_16_content_creation_and_editing", update_existing)

    async def extend_dates():
        if not await _create_trip(page):
            return False
        dates = page.locator('input[type="date"]')
        if await dates.count() < 2:
            return False
        await dates.nth(1).fill("2026-10-06")
        await page.keyboard.press("Tab")
        added = await contains_texts(page, ["2026-10-06"])
        await dates.nth(1).fill("2026-10-04")
        await page.keyboard.press("Tab")
        return added and await contains_texts(page, ["2026-10-03", "2026-10-04"]) and not await page.get_by_text("2026-10-05", exact=True).count()
    await recorder.check("criterion_17_content_switching", extend_dates)

    async def export_preview():
        if not await _create_trip(page):
            return False
        await _add_destination(page, "宽窄巷子")
        try:
            await click_named(page, "导出行程图")
        except Exception:
            return False
        return await contains_texts(page, ["行程图", "成都市", "下载"])
    await recorder.check("criterion_18_file_upload_and_download", export_preview)

    async def persistence():
        if not await _create_trip(page):
            return False
        await fill_any_named(page, ["行程名称", "行程名"], "成都亲子慢游")
        await _add_destination(page, "宽窄巷子")
        try:
            await click_named(page, "保存行程")
            await page.reload(wait_until="domcontentloaded")
            await _open_home(page)
        except Exception:
            return False
        return await contains_texts(page, ["成都亲子慢游", "宽窄巷子"])
    await recorder.check("criterion_19_state_persistence", persistence)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-home")]
    if await _create_trip(page):
        manifest.append(await capture(page, screenshot_dir, "desktop-planner", full_page=False))
    return manifest
