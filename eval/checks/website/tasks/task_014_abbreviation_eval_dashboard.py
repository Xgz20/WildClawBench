from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_information_organization", "c03_detail_display",
    "c04_lists_tables", "c05_detail_display", "c06_lists_tables", "c07_detail_display",
    "c08_detail_display", "c09_information_organization", "c10_page_navigation",
    "c11_search_filtering", "c12_content_switching", "c13_content_switching",
    "c14_operation_feedback", "c15_page_navigation",
]
VISUAL_KEYS = ["c16_page_layout", "c17_visual_style", "c18_responsive_layout"]


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)
    specs = {
        "c01_information_organization": ["Dealing with Abbreviations in the Slovenian Biographical Lexicon", "Angel Daza", "Antske Fokkens", "Tomaž Erjavec"],
        "c02_information_organization": ["缩写", "分词", "未登录词", "斯洛文尼亚语", "资源"],
        "c03_detail_display": ["5,047", "51"],
        "c04_lists_tables": ["458", "1385", "399", "66", "236", "130", "33", "131", "420", "181", "70", "655", "2041", "710"],
        "c05_detail_display": ["命名实体", "宏平均", "F1", "30"],
        "c06_lists_tables": ["GigaFida", "89.36", "20.00", "32.68", "Hunspell", "80.81", "71.19", "75.70", "95.85", "76.90", "85.34", "73.27", "95.95", "83.09"],
        "c07_detail_display": ["SloBERTa", "93.94", "98.10", "95.97", "85.34"],
        "c08_detail_display": ["420", "154", "27.16", "49.64", "59.31"],
        "c09_information_organization": ["简单", "未来", "改进"],
        "c12_content_switching": ["PER", "33.85", "70.59", "原始", "展开"],
        "c13_content_switching": ["LOC", "精确率", "召回率", "F1"],
    }
    for key, expected in specs.items():
        async def check(expected=expected):
            await reset_page(page)
            return await contains_texts(page, expected)
        await r.check(key, check)

    async def nav():
        await reset_page(page)
        await click_named_any(page, ["方法对比", "方法", "实验结果"])
        return await page.get_by_text("SloBERTa", exact=False).first.is_visible()
    await r.check("c10_page_navigation", nav)

    async def sorting():
        await reset_page(page)
        table = page.locator("table").filter(has_text="GigaFida")
        if not await table.count():
            return False
        before = await table.first.locator("tbody tr").all_text_contents()
        headers = table.first.locator("th")
        if not await headers.count():
            return False
        await headers.last.click()
        after = await table.first.locator("tbody tr").all_text_contents()
        await headers.last.click()
        twice = await table.first.locator("tbody tr").all_text_contents()
        return before != after and after == list(reversed(twice))
    await r.check("c11_search_filtering", sorting)

    async def citation():
        await reset_page(page)
        value = " ".join(await page.locator("pre, code, blockquote").all_text_contents())
        return "Daza" in value and len(value) > 80
    await r.check("c14_operation_feedback", citation)

    async def paper():
        await reset_page(page)
        link = page.locator('a[href*="assets/paper.pdf"], a[href$="paper.pdf"]')
        if not await link.count(): return False
        href = await link.first.get_attribute("href")
        res = await page.request.get(page.url.rstrip("/") + "/" + href.lstrip("/"))
        return res.ok and (await res.body()).startswith(b"%PDF")
    await r.check("c15_page_navigation", paper)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-abbreviation-dashboard", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-tables", full_page=True))
    return shots
