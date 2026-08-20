from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_information_organization", "c03_lists_tables",
    "c04_detail_display", "c05_detail_display", "c06_detail_display", "c07_detail_display",
    "c08_lists_tables", "c09_page_navigation", "c10_content_switching", "c11_content_switching",
    "c12_content_switching", "c13_operation_feedback", "c14_page_navigation", "c15_information_organization",
]
VISUAL_KEYS = ["c16_page_layout", "c17_visual_style", "c18_responsive_layout"]


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)
    specs = {
        "c01_information_organization": ["The Essentials of AI for Life and Society", "The University of Texas at Austin", "1 学分", "14 周", "线上", "2023"],
        "c02_information_organization": ["非技术", "学生", "教职工", "校外", "不需要", "数学"],
        "c03_lists_tables": ["AI100", "Current and Future Directions", "14"],
        "c04_detail_display": ["Computer Vision", "Kristen Grauman", "AI and Mis/disinformation", "Matt Lease", "Scott Aaronson", "Luis Sentis"],
        "c05_detail_display": ["788", "132", "631", "25", "17"],
        "c06_detail_display": ["出勤", "30%", "测验", "40%", "反思", "30%"],
        "c07_detail_display": ["4.23", "4.33", "4.00", "4.20"],
        "c08_lists_tables": ["+1.37", "+0.97", "p<0.01"],
        "c10_content_switching": ["Computer Vision", "Kristen Grauman"],
        "c11_content_switching": ["+1.19"],
        "c12_content_switching": ["22%", "37%", "19%", "阅读", "互动"],
        "c15_information_organization": ["2024", "3 学分", "修学分", "旁听", "博客", "新闻"],
    }
    for key, expected in specs.items():
        async def check(expected=expected):
            await reset_page(page)
            return await contains_texts(page, expected)
        await r.check(key, check)

    async def nav():
        await reset_page(page)
        await click_named_any(page, ["课表", "课程安排", "十四讲"])
        return await page.get_by_text("Computer Vision", exact=False).first.is_visible()
    await r.check("c09_page_navigation", nav)

    async def citation():
        await reset_page(page)
        text = " ".join(await page.locator("pre, code, blockquote").all_text_contents())
        return "AI for Life and Society" in text and len(text) > 80
    await r.check("c13_operation_feedback", citation)

    async def paper():
        await reset_page(page)
        link = page.locator('a[href*="assets/paper.pdf"], a[href$="paper.pdf"]')
        if not await link.count():
            return False
        href = await link.first.get_attribute("href")
        response = await page.request.get(page.url.rstrip("/") + "/" + href.lstrip("/"))
        return response.ok and (await response.body()).startswith(b"%PDF")
    await r.check("c14_page_navigation", paper)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-course", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-course", full_page=True))
    return shots
