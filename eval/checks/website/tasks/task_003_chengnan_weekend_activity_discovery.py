from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named, contains_texts, fill_named, reset_page, text_absent
except ImportError:
    from common import CheckRecorder, capture, click_named, contains_texts, fill_named, reset_page, text_absent


RUNTIME_KEYS = [
    "header_hero_content", "activity_list_subscription", "category_filter",
    "activity_detail_dialog", "favorite_count_linkage", "subscription_email_validation",
    "subscription_success_feedback",
]
VISUAL_KEYS = ["color_main_heading", "desktop_page_layout", "card_dialog_style"]


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def header():
        await reset_page(page)
        return await contains_texts(page, [
            "城南周末", "本周活动", "订阅清单", "已收藏 0 项", "把周末过成喜欢的样子",
            "看看本周活动", "本周六—周日 · 城南", "本周精选", "天台落日音乐会",
            "周六 18:30", "云顶剧场", "¥88",
        ])
    await recorder.check("header_hero_content", header)

    async def list_subscription():
        await reset_page(page)
        return await contains_texts(page, [
            "全部", "展览", "市集", "音乐", "亲子", "风从纸上来", "黄昏面包市集",
            "天台落日音乐会", "小小植物观察员", "旧书交换计划", "雨声与大提琴",
            "把周末清单寄给我", "每周四，一封邮件整理好城南值得去的地方。", "订阅周末清单",
        ])
    await recorder.check("activity_list_subscription", list_subscription)

    async def category_filter():
        await reset_page(page)
        await click_named(page, "音乐")
        music_only = await contains_texts(page, ["天台落日音乐会", "雨声与大提琴"]) and await text_absent(page, ["风从纸上来", "黄昏面包市集", "小小植物观察员", "旧书交换计划"])
        await click_named(page, "全部")
        return music_only and await contains_texts(page, ["风从纸上来", "黄昏面包市集", "小小植物观察员", "旧书交换计划"])
    await recorder.check("category_filter", category_filter)

    async def detail_dialog():
        await reset_page(page)
        card = page.locator("article", has_text="天台落日音乐会").last
        await card.get_by_role("button", name="查看详情").click()
        dialog = page.get_by_role("dialog")
        visible = await dialog.is_visible() and await contains_texts(dialog, ["天台落日音乐会", "音乐", "周六 18:30", "云顶剧场", "¥88", "在城南最高的天台"])
        await dialog.get_by_role("button", name="关闭详情").click()
        return visible and await page.get_by_role("dialog").count() == 0
    await recorder.check("activity_detail_dialog", detail_dialog)

    async def favorite():
        await reset_page(page)
        card = page.locator("article", has_text="风从纸上来")
        await card.get_by_role("button", name="收藏", exact=True).click()
        added = await contains_texts(page, ["已收藏 1 项"]) and await card.get_by_role("button", name="已收藏").is_visible()
        await card.get_by_role("button", name="已收藏").click()
        return added and await contains_texts(page, ["已收藏 0 项"])
    await recorder.check("favorite_count_linkage", favorite)

    async def invalid_email():
        await reset_page(page)
        await click_named(page, "订阅周末清单")
        return await contains_texts(page, ["请输入有效的邮箱地址"])
    await recorder.check("subscription_email_validation", invalid_email)

    async def valid_email():
        await reset_page(page)
        await fill_named(page, "你的邮箱地址", "weekend@example.com")
        await click_named(page, "订阅周末清单")
        return await contains_texts(page, ["已订阅，我们会在每周四发送周末清单到 weekend@example.com"])
    await recorder.check("subscription_success_feedback", valid_email)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-home")]
    card = page.locator("article", has_text="天台落日音乐会").last
    await card.get_by_role("button", name="查看详情").click()
    manifest.append(await capture(page, screenshot_dir, "activity-dialog", full_page=False))
    return manifest
