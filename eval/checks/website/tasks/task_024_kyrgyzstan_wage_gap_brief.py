from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, fill_any_named, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_detail_display", "c03_detail_display",
    "c04_information_organization", "c05_detail_display", "c06_lists_tables",
    "c07_detail_display", "c08_data_visualization", "c09_detail_display",
    "c10_lists_tables", "c11_search_filtering", "c12_page_navigation",
]
VISUAL_KEYS = ["c13_page_layout", "c14_visual_style", "c15_responsive_layout"]


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)
    specs = {
        "c01_information_organization": ["Kyrgyzstan", "Irina Kovaleva", "2016", "2019", "工资差距"],
        "c02_detail_display": ["2018", "28.4%", "2019", "23%", "5.4"],
        "c03_detail_display": ["Life in Kyrgyzstan", "2010", "2019", "分层", "两阶段", "3000", "8100", "比什凯克", "奥什"],
        "c04_information_organization": ["OLS", "Heckman", "1979", "Oaxaca-Blinder", "1973", "Mincer", "1974"],
        "c05_detail_display": ["Oaxaca-Blinder", "可观测", "解释", "系数", "差异"],
        "c06_lists_tables": ["2,925", "2,545", ".1276371", ".1375113", "-.0417533", "-.0470802", ".1693904", ".1845915"],
        "c07_detail_display": ["12.8%", "13.8%", "扩大", "无法", "歧视", "未观测"],
        "c09_detail_display": ["Irina Kovaleva", "CC BY 4.0"],
        "c10_lists_tables": ["OLS", "2016", "974", "870", "2019", "879", "636"],
    }
    for key, expected in specs.items():
        async def check(expected=expected):
            await reset_page(page)
            return await contains_texts(page, expected)
        await r.check(key, check)

    async def chart():
        await reset_page(page)
        visual = page.locator("canvas, svg, [role='img']")
        return await visual.count() > 0 and await contains_texts(page, ["2016", "2019", "Explained", "Unexplained"])
    await r.check("c08_data_visualization", chart)

    async def filtering():
        await reset_page(page)
        await fill_any_named(page, ["关键词", "搜索参考文献", "搜索"], "Heckman")
        await page.wait_for_timeout(100)
        refs = page.get_by_text("Heckman", exact=False)
        text = await page.locator("body").inner_text()
        return await refs.count() >= 1 and "Sample selection bias as a specification error" in text
    await r.check("c11_search_filtering", filtering)

    async def nav():
        await reset_page(page)
        await click_named_any(page, ["结论", "研究结论", "Conclusions"])
        heading = page.get_by_text("结论", exact=True)
        if not await heading.count(): return False
        box = await heading.first.bounding_box()
        return bool(box and 0 <= box["y"] < 900)
    await r.check("c12_page_navigation", nav)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-wage-brief", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-wage-brief", full_page=True))
    return shots
