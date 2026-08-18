from __future__ import annotations

try:
    from ..common import (
        CheckRecorder, capture, click_named, contains_any_texts, contains_texts,
        fill_any_named, reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, contains_any_texts, contains_texts,
        fill_any_named, reset_page,
    )


RUNTIME_KEYS = [
    "criterion_01_basic_content", "criterion_02_information_organization", "criterion_03_content_switching",
    "criterion_04_file_upload_and_download", "criterion_05_form_filling_and_validation",
    "criterion_06_file_upload_and_download", "criterion_07_content_creation_and_editing",
    "criterion_08_content_creation_and_editing", "criterion_09_form_filling_and_validation",
    "criterion_10_content_switching", "criterion_11_content_switching", "criterion_12_content_creation_and_editing",
    "criterion_13_form_filling_and_validation", "criterion_14_file_upload_and_download", "criterion_15_page_navigation",
]
VISUAL_KEYS = ["criterion_16_page_layout", "criterion_17_responsive_layout"]

EVAL = "/tmp_workspace_eval"


async def _choose_function(page, label: str) -> bool:
    for candidate in (label, label.replace("PDF", "pdf"), label.replace("图片", "图像")):
        try:
            await click_named(page, candidate)
            await page.wait_for_timeout(100)
            return True
        except Exception:
            continue
    return False


async def _set_files(page, names: list[str]) -> bool:
    inputs = page.locator('input[type="file"]')
    if not await inputs.count():
        return False
    paths = [f"{EVAL}/{name}" for name in names]
    await inputs.first.set_input_files(paths)
    await page.wait_for_timeout(120)
    return True


async def _start_process(page) -> bool:
    for label in ("开始处理", "开始转换", "开始拆分", "应用签名"):
        try:
            await click_named(page, label)
            await page.wait_for_timeout(250)
            return True
        except Exception:
            continue
    return False


async def _result_text(page) -> str:
    await page.wait_for_timeout(500)
    return await page.locator("body").inner_text()


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def basic():
        await reset_page(page)
        return await contains_texts(page, ["文页工坊", "把文件整理成一份好用的 PDF", "开始使用"])
    await recorder.check("criterion_01_basic_content", basic)

    async def functions():
        await reset_page(page)
        text = await page.locator("body").inner_text()
        return all(label in text for label in ["图片转 PDF", "图片合并 PDF", "PDF 合并", "PDF 拆分", "PDF 转图片", "PDF 签名"])
    await recorder.check("criterion_02_information_organization", functions)

    async def switch_function():
        await reset_page(page)
        ok = await _choose_function(page, "图片转 PDF")
        first = await contains_texts(page, ["选择文件", "图片"])
        ok = await _choose_function(page, "PDF 拆分") and ok
        second = await contains_texts(page, ["页码", "拆分"])
        ok = await _choose_function(page, "PDF 签名") and ok
        third = await contains_texts(page, ["签名", "颜色", "大小"])
        return ok and first and second and third
    await recorder.check("criterion_03_content_switching", switch_function)

    async def upload_image():
        await reset_page(page)
        if not await _choose_function(page, "图片转 PDF") or not await _set_files(page, ["sample-image-a.png"]):
            return False
        return await contains_texts(page, ["sample-image-a.png", "PNG", "大小", "移除"])
    await recorder.check("criterion_04_file_upload_and_download", upload_image)

    async def file_validation():
        await reset_page(page)
        if not await _choose_function(page, "图片转 PDF"):
            return False
        inputs = page.locator('input[type="file"]')
        if not await inputs.count():
            return False
        for payload, expected in [
            ({"name": "bad.txt", "mimeType": "text/plain", "buffer": b"text"}, "格式"),
            ({"name": "empty.png", "mimeType": "image/png", "buffer": b""}, "为空"),
            ({"name": "large.png", "mimeType": "image/png", "buffer": b"0" * (51 * 1024 * 1024)}, "过大"),
        ]:
            await inputs.first.set_input_files(payload)
            if not (
                await contains_texts(page, [expected])
                and await contains_any_texts(
                    page, ["不支持", "为空", "过大", "无效", "不能", "错误"]
                )
            ):
                return False
        return True
    await recorder.check("criterion_05_form_filling_and_validation", file_validation)

    async def convert_pdf():
        await reset_page(page)
        if not await _choose_function(page, "图片转 PDF") or not await _set_files(page, ["sample-image-a.png"]):
            return False
        if not await _start_process(page):
            return False
        text = await _result_text(page)
        return "PDF" in text and "下载" in text and any(token in text for token in ("完成", "页", "结果"))
    await recorder.check("criterion_06_file_upload_and_download", convert_pdf)

    async def merge_images():
        await reset_page(page)
        if not await _choose_function(page, "图片合并 PDF") or not await _set_files(page, ["sample-image-a.png", "sample-image-b.png"]):
            return False
        before = await page.locator("body").inner_text()
        if not await _start_process(page):
            return False
        text = await _result_text(page)
        return "sample-image-a.png" in before and "sample-image-b.png" in before and "2" in text and "PDF" in text
    await recorder.check("criterion_07_content_creation_and_editing", merge_images)

    async def merge_pdfs():
        await reset_page(page)
        if not await _choose_function(page, "PDF 合并") or not await _set_files(page, ["sample-2-pages.pdf", "sample-4-pages.pdf"]):
            return False
        if not await _start_process(page):
            return False
        text = await _result_text(page)
        return "6" in text and "PDF" in text and await contains_texts(page, ["输出名称", "下载"])
    await recorder.check("criterion_08_content_creation_and_editing", merge_pdfs)

    async def invalid_ranges():
        await reset_page(page)
        if not await _choose_function(page, "PDF 拆分") or not await _set_files(page, ["sample-4-pages.pdf"]):
            return False
        inputs = page.locator('input[type="number"], input[placeholder*="页"], input[placeholder*="范围"]')
        if await inputs.count() < 2:
            return await contains_texts(page, ["页码范围", "请输入"])
        cases = [
            (("", ""), ["请输入", "不能为空", "必填"]),
            (("3", "2"), ["起始页不能大于结束页", "开始页不能大于结束页", "范围无效"]),
            (("1", "9"), ["超出", "不能超过", "总页数", "范围无效"]),
        ]
        for values, messages in cases:
            await inputs.nth(0).fill(values[0])
            await inputs.nth(1).fill(values[1])
            await _start_process(page)
            if not await contains_any_texts(page, messages):
                return False
        return True
    await recorder.check("criterion_09_form_filling_and_validation", invalid_ranges)

    async def split_modes():
        await reset_page(page)
        if not await _choose_function(page, "PDF 拆分") or not await _set_files(page, ["sample-4-pages.pdf"]):
            return False
        await _start_process(page)
        first = await _result_text(page)
        return ("4" in first and "结果" in first) or await contains_texts(page, ["每页一个文件", "页码范围"])
    await recorder.check("criterion_10_content_switching", split_modes)

    async def pdf_to_image():
        await reset_page(page)
        if not await _choose_function(page, "PDF 转图片") or not await _set_files(page, ["sample-2-pages.pdf"]):
            return False
        for fmt in ("PNG", "JPG"):
            try:
                await click_named(page, fmt)
            except Exception:
                pass
            await _start_process(page)
            text = await _result_text(page)
            if fmt not in text and fmt.lower() not in text.lower():
                return False
        return True
    await recorder.check("criterion_11_content_switching", pdf_to_image)

    async def signature_preview():
        await reset_page(page)
        if not await _choose_function(page, "PDF 签名") or not await _set_files(page, ["sample-2-pages.pdf"]):
            return False
        try:
            await fill_any_named(page, ["签名文字", "输入签名", "签名"], "小满")
            for label in ("颜色", "大小", "添加签名"):
                try:
                    await click_named(page, label)
                except Exception:
                    pass
        except Exception:
            return False
        return await contains_texts(page, ["小满", "预览"])
    await recorder.check("criterion_12_content_creation_and_editing", signature_preview)

    async def empty_signature():
        await reset_page(page)
        if not await _choose_function(page, "PDF 签名"):
            return False
        await _start_process(page)
        return await contains_any_texts(page, ["签名不能为空", "请输入签名"])
    await recorder.check("criterion_13_form_filling_and_validation", empty_signature)

    async def download_feedback():
        await reset_page(page)
        if not await _choose_function(page, "图片转 PDF") or not await _set_files(page, ["sample-image-a.png"]):
            return False
        if not await _start_process(page):
            return False
        try:
            await fill_any_named(page, ["输出名称", "文件名"], "我的文档")
            await click_named(page, "下载")
        except Exception:
            return False
        return await contains_texts(page, ["我的文档"]) and await contains_any_texts(
            page, ["已下载", "下载成功", "开始下载"]
        )
    await recorder.check("criterion_14_file_upload_and_download", download_feedback)

    async def restart():
        await reset_page(page)
        if not await _choose_function(page, "图片转 PDF") or not await _set_files(page, ["sample-image-a.png"]):
            return False
        await _start_process(page)
        for label in ("重新开始", "返回功能选择"):
            try:
                await click_named(page, label)
                return await contains_texts(page, ["图片转 PDF", "PDF 合并", "开始使用"])
            except Exception:
                continue
        return False
    await recorder.check("criterion_15_page_navigation", restart)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-functions", full_page=False)]
    try:
        await _choose_function(page, "图片转 PDF")
        await _set_files(page, ["sample-image-a.png"])
        manifest.append(await capture(page, screenshot_dir, "desktop-file-step", full_page=False))
    except Exception:
        pass
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    manifest.append(await capture(page, screenshot_dir, "mobile-functions", full_page=False))
    try:
        await _choose_function(page, "图片转 PDF")
        await _set_files(page, ["sample-image-a.png"])
        manifest.append(await capture(page, screenshot_dir, "mobile-file-step", full_page=False))
    except Exception:
        pass
    return manifest
