from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, fill_any_named, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_content_editing", "c03_detail_display", "c04_form_validation",
    "c05_form_validation", "c06_rule_settlement", "c07_data_visualization", "c08_data_visualization",
    "c09_content_editing", "c10_rule_settlement", "c11_content_editing", "c12_state_persistence",
    "c16_lists_tables",
]
VISUAL_KEYS = ["c13_page_layout", "c14_component_style", "c15_responsive_layout"]


async def _fresh(page):
    await reset_page(page)


async def _select(page, text):
    for i in range(await page.locator("select").count()):
        select = page.locator("select").nth(i)
        options = await select.locator("option").all_text_contents()
        match = next((o for o in options if text.lower() in o.lower()), None)
        if match:
            await select.select_option(label=match)
            return True
    try:
        await click_named_any(page, [text, f"选择{text}"])
        return True
    except Exception:
        return False


async def _open_form(page):
    await click_named_any(page, ["新增投递", "添加投递", "新建投递"])


async def _add(page, company, role, *, status=None, base=None, applied=None, priority=None, link=None, note=None):
    await _open_form(page)
    await fill_any_named(page, ["公司名称", "公司"], company)
    await fill_any_named(page, ["岗位名称", "岗位"], role)
    if status:
        await _select(page, status)
    if base:
        await fill_any_named(page, ["base 地", "base地", "工作地点", "地点"], base)
    if applied:
        await fill_any_named(page, ["投递日期", "日期"], applied)
    if priority:
        if not await _select(page, priority):
            await fill_any_named(page, ["优先级"], priority)
    if link:
        await fill_any_named(page, ["投递链接", "链接"], link)
    if note:
        await fill_any_named(page, ["备注"], note)
    await click_named_any(page, ["保存", "提交", "新增"])
    await page.wait_for_timeout(100)
    return await contains_texts(page, [company, role])


async def _list(page):
    try:
        await click_named_any(page, ["投递清单", "清单"])
    except Exception:
        pass


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def structure():
        await _fresh(page)
        body = await page.locator("body").inner_text()
        required = await contains_texts(page, ["总投递次数", "还在流程中", "已 offer", "已终止", "投递状态分布", "各岗位投递次数", "投递清单", "新增投递"])
        return required and not any(x in body for x in ["NaN", "Infinity", "undefined", "null", "Invalid Date"])
    await recorder.check("c01_information_organization", structure)

    async def minimal():
        await _fresh(page)
        if not await _add(page, "字节跳动", "前端工程师"):
            return False
        await _list(page)
        return await contains_texts(page, ["字节跳动", "前端工程师", "已投递"]) and await page.get_by_text("字节跳动", exact=True).count() == 1
    await recorder.check("c02_content_editing", minimal)

    async def full_record():
        await _fresh(page)
        ok = await _add(page, "字节跳动", "前端工程师", status="已一面", base="杭州", applied="2025-12-20", priority="高", link="https://jobs.example.com/fe-2026", note="内推，等约二面")
        if not ok:
            return False
        await _list(page)
        return await contains_texts(page, ["字节跳动", "前端工程师", "已一面", "杭州", "2025-12-20", "https://jobs.example.com/fe-2026", "内推，等约二面"])
    await recorder.check("c03_detail_display", full_record)

    async def company_suggest():
        if not await minimal():
            return False
        await _open_form(page)
        await fill_any_named(page, ["公司名称", "公司"], "字")
        await page.wait_for_timeout(80)
        datalist = page.locator("datalist option[value='字节跳动'], [role='option']")
        return await page.get_by_text("字节跳动", exact=True).count() > 0 or await datalist.count() > 0
    await recorder.check("c04_form_validation", company_suggest)

    async def base_suggest():
        if not await full_record():
            return False
        await _open_form(page)
        field = page.get_by_label("base 地", exact=False)
        if not await field.count():
            field = page.get_by_placeholder("base", exact=False)
        if not await field.count():
            return False
        await field.first.click()
        await page.wait_for_timeout(80)
        return await page.get_by_text("杭州", exact=True).count() > 0 or await page.locator("datalist option[value='杭州'], [role='option']").count() > 0
    await recorder.check("c05_form_validation", base_suggest)

    async def stats():
        await _fresh(page)
        await _add(page, "网易", "测试开发")
        await _add(page, "字节跳动", "前端工程师", status="已offer")
        await _add(page, "美团", "后端工程师", status="已终止")
        try:
            await click_named_any(page, ["统计看板", "看板"])
        except Exception:
            pass
        text = await page.locator("body").inner_text()
        return all(label in text for label in ["总投递次数", "还在流程中", "已 offer", "已终止"]) and text.count("3") >= 1 and text.count("1") >= 3
    await recorder.check("c06_rule_settlement", stats)

    async def donut():
        await _fresh(page)
        await _add(page, "字节跳动", "前端工程师")
        await _add(page, "网易", "前端工程师")
        await _add(page, "美团", "测试开发", status="已一面")
        try:
            await click_named_any(page, ["统计看板"])
        except Exception:
            pass
        chart = page.locator("svg[aria-label*='状态'], canvas[aria-label*='状态'], [role='img'][aria-label*='状态']")
        return await chart.count() > 0 and await contains_texts(page, ["已投递", "已一面", "2", "1"])
    await recorder.check("c07_data_visualization", donut)

    async def bars():
        await _fresh(page)
        await _add(page, "字节跳动", "前端工程师")
        await _add(page, "网易", "前端工程师")
        await _add(page, "美团", "测试开发")
        try:
            await click_named_any(page, ["统计看板"])
        except Exception:
            pass
        bars = page.locator("svg rect, .bar-fill, [role='img'][aria-label*='岗位']")
        return await bars.count() >= 2 and await contains_texts(page, ["前端工程师", "测试开发", "2", "1"])
    await recorder.check("c08_data_visualization", bars)

    async def edit():
        if not await full_record():
            return False
        row = page.get_by_text("字节跳动", exact=True).locator("xpath=ancestor::tr[1]")
        if not await row.count():
            return False
        await row.get_by_role("button", name="修改", exact=False).click()
        company = page.get_by_label("公司名称", exact=False)
        prefilled = await company.input_value() == "字节跳动"
        await _select(page, "已二面")
        await fill_any_named(page, ["base 地", "base地", "工作地点"], "北京")
        await click_named_any(page, ["保存", "提交"])
        return prefilled and await contains_texts(page, ["字节跳动", "前端工程师", "已二面", "北京"]) and await page.get_by_text("字节跳动", exact=True).count() == 1
    await recorder.check("c09_content_editing", edit)

    async def recent_sort():
        await _fresh(page)
        await _add(page, "美团", "后端工程师")
        await _add(page, "字节跳动", "前端工程师")
        await _list(page)
        row = page.get_by_text("字节跳动", exact=True).locator("xpath=ancestor::tr[1]")
        await row.get_by_role("button", name="修改", exact=False).click()
        await _select(page, "已笔试")
        await click_named_any(page, ["保存", "提交"])
        rows = await page.locator("tbody tr").all_inner_texts()
        return len(rows) >= 2 and "字节跳动" in rows[0] and any("美团" in r for r in rows[1:])
    await recorder.check("c10_rule_settlement", recent_sort)

    async def delete():
        await _fresh(page)
        await _add(page, "字节跳动", "前端工程师")
        await _add(page, "美团", "后端工程师")
        row = page.get_by_text("美团", exact=True).locator("xpath=ancestor::tr[1]")
        await row.get_by_role("button", name="删除", exact=False).click()
        try:
            await click_named_any(page, ["确认删除", "删除", "确定"])
        except Exception:
            pass
        return await contains_texts(page, ["字节跳动", "前端工程师"]) and not await contains_texts(page, ["美团", "后端工程师"])
    await recorder.check("c11_content_editing", delete)

    async def persistence():
        await _fresh(page)
        await _add(page, "字节跳动", "前端工程师", status="已offer")
        await _add(page, "美团", "后端工程师")
        await page.reload(wait_until="domcontentloaded")
        await _list(page)
        return await contains_texts(page, ["字节跳动", "前端工程师", "已offer", "美团", "后端工程师", "已投递"])
    await recorder.check("c12_state_persistence", persistence)

    async def list_fields():
        if not await full_record():
            return False
        headers = ["公司名称", "岗位名称", "投递状态", "base 地", "投递日期", "更新日期", "优先级", "投递链接", "备注"]
        return await contains_texts(page, headers)
    await recorder.check("c16_lists_tables", list_fields)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await _fresh(page)
    shots = [await capture(page, screenshot_dir, "empty-dashboard", full_page=False)]
    try:
        await _add(page, "字节跳动", "前端工程师", status="已offer")
        await _add(page, "美团", "后端工程师", status="已终止")
        await _list(page)
        shots.append(await capture(page, screenshot_dir, "record-list"))
    except Exception:
        pass
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-list"))
    return shots
