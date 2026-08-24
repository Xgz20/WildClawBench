from __future__ import annotations

from datetime import date, timedelta

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, fill_any_named, reset_page

RUNTIME_KEYS = [
    "c01_information_organization", "c02_rule_settlement", "c03_content_switching", "c04_content_editing",
    "c05_rule_settlement", "c07_form_validation", "c08_rule_settlement", "c09_file_upload_and_download",
    "c10_lists_tables", "c11_detail_display", "c12_content_editing", "c13_popup_overlay",
    "c14_state_persistence", "c15_cross_region_linkage", "c16_rule_settlement", "c17_rule_settlement",
    "c18_information_organization", "c19_content_switching", "c20_data_visualization",
    "c21_data_visualization", "c22_rule_settlement", "c25_rule_settlement",
    "c26_rule_settlement",
]
VISUAL_KEYS = ["c06_component_style", "c23_visual_style", "c24_responsive_layout"]
EVAL = "/tmp_workspace_eval"


async def _fresh(page):
    await reset_page(page)


async def _select(page, text):
    for i in range(await page.locator("select").count()):
        select = page.locator("select").nth(i)
        options = await select.locator("option").all_text_contents()
        match = next((item for item in options if text in item), None)
        if match:
            await select.select_option(label=match)
            return True
    try:
        await click_named_any(page, [text, f"选择{text}"])
        return True
    except Exception:
        return False


async def _open_form(page):
    await click_named_any(page, ["小酌一下", "新增记录", "记一杯", "添加记录"])


async def _record(page, scene, wine, amount, *, companion=None, price=None, note=None, time=None):
    await _open_form(page)
    await _select(page, scene)
    await _select(page, wine)
    try:
        await fill_any_named(page, [f"{wine}饮用量", "饮用量", "毫升", "容量"], str(amount))
    except Exception:
        number = page.locator("input[type=number]")
        if not await number.count():
            return False
        await number.last.fill(str(amount))
    if companion:
        await fill_any_named(page, ["同饮人", "一起喝", "搭子"], companion)
    if price is not None:
        await fill_any_named(page, ["价格", "花费"], str(price))
    if note:
        await fill_any_named(page, ["备注"], note)
    if time:
        await fill_any_named(page, ["饮酒时间", "时间"], time)
    await click_named_any(page, ["保存记录", "保存", "提交"])
    await page.wait_for_timeout(80)
    return await contains_texts(page, [scene, wine])


async def _records(page):
    await click_named_any(page, ["记录", "记录页", "全部记录"])
    await page.wait_for_timeout(50)


async def _stats(page):
    await click_named_any(page, ["统计", "统计页"])
    await page.wait_for_timeout(50)


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def home():
        await _fresh(page)
        return await contains_texts(page, ["今日小酌了吗", "本月饮酒天数", "本月摄入酒精量"]) and await contains_any_texts(page, ["记录", "记录页"]) and await contains_any_texts(page, ["统计", "统计页"]) and await page.locator("[role=grid], table, .calendar").count() > 0
    await r.check("c01_information_organization", home)

    async def future_day():
        await _fresh(page)
        today = date.today().day
        tomorrow = today + 1
        controls = page.get_by_role("button", name=str(tomorrow), exact=True)
        if not await controls.count():
            return False
        selected_before = await page.locator("[aria-selected=true], .selected, .is-selected").all_inner_texts()
        await controls.first.click()
        selected_after = await page.locator("[aria-selected=true], .selected, .is-selected").all_inner_texts()
        return selected_before == selected_after and not await page.locator("[role=dialog], dialog, .modal").count()
    await r.check("c02_rule_settlement", future_day)

    async def month_switch():
        await _fresh(page)
        title = page.locator(".calendar-title, [data-calendar-title], h2").first
        before = await title.inner_text()
        await click_named_any(page, ["上个月", "上一月", "‹", "Previous month"])
        previous = await title.inner_text()
        await click_named_any(page, ["下个月", "下一月", "›", "Next month"])
        return previous != before and await title.inner_text() == before
    await r.check("c03_content_switching", month_switch)

    async def basic_record():
        await _fresh(page)
        await _open_form(page)
        time_input = page.locator("input[type=datetime-local], input[type=date], input[type=time]")
        prefilled = await time_input.count() > 0 and bool(await time_input.first.input_value())
        await _select(page, "餐厅")
        await _select(page, "鹭岛小麦白啤")
        await fill_any_named(page, ["饮用量", "毫升", "容量"], "500")
        await click_named_any(page, ["保存记录", "保存", "提交"])
        return prefilled and await contains_texts(page, ["餐厅", "鹭岛小麦白啤", "500"])
    await r.check("c04_content_editing", basic_record)

    async def monthly_summary():
        await _fresh(page)
        if not await _record(page, "家中", "鹭岛小麦白啤", 500):
            return False
        try:
            await click_named_any(page, ["首页"])
        except Exception:
            pass
        return await contains_texts(page, ["本月饮酒天数", "1", "本月摄入酒精量", "25"])
    await r.check("c05_rule_settlement", monthly_summary)

    async def missing_wine():
        await _fresh(page)
        await _open_form(page)
        await _select(page, "酒吧")
        try:
            await click_named_any(page, ["保存记录", "保存", "提交"])
        except Exception:
            pass
        return await contains_any_texts(page, ["请选择酒", "酒品必填", "必须选择酒品"]) and await page.locator("[role=dialog], dialog, .modal, form").count() > 0
    await r.check("c07_form_validation", missing_wine)

    async def estimate():
        await _fresh(page)
        await _open_form(page)
        await _select(page, "鹭岛小麦白啤")
        nums = page.locator("input[type=number]")
        if not await nums.count():
            return False
        await nums.last.fill("500")
        await _select(page, "汾溪清香二十年")
        nums = page.locator("input[type=number]")
        await nums.last.fill("50")
        await page.wait_for_timeout(60)
        return await contains_texts(page, ["2", "550", "51"])
    await r.check("c08_rule_settlement", estimate)

    async def photos():
        await _fresh(page)
        await _open_form(page)
        inp = page.locator("input[type=file]")
        if not await inp.count():
            return False
        await inp.first.set_input_files([f"{EVAL}/drink-photo-0{i}.jpg" for i in range(1, 4)])
        await page.wait_for_timeout(80)
        previews = page.locator(".photo-preview img, .photos img, [data-photo] img")
        first_count = await previews.count()
        try:
            await inp.first.set_input_files(f"{EVAL}/drink-photo-04.jpg")
        except Exception:
            pass
        return first_count == 3 and await previews.count() == 3
    await r.check("c09_file_upload_and_download", photos)

    async def list_records():
        await _fresh(page)
        await _record(page, "家中", "鹭岛小麦白啤", 500)
        await _record(page, "酒吧", "北岭十二年单一麦芽", 50)
        await _records(page)
        return await contains_texts(page, ["家中", "鹭岛小麦白啤", "500", "酒吧", "北岭十二年单一麦芽", "50"])
    await r.check("c10_lists_tables", list_records)

    async def detail():
        await _fresh(page)
        await _record(page, "酒吧", "北岭十二年单一麦芽", 50, companion="老陈", price=180, note="庆祝升职")
        await _records(page)
        await click_named_any(page, ["查看详情", "详情", "北岭十二年单一麦芽"])
        return await contains_texts(page, ["酒吧", "老陈", "180", "庆祝升职", "北岭十二年单一麦芽", "50"])
    await r.check("c11_detail_display", detail)

    async def edit():
        await _fresh(page)
        await _record(page, "家中", "鹭岛小麦白啤", 500)
        await _records(page)
        await click_named_any(page, ["编辑", "修改"])
        await _select(page, "餐厅")
        field = page.locator("input[type=number]").last
        await field.fill("200")
        await click_named_any(page, ["保存修改", "保存", "提交"])
        return await contains_texts(page, ["餐厅", "200", "10"])
    await r.check("c12_content_editing", edit)

    async def delete_confirm():
        await _fresh(page)
        await _record(page, "家中", "鹭岛小麦白啤", 500)
        await _records(page)
        await click_named_any(page, ["删除"])
        dialog = page.locator("[role=dialog], dialog, .modal, .overlay")
        opened = await dialog.count() and await dialog.first.is_visible()
        await click_named_any(page, ["取消"])
        stayed = await contains_texts(page, ["鹭岛小麦白啤"])
        await click_named_any(page, ["删除"])
        await click_named_any(page, ["确认删除", "确认", "确定"])
        return bool(opened and stayed and await contains_any_texts(page, ["没有记录", "暂无记录"]))
    await r.check("c13_popup_overlay", delete_confirm)

    async def persistence():
        await _fresh(page)
        await _record(page, "朋友家", "稻乡桂花米酒", 200)
        await page.reload(wait_until="domcontentloaded")
        await _records(page)
        return await contains_texts(page, ["朋友家", "稻乡桂花米酒"])
    await r.check("c14_state_persistence", persistence)

    async def add_wine():
        await _fresh(page)
        await click_named_any(page, ["酒库", "我的酒库"])
        await click_named_any(page, ["新增酒品", "添加酒品", "新增一款酒"])
        await _select(page, "清酒")
        await fill_any_named(page, ["品牌"], "月见")
        await fill_any_named(page, ["名称", "酒名"], "月见纯米酒")
        await fill_any_named(page, ["酒精度"], "14")
        await fill_any_named(page, ["规格"], "500ml/瓶")
        await click_named_any(page, ["保存酒品", "保存", "添加"])
        await click_named_any(page, ["首页"])
        await _open_form(page)
        return await contains_texts(page, ["月见纯米酒", "鹭岛小麦白啤"])
    await r.check("c15_cross_region_linkage", add_wine)

    async def monthly_metrics():
        await _fresh(page)
        await _record(page, "餐厅", "鹭岛小麦白啤", 500, price=120)
        await _record(page, "家中", "黎山赤霞珠2019", 200, price=80)
        await _stats(page)
        await _select(page, "月度")
        return await contains_texts(page, ["饮酒天数", "1", "饮酒花费", "200", "酒款数", "2", "摄入酒精量", "51"])
    await r.check("c16_rule_settlement", monthly_metrics)

    async def month_scope():
        await _fresh(page)
        await click_named_any(page, ["上个月", "上一月", "‹"])
        past_day = page.locator("[role=gridcell] button:not([disabled]), .calendar-day:not(.disabled)").first
        if await past_day.count():
            await past_day.click()
        await _record(page, "家中", "汾溪清香二十年", 50)
        try:
            await click_named_any(page, ["首页"])
        except Exception:
            pass
        await click_named_any(page, ["下个月", "下一月", "›"])
        await _record(page, "餐厅", "鹭岛小麦白啤", 500)
        await _stats(page)
        return await contains_texts(page, ["饮酒天数", "1", "摄入酒精量", "25"])
    await r.check("c17_rule_settlement", month_scope)

    async def stats_structure():
        await _fresh(page)
        await _stats(page)
        return await contains_texts(page, ["饮酒天数", "饮酒花费", "酒款数", "摄入酒精量", "最常饮酒场景", "最常饮用酒品", "最常一起喝的搭子", "最常饮酒时间段"]) and await page.locator("svg, canvas, [role=img], .calendar").count() >= 3
    await r.check("c18_information_organization", stats_structure)

    async def period_switch():
        await _fresh(page)
        await _stats(page)
        before = await page.locator("body").inner_text()
        await _select(page, "年度")
        annual = await page.locator("body").inner_text()
        await _select(page, "月度")
        monthly = await page.locator("body").inner_text()
        return annual != before and monthly != annual and str(date.today().year) in annual
    await r.check("c19_content_switching", period_switch)

    async def donut():
        await _fresh(page)
        await _record(page, "餐厅", "鹭岛小麦白啤", 500)
        await _record(page, "家中", "汾溪清香二十年", 50)
        await _stats(page)
        chart = page.locator("svg[aria-label*='类型'], canvas[aria-label*='类型'], .donut, .pie-chart")
        return await chart.count() > 0 and await contains_texts(page, ["啤酒", "白酒"])
    await r.check("c20_data_visualization", donut)

    async def trend():
        await _fresh(page)
        await _record(page, "餐厅", "鹭岛小麦白啤", 500)
        await _stats(page)
        marks = page.locator("svg circle, svg rect, svg path, canvas, .bar, .point")
        return await marks.count() > 0 and await contains_texts(page, [str(date.today().day), "25"])
    await r.check("c21_data_visualization", trend)

    async def top_conclusions():
        await _fresh(page)
        await _record(page, "餐厅", "鹭岛小麦白啤", 500, companion="老陈")
        await _record(page, "餐厅", "鹭岛小麦白啤", 500, companion="老陈")
        await _record(page, "家中", "黎山赤霞珠2019", 200, companion="小林")
        await _stats(page)
        return await contains_texts(page, ["最常饮酒场景", "餐厅", "最常饮用酒品", "鹭岛小麦白啤", "最常一起喝的搭子", "老陈"])
    await r.check("c22_rule_settlement", top_conclusions)

    async def morning():
        await _fresh(page)
        await _record(page, "家中", "鹭岛小麦白啤", 500, time="07:00")
        await _record(page, "家中", "鹭岛小麦白啤", 500, time="07:00")
        await _stats(page)
        return await contains_any_texts(page, ["早晨", "清晨", "上午", "06:00-09:00", "6:00–9:00"])
    await r.check("c25_rule_settlement", morning)

    async def all_metrics_reconcile():
        await _fresh(page)
        await _record(page, "餐厅", "鹭岛小麦白啤", 500, companion="老陈", price=120)
        home_ok = await contains_texts(page, ["本月饮酒天数", "1", "本月摄入酒精量", "25"])
        await _stats(page)
        body = await page.locator("body").inner_text()
        stats_ok = await contains_texts(page, [
            "饮酒天数", "1", "饮酒花费", "120", "酒款数", "1", "摄入酒精量", "25",
            "餐厅", "鹭岛小麦白啤", "老陈",
        ])
        return home_ok and stats_ok and not any(value in body for value in ["NaN", "Infinity", "undefined"])
    await r.check("c26_rule_settlement", all_metrics_reconcile)
    return r.results


async def capture_visual(page, screenshot_dir):
    await _fresh(page)
    shots = [await capture(page, screenshot_dir, "desktop-home", full_page=False)]
    try:
        await _stats(page)
        shots.append(await capture(page, screenshot_dir, "desktop-stats"))
    except Exception:
        pass
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-stats"))
    return shots
