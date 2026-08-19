from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_lists_tables", "c03_detail_display",
    "c04_detail_display", "c05_detail_display", "c06_lists_tables", "c07_detail_display",
    "c08_lists_tables", "c09_page_navigation", "c10_information_organization",
    "c11_operation_feedback", "c12_file_upload_and_download",
]
VISUAL_KEYS = ["c13_page_layout", "c14_visual_style", "c15_responsive_layout"]


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)
    specs = {
        "c01_information_organization": ["COMMENTATOR", "Rajvee Sheth", "Shubh Nisar", "Heenaben Prajapati", "Himanshu Beniwal", "Mayank Singh"],
        "c02_lists_tables": ["语言识别", "LID", "词性标注", "POS", "主体语言", "MLI"],
        "c03_detail_display": ["标注员", "任务选择", "标注页", "历史", "修改"],
        "c04_detail_display": ["管理员", "CSV", "Cohen's Kappa", "CMI", "导出", "筛选"],
        "c05_detail_display": ["CMI", "0", "100", "单语", "高度混合"],
        "c06_lists_tables": ["YEDDA", "757.00", "1370.66", "MarkUp", "1192.33", "1579.00", "INCEpTION", "1040.66", "1714.66", "UBIAI", "690.66", "748.33", "GATE", "1118.33", "COMMENTATOR", "138.33", "337.66"],
        "c07_detail_display": ["UBIAI", "LID", "5", "POS", "2"],
        "c08_lists_tables": ["网页版", "预训练模型", "基础", "Fleiss", "Krippendorff", "组内相关"],
        "c10_information_organization": ["标注员", "管理员", "历史", "CSV", "一致性"],
    }
    for key, expected in specs.items():
        async def check(expected=expected):
            await reset_page(page)
            return await contains_texts(page, expected)
        await r.check(key, check)

    async def nav():
        await reset_page(page)
        await click_named_any(page, ["耗时对比", "性能", "实验结果"])
        return await page.get_by_text("138.33", exact=False).first.is_visible()
    await r.check("c09_page_navigation", nav)

    async def citation():
        await reset_page(page)
        value = " ".join(await page.locator("pre, code, blockquote").all_text_contents())
        return "COMMENTATOR" in value and "Sheth" in value and len(value) > 80
    await r.check("c11_operation_feedback", citation)

    async def paper():
        await reset_page(page)
        link = page.locator('a[href*="assets/paper.pdf"], a[href$="paper.pdf"]')
        if not await link.count(): return False
        href = await link.first.get_attribute("href")
        res = await page.request.get(page.url.rstrip("/") + "/" + href.lstrip("/"))
        return res.ok and (await res.body()).startswith(b"%PDF")
    await r.check("c12_file_upload_and_download", paper)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-commentator", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-commentator", full_page=True))
    return shots
