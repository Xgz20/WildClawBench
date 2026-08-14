from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named, contains_texts, fill_named, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named, contains_texts, fill_named, reset_page


RUNTIME_KEYS = [
    "header_daily_overview", "tasks_focus_tips", "timer_mode_switch", "timer_controls",
    "focus_total_persistence", "task_form_validation", "task_completion_linkage",
    "task_state_persistence", "timer_completion_feedback",
]
VISUAL_KEYS = ["color_typography", "desktop_two_column_layout", "timer_card_style"]


async def _install_clock(page):
    try:
        await page.clock.install()
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise


async def _add_task(page):
    await fill_named(page, "写下一件今天要做的事", "整理周会结论")
    await click_named(page, "添加任务")


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def header():
        await reset_page(page)
        return await contains_texts(page, [
            "一刻专注", "把这一刻，留给最重要的事", "用一段专注、一次休息，把大任务慢慢变小。",
            "今日专注", "0分钟", "完成任务", "0项", "25:00", "专注", "短休息", "长休息", "开始", "重置",
        ])
    await recorder.check("header_daily_overview", header)

    async def tasks_tips():
        await reset_page(page)
        return await contains_texts(page, [
            "今日任务", "还没有任务，先写下今天最重要的一件事。", "添加任务", "专注建议",
            "一次只做一件事", "铃响后离开座位休息", "连续完成四轮后进行长休息",
        ])
    await recorder.check("tasks_focus_tips", tasks_tips)

    async def mode_switch():
        await reset_page(page)
        for mode, expected in [("短休息", "05:00"), ("长休息", "15:00"), ("专注", "25:00")]:
            await click_named(page, mode)
            if not await contains_texts(page, [expected, "开始"]):
                return False
        return True
    await recorder.check("timer_mode_switch", mode_switch)

    async def controls():
        await reset_page(page)
        await _install_clock(page)
        await click_named(page, "开始")
        await page.clock.fast_forward("00:00:03")
        started = await contains_texts(page, ["24:57", "暂停"])
        await click_named(page, "暂停")
        paused_time = await page.locator(".ring-time").inner_text()
        await page.clock.fast_forward("00:00:03")
        stopped = paused_time == await page.locator(".ring-time").inner_text() and await contains_texts(page, ["继续"])
        await click_named(page, "继续")
        await page.clock.fast_forward("00:00:02")
        continued = paused_time != await page.locator(".ring-time").inner_text()
        await click_named(page, "重置")
        return started and stopped and continued and await contains_texts(page, ["25:00", "开始"])
    await recorder.check("timer_controls", controls)

    async def focus_persistence():
        await reset_page(page)
        await _install_clock(page)
        await click_named(page, "开始")
        await page.clock.fast_forward("00:01:01")
        focused = await contains_texts(page, ["今日专注", "1分钟"])
        await click_named(page, "短休息")
        await click_named(page, "开始")
        await page.clock.fast_forward("00:01:01")
        no_increment = await contains_texts(page, ["今日专注", "1分钟"])
        await page.reload(wait_until="domcontentloaded")
        return focused and no_increment and await contains_texts(page, ["今日专注", "1分钟"])
    await recorder.check("focus_total_persistence", focus_persistence)

    async def task_validation():
        await reset_page(page)
        await click_named(page, "添加任务")
        invalid = await contains_texts(page, ["请输入任务名称"])
        await _add_task(page)
        value = await page.get_by_placeholder("写下一件今天要做的事", exact=False).input_value()
        return invalid and value == "" and await contains_texts(page, ["整理周会结论"])
    await recorder.check("task_form_validation", task_validation)

    async def task_completion():
        await reset_page(page)
        await _add_task(page)
        await page.get_by_role("checkbox").click()
        decoration = await page.get_by_text("整理周会结论", exact=True).evaluate("el => getComputedStyle(el).textDecorationLine")
        return "line-through" in decoration and await contains_texts(page, ["完成任务", "1项"])
    await recorder.check("task_completion_linkage", task_completion)

    async def task_persistence():
        await reset_page(page)
        await _add_task(page)
        await page.get_by_role("checkbox").click()
        await page.reload(wait_until="domcontentloaded")
        return await contains_texts(page, ["整理周会结论", "完成任务", "1项"]) and await page.get_by_role("checkbox").get_attribute("aria-checked") == "true"
    await recorder.check("task_state_persistence", task_persistence)

    async def completion_feedback():
        await reset_page(page)
        await _install_clock(page)
        await click_named(page, "开始")
        await page.clock.fast_forward("00:25:01")
        return await contains_texts(page, ["00:00", "本轮专注结束，起来休息一下"])
    await recorder.check("timer_completion_feedback", completion_feedback)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    return [await capture(page, screenshot_dir, "desktop-default")]
