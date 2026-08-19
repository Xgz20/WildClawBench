from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_each_any_texts, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_each_any_texts, contains_texts, fill_any_named, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_detail_display", "c03_lists_tables", "c04_detail_display",
    "c05_detail_display", "c06_lists_tables", "c07_detail_display", "c08_detail_display",
    "c09_data_visualization", "c10_detail_display", "c11_cross_region_linkage",
    "c12_search_filtering", "c13_detail_display", "c14_page_navigation",
]
VISUAL_KEYS = ["c15_page_layout", "c16_visual_style", "c17_responsive_layout"]


async def _fresh(page):
    await reset_page(page)


async def _groups(page, *groups):
    return await contains_each_any_texts(page, [list(group) for group in groups])


async def _scenario(page, name):
    try:
        await click_named_any(page, [name, f"选择{name}", f"{name}情景"])
        await page.wait_for_timeout(100)
        return True
    except Exception:
        selects = page.locator("select")
        for index in range(await selects.count()):
            options = await selects.nth(index).locator("option").all_text_contents()
            match = next((item for item in options if name.lower() in item.lower()), None)
            if match:
                await selects.nth(index).select_option(label=match)
                return True
    return False


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def text_check(*groups):
        await _fresh(page)
        return await _groups(page, *groups)

    await recorder.check("c01_information_organization", lambda: text_check(("Annual Energy Outlook 2022", "AEO2022"), ("2020",), ("2050",), ("2022年3月3日", "March 3, 2022", "2022-03-03")))
    await recorder.check("c02_detail_display", lambda: text_check(("石油", "oil"), ("天然气", "natural gas"), ("可再生能源增长最快", "renewables grow fastest"), ("风能", "wind"), ("太阳能", "solar"), ("煤电", "coal"), ("核电", "nuclear"), ("出口", "exports")))
    await recorder.check("c03_lists_tables", lambda: text_check(("Reference", "参考情景"), ("High Economic Growth", "高经济增长"), ("Low Economic Growth", "低经济增长"), ("High Oil Price", "高油价"), ("Low Oil Price", "低油价"), ("High Oil and Gas Supply", "高油气供应"), ("Low Oil and Gas Supply", "低油气供应"), ("High Renewables Cost", "高可再生能源成本"), ("Low Renewables Cost", "低可再生能源成本")))
    await recorder.check("c04_detail_display", lambda: text_check(("2.2%",), ("2.7%",), ("1.8%",), ("90",), ("170",), ("45",), ("Brent", "布伦特")))
    await recorder.check("c05_detail_display", lambda: text_check(("2021年11月", "November 2021"), ("Bipartisan Infrastructure Law", "两党基础设施法"), ("40%",), ("成本不再下降", "costs do not decline")))
    await recorder.check("c06_lists_tables", lambda: text_check(("carbon fee", "碳费"), ("sunset credits", "信贷退坡"), ("extended credits", "信贷延长"), ("no new pipelines", "不新建管道"), ("alternative weather assumptions", "替代天气假设"), ("battery storage", "电池储能")))
    await recorder.check("c07_detail_display", lambda: text_check(("电力消费", "electricity consumption"), ("1%",), ("参考情景", "Reference")))
    await recorder.check("c08_detail_display", lambda: text_check(("LNG", "液化天然气"), ("8万亿", "8 trillion"), ("立方英尺", "cubic feet")))

    async def chart():
        await _fresh(page)
        visuals = page.locator("svg, canvas, [role='img']")
        marks = page.locator("svg rect, svg path, svg circle, canvas, [role='img']")
        return await visuals.count() > 0 and await marks.count() >= 3 and await _groups(page, ("High Oil Price", "高油价"), ("Reference", "参考情景"), ("Low Oil Price", "低油价"))
    await recorder.check("c09_data_visualization", chart)
    await recorder.check("c10_detail_display", lambda: text_check(("EIA", "U.S. Energy Information Administration", "美国能源信息署"), ("public domain", "公有领域", "government publication", "政府出版物")))

    async def linked():
        await _fresh(page)
        if not await _scenario(page, "High Oil Price") and not await _scenario(page, "高油价"):
            return False
        selected = page.locator("[aria-selected='true'], [aria-pressed='true'], .active, .selected")
        return await contains_texts(page, ["170"]) and await selected.filter(has_text="High Oil Price").count() + await selected.filter(has_text="高油价").count() > 0
    await recorder.check("c11_cross_region_linkage", linked)

    async def filtering():
        await _fresh(page)
        try:
            await fill_any_named(page, ["关键词", "搜索情景", "Search", "Filter"], "Renewables")
        except Exception:
            return False
        await page.wait_for_timeout(100)
        body = await page.locator("body").inner_text()
        filtered = "High Renewables Cost" in body and "Low Renewables Cost" in body and "High Oil Price" not in body
        field = page.locator("input").filter(has=page.locator("xpath=.."))
        inputs = page.locator("input[type='search'], input[placeholder*='搜索'], input[placeholder*='Search'], input[placeholder*='关键词']")
        if await inputs.count():
            await inputs.first.fill("")
        await page.wait_for_timeout(100)
        restored = await _groups(page, ("High Oil Price", "高油价"), ("Low Oil Price", "低油价"), ("Reference", "参考情景"))
        return filtered and restored
    await recorder.check("c12_search_filtering", filtering)

    async def gas():
        await _fresh(page)
        try:
            await click_named_any(page, ["天然气", "Natural Gas", "天然气领域"])
        except Exception:
            pass
        return await _groups(page, ("工业用途", "industrial use"), ("出口", "exports"), ("天然气", "natural gas"))
    await recorder.check("c13_detail_display", gas)

    async def navigation():
        await _fresh(page)
        try:
            await click_named_any(page, ["后续专题情景", "专题情景", "Later Cases", "Cases to be released"])
        except Exception:
            return False
        await page.wait_for_timeout(100)
        target = page.get_by_text("carbon fee", exact=False)
        if not await target.count():
            target = page.get_by_text("碳费", exact=False)
        return bool(await target.count() and await target.first.is_visible())
    await recorder.check("c14_page_navigation", navigation)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await _fresh(page)
    shots = [await capture(page, screenshot_dir, "desktop-full")]
    await _scenario(page, "High Oil Price")
    shots.append(await capture(page, screenshot_dir, "scenario-comparison", full_page=False))
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-full"))
    return shots
