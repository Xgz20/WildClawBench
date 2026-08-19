from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_information_organization", "c03_lists_tables",
    "c04_information_organization", "c05_detail_display", "c06_detail_display",
    "c07_detail_display", "c08_lists_tables", "c09_detail_display", "c10_detail_display",
    "c11_page_navigation", "c12_detail_display", "c13_detail_display",
    "c14_operation_feedback", "c15_file_upload_and_download",
]
VISUAL_KEYS = ["c16_page_layout", "c17_visual_style", "c18_responsive_layout"]


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)
    specs = {
        "c01_information_organization": ["Statistical Uncertainty in Word Embeddings: GloVe-V", "Andrea Vallebueno", "Cassandra Handan-Nader", "Christopher D. Manning", "Daniel E. Ho", "Stanford University"],
        "c02_information_organization": ["点估计", "数据稀疏", "bootstrap", "置换检验", "计算"],
        "c03_lists_tables": ["矩阵", "向量", "标量", "集合", "D", "词向量维度", "V", "词表", "K", "共现"],
        "c04_information_organization": ["GloVe", "代价函数", "低秩", "加权最小二乘", "多元正态", "方差", "协方差"],
        "c05_detail_display": ["上下文向量", "固定", "最优", "加权", "对数", "多元正态", "独立"],
        "c06_detail_display": ["100", "3/4", "1", "权重函数"],
        "c07_detail_display": ["|K|", "D", "Moore-Penrose", "伪逆", "数值"],
        "c08_lists_tables": ["上下文词", "共现矩阵", "GloVe", "稀疏", "超参数", "固定"],
        "c09_detail_display": ["纽约时报", "50", "96%", "300", "36%"],
        "c10_detail_display": ["COHA", "1900", "1999", "300", "8"],
        "c12_detail_display": ["多元正态", "公式", "概率"],
        "c13_detail_display": ["K", "共现", "下标"],
    }
    for key, expected in specs.items():
        async def check(expected=expected):
            await reset_page(page)
            return await contains_texts(page, expected)
        await r.check(key, check)

    async def nav():
        await reset_page(page)
        await click_named_any(page, ["推导", "方法推导", "Derivation"])
        return await page.get_by_text("加权最小二乘", exact=False).first.is_visible()
    await r.check("c11_page_navigation", nav)

    async def citation():
        await reset_page(page)
        value = " ".join(await page.locator("pre, code, blockquote").all_text_contents())
        return "GloVe-V" in value and "Vallebueno" in value and len(value) > 100
    await r.check("c14_operation_feedback", citation)

    async def paper():
        await reset_page(page)
        link = page.locator('a[href*="assets/paper.pdf"], a[href$="paper.pdf"]')
        if not await link.count(): return False
        href = await link.first.get_attribute("href")
        res = await page.request.get(page.url.rstrip("/") + "/" + href.lstrip("/"))
        return res.ok and (await res.body()).startswith(b"%PDF")
    await r.check("c15_file_upload_and_download", paper)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-glove-v", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-derivation", full_page=True))
    return shots
