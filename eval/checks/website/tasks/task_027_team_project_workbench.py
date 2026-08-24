from __future__ import annotations

from datetime import date, timedelta

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, fill_any_named, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_content_switching", "c03_content_editing", "c04_content_editing",
    "c05_content_editing", "c06_rule_settlement", "c07_rule_settlement", "c08_cross_region_linkage",
    "c09_rule_settlement", "c10_cross_region_linkage", "c11_rule_settlement", "c12_search_filtering",
    "c13_popup_overlay", "c14_state_persistence", "c15_data_visualization", "c16_lists_tables",
    "c17_detail_display", "c21_rule_settlement",
]
VISUAL_KEYS = ["c18_visual_style", "c19_page_layout", "c20_responsive_layout"]


async def _fresh(page):
    await reset_page(page)


async def _save(page, names=("保存", "创建", "确定", "提交")):
    await click_named_any(page, list(names))
    await page.wait_for_timeout(80)


async def _select_option(page, text):
    selects = page.locator("select")
    for i in range(await selects.count()):
        opts = await selects.nth(i).locator("option").all_text_contents()
        match = next((o for o in opts if text in o), None)
        if match:
            await selects.nth(i).select_option(label=match)
            return True
    try:
        await click_named_any(page, [text, f"选择{text}"])
        return True
    except Exception:
        return False


async def _create_project(page, name):
    await click_named_any(page, ["项目", "项目管理"])
    await click_named_any(page, ["新建项目", "新增项目", "创建项目"])
    await fill_any_named(page, ["项目名称", "项目名", "名称"], name)
    await _save(page)
    return await contains_texts(page, [name])


async def _create_requirement(page, title):
    await click_named_any(page, ["需求", "需求管理"])
    await click_named_any(page, ["新建需求", "新增需求", "创建需求"])
    await fill_any_named(page, ["需求标题", "需求名称", "标题"], title)
    await _select_option(page, "客服系统重构")
    await _save(page)
    return await contains_texts(page, [title, "客服系统重构"])


async def _create_task(page, title, owner, due):
    await click_named_any(page, ["任务", "任务看板", "看板"])
    await click_named_any(page, ["新建任务", "新增任务", "创建任务"])
    await fill_any_named(page, ["任务标题", "任务名称", "标题"], title)
    await _select_option(page, "工单列表改版")
    if not await _select_option(page, owner):
        try:
            await fill_any_named(page, ["负责人", "责任人"], owner)
        except Exception:
            pass
    await fill_any_named(page, ["截止日期", "截止时间", "日期"], due)
    await _save(page)
    return await contains_texts(page, [title, owner])


async def _seed(page, *, two_tasks=True):
    await _fresh(page)
    if not await _create_project(page, "客服系统重构"):
        return False
    if not await _create_requirement(page, "工单列表改版"):
        return False
    due = (date.today() + timedelta(days=30)).isoformat()
    if not await _create_task(page, "梳理工单字段", "林薇", due):
        return False
    if two_tasks and not await _create_task(page, "联调工单接口", "周越", due):
        return False
    return True


async def _drag(page, title, status):
    card = page.get_by_text(title, exact=True)
    target_text = page.get_by_text(status, exact=True)
    if not await card.count() or not await target_text.count():
        return False
    source = card.first.locator("xpath=ancestor-or-self::*[@draggable='true'][1]")
    if not await source.count():
        source = card.first.locator("xpath=ancestor::*[contains(@class,'card')][1]")
    target = target_text.first.locator("xpath=ancestor-or-self::*[contains(@class,'column') or contains(@class,'lane')][1]")
    if not await target.count():
        target = target_text.first
    await source.drag_to(target)
    await page.wait_for_timeout(120)
    return await contains_texts(target, [title])


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def empty_dashboard():
        await _fresh(page)
        body = await page.locator("body").inner_text()
        return await contains_texts(page, ["工作台", "项目", "需求", "任务"]) and await contains_any_texts(page, ["新建项目", "还没有", "暂无", "0"]) and not any(x in body for x in ["NaN", "Infinity", "undefined", "null"])
    await recorder.check("c01_information_organization", empty_dashboard)

    async def switching():
        await _fresh(page)
        for label in ("项目", "需求", "任务", "工作台"):
            await click_named_any(page, [label])
            heading = page.get_by_role("heading", name=label, exact=True)
            if not await heading.count():
                return False
        return True
    await recorder.check("c02_content_switching", switching)

    async def project():
        await _fresh(page)
        ok = await _create_project(page, "客服系统重构")
        await click_named_any(page, ["工作台"])
        return ok and await contains_texts(page, ["客服系统重构"])
    await recorder.check("c03_content_editing", project)

    async def requirement():
        await _fresh(page)
        return await _create_project(page, "客服系统重构") and await _create_requirement(page, "工单列表改版")
    await recorder.check("c04_content_editing", requirement)

    async def task():
        await _fresh(page)
        await _create_project(page, "客服系统重构")
        await _create_requirement(page, "工单列表改版")
        return await _create_task(page, "梳理工单字段", "林薇", (date.today() + timedelta(days=30)).isoformat()) and await contains_texts(page, ["待开始"])
    await recorder.check("c05_content_editing", task)

    async def half_done():
        if not await _seed(page):
            return False
        if not await _drag(page, "梳理工单字段", "已完成"):
            return False
        await click_named_any(page, ["需求"])
        return await contains_texts(page, ["工单列表改版"]) and await contains_any_texts(page, ["50%", "1/2", "1 / 2"])
    await recorder.check("c06_rule_settlement", half_done)

    async def all_done():
        if not await _seed(page):
            return False
        await _drag(page, "梳理工单字段", "已完成")
        await _drag(page, "联调工单接口", "已完成")
        await click_named_any(page, ["需求"])
        return await contains_texts(page, ["工单列表改版", "已完成"]) and await contains_any_texts(page, ["100%", "2/2", "2 / 2"])
    await recorder.check("c07_rule_settlement", all_done)

    async def status_chart():
        if not await _seed(page):
            return False
        await _drag(page, "梳理工单字段", "进行中")
        await click_named_any(page, ["工作台"])
        return await contains_texts(page, ["任务状态分布", "待开始", "进行中"]) and await contains_any_texts(page, ["1 个", "1个", "1"])
    await recorder.check("c08_cross_region_linkage", status_chart)

    async def overdue():
        if not await _seed(page, two_tasks=False):
            return False
        await _create_task(page, "导出历史工单", "周越", "2025-11-28")
        await click_named_any(page, ["工作台"])
        return await contains_texts(page, ["导出历史工单", "周越", "工单列表改版"]) and await contains_any_texts(page, ["逾期", "已过期"])
    await recorder.check("c09_rule_settlement", overdue)

    async def reminder_link():
        if not await overdue():
            return False
        before = page.url
        await click_named_any(page, ["导出历史工单"])
        card = page.get_by_text("导出历史工单", exact=True)
        return bool(await card.count() and await card.first.is_visible() and (page.url != before or await card.first.evaluate("e => !!e.closest('[role=dialog], .highlight, .card, .task-card')")))
    await recorder.check("c10_cross_region_linkage", reminder_link)

    async def due_window():
        if not await _seed(page, two_tasks=False):
            return False
        await _create_task(page, "补充埋点", "林薇", (date.today() + timedelta(days=1)).isoformat())
        await _create_task(page, "季度复盘", "周越", (date.today() + timedelta(days=90)).isoformat())
        await click_named_any(page, ["工作台"])
        text = await page.locator("body").inner_text()
        reminder = page.get_by_text("一周内要交", exact=False).locator("xpath=ancestor::*[self::section or self::div][1]")
        return "补充埋点" in text and (not await reminder.count() or "季度复盘" not in await reminder.first.inner_text())
    await recorder.check("c11_rule_settlement", due_window)

    async def filtering():
        if not await _seed(page):
            return False
        if not await _select_option(page, "林薇"):
            return False
        body = await page.locator("body").inner_text()
        filtered = "梳理工单字段" in body and "联调工单接口" not in body
        selects = page.locator("select")
        for i in range(await selects.count()):
            try:
                await selects.nth(i).select_option(index=0)
            except Exception:
                pass
        await page.wait_for_timeout(80)
        return filtered and await contains_texts(page, ["梳理工单字段", "联调工单接口"])
    await recorder.check("c12_search_filtering", filtering)

    async def delete_confirm():
        if not await _seed(page):
            return False
        await click_named_any(page, ["需求"])
        row = page.get_by_text("工单列表改版", exact=True).locator("xpath=ancestor::*[self::li or self::tr or contains(@class,'card')][1]")
        delete = row.get_by_role("button", name="删除", exact=False)
        if not await delete.count():
            return False
        await delete.first.click()
        dialog = page.locator("[role='dialog'], dialog, .modal, .overlay")
        opened = bool(await dialog.count() and await dialog.first.is_visible())
        await click_named_any(page, ["取消", "暂不删除"])
        stayed = await contains_texts(page, ["工单列表改版"])
        await delete.first.click()
        await click_named_any(page, ["确认删除", "删除", "确定"])
        return opened and stayed and not await contains_texts(page, ["工单列表改版"])
    await recorder.check("c13_popup_overlay", delete_confirm)

    async def persistence():
        if not await _seed(page, two_tasks=False):
            return False
        await _drag(page, "梳理工单字段", "进行中")
        await page.reload(wait_until="domcontentloaded")
        return await contains_texts(page, ["梳理工单字段", "林薇", "进行中"])
    await recorder.check("c14_state_persistence", persistence)

    async def owner_chart():
        if not await _seed(page):
            return False
        await click_named_any(page, ["工作台"])
        return await contains_texts(page, ["每人未完成任务", "林薇", "周越"]) and await page.locator("svg, canvas, .bar, [role='img']").count() > 0
    await recorder.check("c15_data_visualization", owner_chart)

    async def empty_projects():
        await _fresh(page)
        await _create_project(page, "客服系统重构")
        await _create_project(page, "数据看板升级")
        body = await page.locator("body").inner_text()
        return all(x in body for x in ["客服系统重构", "数据看板升级"]) and not any(x in body for x in ["NaN", "Infinity", "undefined", "null", "100%"])
    await recorder.check("c16_lists_tables", empty_projects)

    async def detail():
        if not await _seed(page):
            return False
        await click_named_any(page, ["需求"])
        await click_named_any(page, ["工单列表改版"])
        return await contains_texts(page, ["客服系统重构", "梳理工单字段", "联调工单接口"])
    await recorder.check("c17_detail_display", detail)

    async def dashboard_numbers_reconcile():
        if not await _seed(page):
            return False
        await _create_task(page, "逾期回归测试", "周越", "2025-11-28")
        await _drag(page, "梳理工单字段", "已完成")
        await _drag(page, "联调工单接口", "进行中")
        await click_named_any(page, ["工作台"])
        dashboard_body = await page.locator("body").inner_text()
        dashboard_ok = (
            await contains_texts(page, ["客服系统重构", "工单列表改版"])
            and await contains_any_texts(page, ["逾期 1", "逾期1", "1 个逾期", "逾期任务"])
            and not any(value in dashboard_body for value in ["NaN", "Infinity", "undefined"])
        )
        await click_named_any(page, ["需求", "需求管理"])
        await click_named_any(page, ["工单列表改版"])
        detail_ok = (
            await contains_texts(page, ["梳理工单字段", "联调工单接口", "逾期回归测试"])
            and await contains_any_texts(page, ["1/3", "1 / 3", "33%", "33.3%"])
        )
        return dashboard_ok and detail_ok
    await recorder.check("c21_rule_settlement", dashboard_numbers_reconcile)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await _fresh(page)
    shots = [await capture(page, screenshot_dir, "empty-dashboard", full_page=False)]
    try:
        await _seed(page)
        shots.append(await capture(page, screenshot_dir, "desktop-board"))
    except Exception:
        pass
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-board"))
    return shots
