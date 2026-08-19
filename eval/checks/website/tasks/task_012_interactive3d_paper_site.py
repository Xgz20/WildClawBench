from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_detail_display", "c03_information_organization",
    "c04_lists_tables", "c05_lists_tables", "c06_page_navigation", "c07_content_switching",
    "c08_content_switching", "c09_content_switching", "c10_operation_feedback",
    "c11_content_switching", "c12_detail_display", "c13_operation_feedback",
    "c17_information_organization", "c18_page_navigation", "c19_detail_display", "c20_detail_display",
]
VISUAL_KEYS = ["c14_page_layout", "c15_visual_style", "c16_responsive_layout"]


async def _pdf_link_works(page):
    links = page.locator('a[href$="paper.pdf"], a[href*="assets/paper.pdf"]')
    if not await links.count():
        return False
    href = await links.first.get_attribute("href")
    response = await page.request.get(page.url.rstrip("/") + "/" + href.lstrip("/"))
    return response.ok and (await response.body()).startswith(b"%PDF")


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)
    text_checks = {
        "c01_information_organization": ["Interactive3D", "CVPR 2024", "Shaocong Dong", "Lihe Ding", "Zhanpeng Huang", "Zibin Wang", "Tianfan Xue", "Dan Xu"],
        "c02_detail_display": ["Gaussian Splatting", "InstantNGP", "3D", "交互"],
        "c03_information_organization": ["Gaussian Splatting", "Interactive Hash Refinement", "阶段"],
        "c04_lists_tables": ["添加", "删除", "几何变换", "形变", "刚性拖拽", "语义编辑", "Interactive Hash Refinement"],
        "c05_lists_tables": ["CLIP R-Precision", "Interactive3D", "0.94", "50min", "DreamFusion", "0.67", "1.1h"],
        "c07_content_switching": ["表示转换", "局部", "哈希", "表面", "纹理"],
        "c08_content_switching": ["语义编辑", "局部", "几何变换", "结构"],
        "c09_content_switching": ["形变拖拽", "prompt"],
        "c11_content_switching": ["结果", "Interactive3D"],
        "c12_detail_display": ["Gaussian Splatting", "InstantNGP", "SDS", "损失", "3D"],
        "c17_information_organization": ["Interactive3D", "作者", "方法", "结果", "引用"],
        "c19_detail_display": ["刚性拖拽", "霸王龙", "头", "右"],
        "c20_detail_display": ["高斯", "交互", "几何", "InstantNGP", "细化", "表面"],
    }
    for key, expected in text_checks.items():
        async def check(expected=expected):
            await reset_page(page)
            return await contains_texts(page, expected)
        await r.check(key, check)

    async def navigation():
        await reset_page(page)
        await click_named_any(page, ["方法", "两阶段方法", "Method"])
        return await page.get_by_text("Gaussian Splatting", exact=False).first.is_visible()
    await r.check("c06_page_navigation", navigation)

    async def video():
        await reset_page(page)
        try:
            await click_named_any(page, ["形变拖拽", "Deformable Dragging"])
        except AssertionError:
            pass
        media = page.locator("video")
        if not await media.count():
            return False
        src = await media.first.evaluate("v => v.currentSrc || v.getAttribute('src') || ''")
        if not src or src.startswith("http") and "127.0.0.1" not in src:
            return False
        await media.first.evaluate("v => { v.muted = true; return v.play(); }")
        await page.wait_for_timeout(700)
        return await media.first.evaluate("v => !v.paused || v.currentTime > 0")
    await r.check("c10_operation_feedback", video)

    async def citation():
        await reset_page(page)
        code = page.locator("pre, code")
        values = " ".join(await code.all_text_contents())
        return "Interactive3D" in values and ("Dong" in values or "bib" in values.lower())
    await r.check("c13_operation_feedback", citation)

    async def paper():
        await reset_page(page)
        return await _pdf_link_works(page)
    await r.check("c18_page_navigation", paper)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-paper-home", full_page=True)]
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-method-results", full_page=True))
    return shots
