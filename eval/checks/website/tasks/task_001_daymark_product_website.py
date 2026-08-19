from __future__ import annotations

try:
    from ..common import (
        CheckRecorder, capture, click_named, click_named_any, contains_texts,
        fill_named, reset_page, text_absent,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, click_named_any, contains_texts,
        fill_named, reset_page, text_absent,
    )


RUNTIME_KEYS = [
    "c01_information_organization", "c02_information_organization",
    "c03_information_organization", "c04_page_navigation", "c05_content_switching",
    "c06_content_switching", "c07_form_validation", "c08_form_validation",
]
VISUAL_KEYS = [
    "c09_visual_style", "c10_page_layout", "c11_component_style",
    "c12_responsive_layout",
]


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def hero_content():
        await reset_page(page)
        return await contains_texts(page, [
            "昼航 Daymark", "开完会，事情就该向前走", "免费试用 14 天",
            "查看工作流", "无需信用卡 · 5 分钟完成设置",
            "昼航把议题、决定和负责人放进同一条时间线，让每一次讨论都有清楚的下文。",
        ])
    await recorder.check("c01_information_organization", hero_content)

    async def timeline_and_results():
        await reset_page(page)
        return await contains_texts(page, [
            "周一产品例会", "决定", "负责人", "下一步",
            "42%", "跟进消息减少", "3.2 小时", "每人每周节省", "96%", "决定都有负责人",
        ])
    await recorder.check("c02_information_organization", timeline_and_results)

    async def workflow():
        await reset_page(page)
        return await contains_texts(page, [
            "从议题到行动，只走三步", "会前收拢议题", "会中锁定决定", "会后推动行动",
            "合并重复", "记录结论", "负责人", "截止时间", "追踪行动",
        ])
    await recorder.check("c03_information_organization", workflow)

    async def navigation():
        await reset_page(page)
        targets = [
            ("工作流", "从议题到行动，只走三步"),
            ("定价", "轻帆"),
            ("常见问题", "可以导入已有会议记录吗？"),
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
    await recorder.check("c04_page_navigation", navigation)

    async def pricing_switch():
        await reset_page(page)
        monthly = await contains_texts(page, ["¥39", "¥89"])
        await click_named_any(page, ["按年", "切换按年付费", "按年付费"])
        yearly = await contains_texts(page, ["¥31", "¥71", "按年付费，约省 20%"])
        await click_named_any(page, ["按月", "切换按月付费", "切换按年付费", "按月付费"])
        restored = await contains_texts(page, ["¥39", "¥89"])
        return monthly and yearly and restored
    await recorder.check("c05_content_switching", pricing_switch)

    async def faq_accordion():
        await reset_page(page)
        first = page.get_by_role("button", name="可以导入已有会议记录吗？")
        second = page.get_by_role("button", name="没有管理员也能开始吗？")
        first_answer = "可以，支持粘贴文本或导入 Markdown，原有标题和待办会被保留。"
        second_answer = "可以，任何成员都能创建第一个工作区，之后再邀请同事加入。"
        initial_closed = await text_absent(page, [first_answer, second_answer])
        await first.click()
        first_open = await contains_texts(page, [first_answer])
        await second.click()
        return (
            initial_closed
            and first_open
            and await text_absent(page, [first_answer])
            and await contains_texts(page, [second_answer])
        )
    await recorder.check("c06_content_switching", faq_accordion)

    async def trial_validation():
        await reset_page(page)
        await click_named(page, "免费试用 14 天")
        await click_named(page, "提交申请")
        return await contains_texts(page, ["请输入姓名", "请输入有效的工作邮箱"])
    await recorder.check("c07_form_validation", trial_validation)

    async def trial_success():
        await reset_page(page)
        await click_named(page, "免费试用 14 天")
        await fill_named(page, "姓名", "林晓")
        await fill_named(page, "工作邮箱", "linxiao@example.com")
        await click_named(page, "提交申请")
        success = await contains_texts(page, ["申请已收到", "linxiao@example.com"])
        await click_named(page, "关闭")
        return success and await page.get_by_role("dialog").count() == 0
    await recorder.check("c08_form_validation", trial_success)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-home")]
    try:
        await click_named(page, "常见问题")
        manifest.append(await capture(page, screenshot_dir, "faq-section", full_page=False))
    except Exception:
        pass
    return manifest
