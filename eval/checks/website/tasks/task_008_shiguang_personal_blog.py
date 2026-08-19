from __future__ import annotations

try:
    from ..common import (
        CheckRecorder, capture, click_named, contains_any_texts,
        contains_each_any_texts, contains_texts, fill_any_named,
        fill_named, reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, contains_any_texts,
        contains_each_any_texts, contains_texts, fill_any_named,
        fill_named, reset_page,
    )


RUNTIME_KEYS = [
    "c01_information_organization", "c02_lists_tables", "c03_information_organization",
    "c04_search_filtering", "c05_search_filtering", "c06_search_filtering",
    "c07_search_filtering", "c08_page_navigation", "c09_content_editing",
    "c10_content_editing", "c11_content_editing", "c12_content_editing",
    "c13_form_validation", "c14_content_editing", "c15_content_editing",
    "c16_popup_overlay", "c17_content_editing", "c18_state_persistence",
    "c19_search_filtering", "c23_page_navigation",
]
VISUAL_KEYS = ["c20_page_layout", "c21_visual_style", "c22_responsive_layout"]


async def _search(page, value: str) -> bool:
    for name in ("搜索文章", "搜索", "输入关键词", "搜索标题、摘要或标签"):
        try:
            await fill_named(page, name, value)
            return True
        except Exception:
            continue
    return False


async def _clear(page) -> bool:
    for label in ("清除筛选", "清除", "重置筛选", "查看全部"):
        try:
            await click_named(page, label)
            return True
        except Exception:
            continue
    return False


async def _article_count(page) -> int:
    article_count = await page.locator("article").count()
    entry_count = 0
    for label in ("阅读全文", "查看全文"):
        entry_count += await page.get_by_text(label, exact=True).count()
    return max(article_count, entry_count)


async def _select_category(page, value: str) -> bool:
    selects = page.locator("select")
    for index in range(await selects.count()):
        select = selects.nth(index)
        options = [item.strip() for item in await select.locator("option").all_text_contents()]
        if value in options:
            await select.select_option(label=value)
            return True
    try:
        await click_named(page, value)
        return True
    except AssertionError:
        return False


async def _open_first_article(page) -> bool:
    for label in ("阅读全文", "查看全文"):
        try:
            await click_named(page, label)
            return True
        except Exception:
            continue
    cards = page.locator("article")
    if await cards.count():
        try:
            await cards.first.click()
            return await contains_any_texts(page, ["返回文章列表", "返回文章"])
        except Exception:
            pass
    return False


async def _editor_body(page):
    for selector in ("[contenteditable='true']", "textarea"):
        locator = page.locator(selector)
        if await locator.count():
            return locator.last
    return None


async def _fill_editor(page, title: str = "雨后的城市", body: str = "今天沿着河边散步，留下了一段值得记住的文字。") -> bool:
    try:
        await fill_any_named(page, ["标题", "文章标题"], title)
        await fill_any_named(page, ["摘要", "文章摘要"], "一段关于生活和城市的记录")
        await fill_any_named(page, ["标签", "文章标签"], "城市,散步")
    except Exception:
        return False
    editor = await _editor_body(page)
    if editor is None:
        return False
    await editor.fill(body)
    return True


async def _save_editor(page) -> bool:
    for label in ("保存文章", "发布文章", "保存"):
        try:
            await click_named(page, label)
            return True
        except Exception:
            continue
    return False


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def basic():
        await reset_page(page)
        return await contains_texts(page, ["拾光札记", "文章", "关于作者", "写一篇", "把日子写成自己的风景", "记录阅读、散步与工作里那些值得留下的片段。"])
    await recorder.check("c01_information_organization", basic)

    async def seeded_articles():
        await reset_page(page)
        return await _article_count(page) >= 3 and await contains_texts(
            page, ["生活", "阅读", "城市", "阅读全文", "标签"]
        ) and await contains_any_texts(page, ["分钟", "阅读时长"])
    await recorder.check("c02_lists_tables", seeded_articles)

    async def author_footer():
        await reset_page(page)
        return await contains_texts(
            page, ["关于作者", "一个记录日常、阅读和城市漫游的个人角落。"]
        ) and await contains_any_texts(page, ["©", "版权", "版权所有", "Copyright"])
    await recorder.check("c03_information_organization", author_footer)

    async def search():
        await reset_page(page)
        before = await _article_count(page)
        ok = await _search(page, "散步")
        after = await _article_count(page)
        return ok and before >= 3 and after >= 1 and after < before and await contains_texts(page, ["散步"])
    await recorder.check("c04_search_filtering", search)

    async def category():
        await reset_page(page)
        before = await _article_count(page)
        if not await _select_category(page, "阅读"):
            return False
        filtered = await _article_count(page)
        if not await _select_category(page, "全部"):
            return False
        return filtered >= 1 and filtered < before and await _article_count(page) == before
    await recorder.check("c05_search_filtering", category)

    async def combined_filter():
        await reset_page(page)
        ok = await _search(page, "城市")
        try:
            selected = await _select_category(page, "城市")
        except Exception:
            return False
        return ok and selected and await _article_count(page) >= 1 and await contains_texts(page, ["城市"])
    await recorder.check("c06_search_filtering", combined_filter)

    async def empty_and_clear():
        await reset_page(page)
        if not await _search(page, "不存在的文章关键词"):
            return False
        empty = await contains_any_texts(page, ["没有找到", "暂无匹配", "没有匹配"]) and await contains_texts(page, ["清除"])
        cleared = await _clear(page)
        return empty and cleared and await _article_count(page) >= 3
    await recorder.check("c07_search_filtering", empty_and_clear)

    async def detail():
        await reset_page(page)
        if not await _open_first_article(page):
            return False
        return (
            await contains_texts(page, ["返回文章", "编辑文章", "删除文章"])
            and await contains_any_texts(page, ["分钟", "阅读时长"])
            and await page.locator("article h1, article h2, article h3, .detail-card h2").count() > 0
            and await page.locator("article p, article blockquote, article li, .prose").count() > 0
        )
    await recorder.check("c08_page_navigation", detail)

    async def editor():
        await reset_page(page)
        await click_named(page, "写一篇")
        return await contains_texts(page, ["标题", "分类", "摘要", "标签", "发布日期", "正文", "加粗", "下划线", "引用", "列表"])
    await recorder.check("c09_content_editing", editor)

    async def inline_format():
        await reset_page(page)
        await click_named(page, "写一篇")
        body = await _editor_body(page)
        if body is None:
            return False
        await body.fill("格式化文字")
        await body.press("ControlOrMeta+A")
        try:
            await click_named(page, "加粗")
            await click_named(page, "下划线")
        except Exception:
            return False
        return await page.locator("strong, b, u").count() > 0
    await recorder.check("c10_content_editing", inline_format)

    async def block_format():
        await reset_page(page)
        await click_named(page, "写一篇")
        body = await _editor_body(page)
        if body is None:
            return False
        for label in ("标题", "引用", "无序列表", "列表"):
            try:
                await click_named(page, label)
            except Exception:
                continue
        return await page.locator("h1, h2, h3, blockquote, ul").count() > 0 or await contains_texts(page, ["标题", "引用"])
    await recorder.check("c11_content_editing", block_format)

    async def markdown_shortcuts():
        await reset_page(page)
        await click_named(page, "写一篇")
        body = await _editor_body(page)
        if body is None:
            return False
        await body.fill("# ")
        await body.press("End")
        await body.type("标题段落")
        text = await body.inner_text() if await body.get_attribute("contenteditable") == "true" else await body.input_value()
        return "标题段落" in text and "# " not in text
    await recorder.check("c12_content_editing", markdown_shortcuts)

    async def empty_validation():
        await reset_page(page)
        await click_named(page, "写一篇")
        await _save_editor(page)
        return await contains_each_any_texts(
            page,
            [
                ["请输入标题", "标题不能为空", "标题必填"],
                ["请输入正文", "正文不能为空", "正文必填"],
            ],
        )
    await recorder.check("c13_form_validation", empty_validation)

    async def create_article():
        await reset_page(page)
        await click_named(page, "写一篇")
        if not await _fill_editor(page):
            return False
        if not await _save_editor(page):
            return False
        return await contains_texts(page, ["雨后的城市", "一段关于生活和城市的记录"])
    await recorder.check("c14_content_editing", create_article)

    async def edit_article():
        await reset_page(page)
        await click_named(page, "写一篇")
        if not await _fill_editor(page, "待修改文章", "原始内容") or not await _save_editor(page):
            return False
        if not await _open_first_article(page):
            return False
        try:
            await click_named(page, "编辑文章")
            await fill_any_named(page, ["标题", "文章标题"], "修改后的文章")
            await _save_editor(page)
        except Exception:
            return False
        return await contains_texts(page, ["修改后的文章"])
    await recorder.check("c15_content_editing", edit_article)

    async def delete_cancel():
        await reset_page(page)
        if not await _open_first_article(page):
            return False
        await click_named(page, "删除文章")
        dialog = await contains_texts(page, ["确认删除", "取消"])
        try:
            await click_named(page, "取消")
        except Exception:
            return False
        return dialog and await contains_texts(page, ["编辑文章", "删除文章"])
    await recorder.check("c16_popup_overlay", delete_cancel)

    async def delete_confirm():
        await reset_page(page)
        await click_named(page, "写一篇")
        if not await _fill_editor(page, "待删除文章", "删除测试") or not await _save_editor(page):
            return False
        if not await _open_first_article(page):
            return False
        try:
            await click_named(page, "删除文章")
            await click_named(page, "确认删除")
        except Exception:
            return False
        return not await page.get_by_text("待删除文章", exact=True).count()
    await recorder.check("c17_content_editing", delete_confirm)

    async def persistence():
        await reset_page(page)
        await click_named(page, "写一篇")
        if not await _fill_editor(page, "持久化文章", "保存后的正文") or not await _save_editor(page):
            return False
        await page.reload(wait_until="domcontentloaded")
        return await contains_texts(page, ["持久化文章"])
    await recorder.check("c18_state_persistence", persistence)

    async def tag_filter():
        await reset_page(page)
        try:
            await click_named(page, "生活方式")
        except Exception:
            return False
        filtered = await page.locator("article").count()
        cleared = await _clear(page)
        return filtered >= 1 and cleared and await page.locator("article").count() >= filtered
    await recorder.check("c19_search_filtering", tag_filter)

    async def navigation():
        await reset_page(page)
        await click_named(page, "文章")
        article_anchor = await page.locator("article").first.is_visible() if await page.locator("article").count() else False
        await click_named(page, "关于作者")
        author = await contains_texts(page, ["一个记录日常、阅读和城市漫游的个人角落。"])
        return article_anchor and author
    await recorder.check("c23_page_navigation", navigation)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-home")]
    try:
        await click_named(page, "写一篇")
        manifest.append(await capture(page, screenshot_dir, "editor", full_page=False))
    except Exception:
        pass
    await page.set_viewport_size({"width": 375, "height": 812})
    await reset_page(page, clear_storage=False)
    manifest.append(await capture(page, screenshot_dir, "mobile-home", full_page=False))
    try:
        await click_named(page, "写一篇")
        manifest.append(await capture(page, screenshot_dir, "mobile-editor", full_page=False))
    except Exception:
        pass
    return manifest
