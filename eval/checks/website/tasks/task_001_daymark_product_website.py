from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named, contains_texts, fill_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named, contains_texts, fill_named, reset_page


RUNTIME_KEYS = [
    "hero_content", "workflow_pricing_faq", "in_page_navigation", "pricing_switch",
    "faq_accordion", "trial_form_validation", "trial_success_feedback",
]
VISUAL_KEYS = ["color_typography", "desktop_hero_layout", "timeline_card_style"]


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def hero_content():
        await reset_page(page)
        return await contains_texts(page, [
            "昼航 Daymark", "开完会，事情就该向前走", "免费试用 14 天",
            "查看工作流", "无需信用卡 · 5 分钟完成设置", "周一产品例会",
            "42%", "跟进消息减少", "3.2 小时", "每人每周节省", "96%", "决定都有负责人",
        ])
    await recorder.check("hero_content", hero_content)

    async def workflow_pricing_faq():
        await reset_page(page)
        return await contains_texts(page, [
            "从议题到行动，只走三步", "会前收拢议题", "会中锁定决定", "会后推动行动",
            "轻帆", "¥39", "协作舱", "¥89", "可以导入已有会议记录吗？",
            "没有管理员也能开始吗？", "数据会被用于训练模型吗？",
        ])
    await recorder.check("workflow_pricing_faq", workflow_pricing_faq)

    async def navigation():
        await reset_page(page)
        targets = [
            ("工作流", "从议题到行动，只走三步"),
            ("定价", "按团队规模，透明付费"),
            ("常见问题", "你可能想知道的"),
        ]
        for control, heading in targets:
            await click_named(page, control)
            locator = page.get_by_text(heading, exact=True)
            await locator.scroll_into_view_if_needed()
            if not await locator.is_visible():
                return False
            box = await locator.bounding_box()
            if not box or box["y"] < 0 or box["y"] >= 900:
                return False
        return True
    await recorder.check("in_page_navigation", navigation)

    async def pricing_switch():
        await reset_page(page)
        monthly = await contains_texts(page, ["¥39", "¥89"])
        await click_named(page, "切换按年付费")
        yearly = await contains_texts(page, ["¥31", "¥71", "按年付费，约省 20%"])
        await click_named(page, "切换按年付费")
        restored = await contains_texts(page, ["¥39", "¥89"])
        return monthly and yearly and restored
    await recorder.check("pricing_switch", pricing_switch)

    async def faq_accordion():
        await reset_page(page)
        first = page.get_by_role("button", name="可以导入已有会议记录吗？")
        second = page.get_by_role("button", name="没有管理员也能开始吗？")
        initial_closed = (
            await first.get_attribute("aria-expanded") == "false"
            and await second.get_attribute("aria-expanded") == "false"
        )
        await first.click()
        first_open = await first.get_attribute("aria-expanded") == "true"
        await second.click()
        return initial_closed and first_open and await first.get_attribute("aria-expanded") == "false" and await second.get_attribute("aria-expanded") == "true"
    await recorder.check("faq_accordion", faq_accordion)

    async def trial_validation():
        await reset_page(page)
        await click_named(page, "免费试用 14 天")
        await click_named(page, "提交申请")
        return await contains_texts(page, ["请输入姓名", "请输入有效的工作邮箱"])
    await recorder.check("trial_form_validation", trial_validation)

    async def trial_success():
        await reset_page(page)
        await click_named(page, "免费试用 14 天")
        await fill_named(page, "姓名", "周予安")
        await fill_named(page, "工作邮箱", "zhou@example.com")
        await click_named(page, "提交申请")
        success = await contains_texts(page, ["申请已收到", "zhou@example.com"])
        await click_named(page, "关闭")
        return success and await page.get_by_role("dialog").count() == 0
    await recorder.check("trial_success_feedback", trial_success)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-home")]
    await click_named(page, "常见问题")
    manifest.append(await capture(page, screenshot_dir, "faq-section", full_page=False))
    return manifest
