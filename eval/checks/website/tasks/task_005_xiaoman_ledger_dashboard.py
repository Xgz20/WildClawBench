from __future__ import annotations

try:
    from ..common import (
        CheckRecorder, ancestor_contains_texts, capture, click_named, contains_texts,
        element_contains_texts, fill_any_named, fill_named, reset_page,
        visualization_contains_texts,
    )
except ImportError:
    from common import (
        CheckRecorder, ancestor_contains_texts, capture, click_named, contains_texts,
        element_contains_texts, fill_any_named, fill_named, reset_page,
        visualization_contains_texts,
    )


RUNTIME_KEYS = [
    "c01_information_organization", "c02_form_validation", "c03_content_editing",
    "c04_content_switching", "c05_content_switching", "c06_search_filtering",
    "c07_search_filtering", "c08_detail_display", "c09_content_editing",
    "c10_popup_overlay", "c11_data_visualization", "c12_content_switching",
    "c13_state_persistence",
]
VISUAL_KEYS = ["c14_page_layout", "c15_responsive_layout"]


async def _select_by_options(
    page, labels: list[str], value: str, *, prefer_last: bool = False
) -> bool:
    selects = page.locator("select")
    indexes = list(range(await selects.count()))
    if prefer_last:
        indexes.reverse()
    for index in indexes:
        options = await selects.nth(index).locator("option").all_text_contents()
        if all(label in options for label in labels):
            await selects.nth(index).select_option(label=value)
            return True
    return False


async def _set_period(page, label: str) -> bool:
    return await _select_by_options(page, ["2026年6月", "2026年7月", "2026年8月"], label)


async def _reset_records(page):
    await reset_page(page)


async def _open_record(page, name: str):
    await page.get_by_text(name, exact=True).first.click()


async def _open_add(page):
    await click_named(page, "记一笔")


async def _fill_record_modal(page, name: str, amount: str, category: str, date: str, note: str):
    await fill_any_named(page, ["输入名称", "如：超市采购", "名称"], name)
    await fill_any_named(page, ["输入金额", "0.00", "金额"], amount)
    await _select_by_options(
        page, ["餐饮", "交通", "居住", "学习"], category, prefer_last=True
    )
    dates = page.locator('input[type="date"]')
    if await dates.count():
        await dates.last.fill(date)
    await fill_any_named(page, ["输入备注（选填）", "输入备注", "可选", "备注"], note)


async def _save_record(page):
    await click_named(page, "保存记录")


async def _close_detail(page):
    for name in ("关闭", "×", "✕", "X"):
        button = page.get_by_role("button", name=name, exact=True)
        if await button.count():
            await button.first.click()
            return
    raise AssertionError("required detail close control not found")


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def header():
        await _reset_records(page)
        return await contains_texts(page, [
            "小满账簿", "把每一笔认真记下，也把生活慢慢看清。", "记一笔", "按月", "2026年8月",
            "明细", "8月明细",
        ])
    await recorder.check("c01_information_organization", header)

    async def august_list():
        await _reset_records(page)
        return await contains_texts(page, [
            "收入", "¥11,000.00", "支出", "¥3,044.00", "结余", "¥7,956.00", "记录数", "6 笔",
            "咖啡豆", "地铁充值", "项目奖金", "房租", "超市采购", "工资", "当前结果 6 条",
        ])

    async def july_switch():
        await _reset_records(page)
        if not await _set_period(page, "2026年7月"):
            return False
        return await contains_texts(page, ["7月明细", "¥10,700.00", "¥3,402.00", "¥7,298.00", "6 笔", "旅行交通", "朋友聚餐", "电影票"])
    await recorder.check("c04_content_switching", july_switch)

    async def weekly_switch():
        await _reset_records(page)
        await click_named(page, "按周")
        return await contains_texts(page, ["2026年8月第2周（8/3-8/9）", "8月第2周明细", "¥1,200.00", "¥2,976.00", "-¥1,776.00", "4 笔", "地铁充值", "项目奖金", "房租", "超市采购"])
    await recorder.check("c05_content_switching", weekly_switch)

    async def search():
        await _reset_records(page)
        await fill_named(page, "搜索名称或备注", "手冲")
        return await contains_texts(page, ["当前结果 1 条", "咖啡豆", "给家里补一袋手冲豆"]) and await page.get_by_text("地铁充值", exact=True).count() == 0
    await recorder.check("c06_search_filtering", search)

    async def filters():
        await _reset_records(page)
        if not await _select_by_options(page, ["全部", "支出", "收入"], "支出"):
            await click_named(page, "支出")
        if not await _select_by_options(page, ["全部分类", "餐饮", "交通", "居住"], "餐饮"):
            return False
        if not await _select_by_options(page, ["最新优先", "金额从高到低"], "金额从高到低"):
            return False
        text = await page.locator("body").inner_text()
        return await contains_texts(page, ["当前结果 2 条", "超市采购", "咖啡豆"]) and text.find("超市采购") < text.find("咖啡豆")
    await recorder.check("c07_search_filtering", filters)

    async def drawer():
        await _reset_records(page)
        await _open_record(page, "地铁充值")
        return await contains_texts(page, ["记录详情", "地铁充值", "-¥50.00", "支出", "交通", "2026-08-09", "交通卡自动充值", "编辑记录", "删除记录"])
    await recorder.check("c08_detail_display", drawer)

    async def tabs():
        await _reset_records(page)
        await click_named(page, "分析")
        analysis = await contains_texts(
            page, ["收支概览", "收入分类", "支出分类", "趋势", "收入 Top3", "支出 Top3"]
        )
        await click_named(page, "明细")
        detail = (
            await page.get_by_placeholder("搜索名称或备注", exact=False).is_visible()
            and await contains_texts(page, ["当前结果 6 条", "咖啡豆"])
        )
        return analysis and detail

    async def analysis_overview():
        await _reset_records(page)
        await click_named(page, "分析")
        overview = await contains_texts(
            page, ["2026年8月", "¥11,000.00", "¥3,044.00", "¥7,956.00", "6 笔"]
        )
        maximum = await element_contains_texts(
            page, "最大支出分类", ["居住", "¥2,600.00"]
        )
        return overview and maximum
    await recorder.check("c11_data_visualization", analysis_overview)

    async def donuts():
        await _reset_records(page)
        await click_named(page, "分析")
        return await contains_texts(page, ["收入分类", "工资", "¥9,800.00", "奖金", "¥1,200.00", "支出分类", "居住", "¥2,600.00", "餐饮", "¥394.00", "交通", "¥50.00"])

    async def trend_default():
        await _reset_records(page)
        await click_named(page, "分析")
        return await visualization_contains_texts(
            page, "趋势", ["支出", "6月", "7月", "8月", "3,207", "3,402", "3,044"]
        )

    async def trend_switch():
        await _reset_records(page)
        await click_named(page, "分析")
        await click_named(page, "收入")
        income = await visualization_contains_texts(
            page, "趋势", ["收入", "9,900", "10,700", "11,000"]
        )
        await click_named(page, "结余")
        balance = await visualization_contains_texts(
            page, "趋势", ["结余", "6,693", "7,298", "7,956"]
        )
        return income and balance
    await recorder.check("c12_content_switching", trend_switch)

    async def weekly_analysis_linkage():
        await _reset_records(page)
        await click_named(page, "分析")
        await click_named(page, "按周")
        return await contains_texts(page, ["2026年8月第2周", "8/3-8/9", "2,976", "收入分类", "支出分类", "收入 Top3", "支出 Top3"])

    async def weekly_trend():
        await _reset_records(page)
        await click_named(page, "分析")
        await click_named(page, "按周")
        return await visualization_contains_texts(
            page, "趋势", ["支出", "8/3-8/9", "8/10-8/16", "2,976", "68"]
        )

    async def monthly_top3():
        await _reset_records(page)
        await click_named(page, "分析")
        return await contains_texts(page, ["收入 Top3", "工资", "¥9,800.00", "项目奖金", "¥1,200.00", "支出 Top3", "房租", "¥2,600.00", "超市采购", "¥326.00", "咖啡豆", "¥68.00"])

    async def weekly_top3():
        await _reset_records(page)
        await click_named(page, "分析")
        await click_named(page, "按周")
        text = await page.locator("body").inner_text()
        return all(value in text for value in ["收入 Top3", "项目奖金", "¥1,200.00", "支出 Top3", "房租", "¥2,600.00", "超市采购", "¥326.00", "地铁充值", "¥50.00"])

    async def validation():
        await _reset_records(page)
        await _open_add(page)
        await fill_any_named(page, ["输入名称", "如：超市采购", "名称"], " ")
        await fill_any_named(page, ["输入金额", "0.00", "金额"], "0")
        await _save_record(page)
        return await contains_texts(page, ["请输入记录名称", "金额必须大于 0", "保存记录", "取消"])
    await recorder.check("c02_form_validation", validation)

    async def create():
        await _reset_records(page)
        await _open_add(page)
        await _fill_record_modal(page, "书店购书", "88", "学习", "2026-08-11", "设计与写作")
        await _save_record(page)
        detail_ok = await contains_texts(page, ["书店购书", "-¥88.00", "学习", "当前结果 7 条", "¥3,132.00", "¥7,868.00"])
        await click_named(page, "分析")
        linked = await contains_texts(page, ["学习", "¥88.00", "3,132", "书店购书"])
        return detail_ok and linked
    await recorder.check("c03_content_editing", create)

    async def edit_move():
        await _reset_records(page)
        await _open_add(page)
        await _fill_record_modal(page, "书店购书", "88", "学习", "2026-08-11", "设计与写作")
        await _save_record(page)
        await _open_record(page, "书店购书")
        await click_named(page, "编辑记录")
        await fill_any_named(page, ["输入名称", "如：超市采购", "名称"], "技术书籍")
        await fill_any_named(page, ["输入金额", "0.00", "金额"], "98")
        dates = page.locator('input[type="date"]')
        await dates.last.fill("2026-07-22")
        await _save_record(page)
        august_gone = await page.get_by_text("书店购书", exact=True).count() == 0
        await _close_detail(page)
        await _set_period(page, "2026年7月")
        detail_ok = await contains_texts(page, ["技术书籍", "-¥98.00", "¥3,500.00", "¥7,200.00"])
        await click_named(page, "分析")
        linked = await contains_texts(page, ["学习", "¥98.00", "3,500"])
        return august_gone and detail_ok and linked
    await recorder.check("c09_content_editing", edit_move)

    async def delete():
        await _reset_records(page)
        await _open_record(page, "咖啡豆")
        await click_named(page, "删除记录")
        prompt = await contains_texts(page, ["确定删除这笔记录吗？", "取消", "确认删除"])
        await click_named(page, "取消")
        remains = await page.get_by_text("咖啡豆", exact=True).count() > 0
        await click_named(page, "删除记录")
        await click_named(page, "确认删除")
        detail_updated = (
            await page.get_by_text("咖啡豆", exact=True).count() == 0
            and await contains_texts(page, ["当前结果 5 条", "¥2,976.00", "¥8,024.00"])
        )
        await click_named(page, "分析")
        analysis_updated = await contains_texts(page, [
            "支出分类", "餐饮", "¥326.00", "支出 Top3", "地铁充值", "¥50.00",
        ])
        trend_updated = await visualization_contains_texts(
            page, "趋势", ["支出", "2,976"]
        )
        return prompt and remains and detail_updated and analysis_updated and trend_updated
    await recorder.check("c10_popup_overlay", delete)

    async def persistence():
        await _reset_records(page)
        await _open_add(page)
        await _fill_record_modal(page, "书店购书", "88", "学习", "2026-08-11", "设计与写作")
        await _save_record(page)
        await page.reload(wait_until="domcontentloaded")
        restored = await contains_texts(page, ["书店购书", "当前结果 7 条", "¥3,132.00", "¥7,868.00", "按月", "2026年8月", "明细"])
        no_overlay = (
            await page.get_by_text("记录详情", exact=True).count() == 0
            and await page.get_by_text("保存记录", exact=True).count() == 0
        )
        await click_named(page, "分析")
        analysis_restored = await ancestor_contains_texts(
            page, "支出分类", ["学习", "¥88.00"]
        )
        return restored and no_overlay and analysis_restored
    await recorder.check("c13_state_persistence", persistence)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-detail")]
    await click_named(page, "分析")
    manifest.append(await capture(page, screenshot_dir, "desktop-analysis", full_page=False))
    return manifest
