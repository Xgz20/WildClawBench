from __future__ import annotations

import re

try:
    from ..common import (
        CheckRecorder, capture, click_named, contains_texts, fill_any_named,
        reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, contains_texts, fill_any_named,
        reset_page,
    )


RUNTIME_KEYS = [
    "c01_information_organization", "c02_content_switching",
    "c03_realtime_auto_progress", "c04_rule_settlement", "c05_form_validation",
    "c06_operation_feedback", "c07_state_persistence", "c08_realtime_auto_progress",
]
VISUAL_KEYS = [
    "c09_visual_style", "c10_page_layout", "c11_component_style",
    "c12_responsive_layout",
]


async def _install_clock(page):
    try:
        await page.clock.install()
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise


async def _add_task(page):
    await fill_any_named(
        page,
        ["任务名称", "写下一件今天要做的事", "写下今天最重要的一件事"],
        "整理周会结论",
    )
    await click_named(page, "添加任务")


async def _task_input(page):
    for name in ("任务名称", "写下一件今天要做的事", "写下今天最重要的一件事"):
        for getter in (page.get_by_label, page.get_by_placeholder):
            locator = getter(name, exact=False)
            if await locator.count():
                return locator.first
    raise AssertionError("task name field not found")


async def _task_completion_control(page):
    checkboxes = page.get_by_role("checkbox")
    if await checkboxes.count():
        return checkboxes.first
    buttons = page.get_by_role(
        "button",
        name=re.compile(r"标记.*整理周会结论.*(完成|未完成)|整理周会结论.*完成"),
    )
    if await buttons.count():
        return buttons.first
    raise AssertionError("task completion control not found")


async def _read_timer_text(page) -> str:
    timers = page.get_by_text(re.compile(r"^\s*\d{2}:\d{2}\s*$"))
    for index in range(await timers.count()):
        timer = timers.nth(index)
        if await timer.is_visible():
            return (await timer.inner_text()).strip()
    raise AssertionError("visible timer text not found")


async def _is_checked(control) -> bool:
    try:
        return await control.is_checked()
    except Exception:
        aria_checked = await control.get_attribute("aria-checked")
        aria_pressed = await control.get_attribute("aria-pressed")
        data_state = await control.get_attribute("data-state")
        return (
            aria_checked == "true"
            or aria_pressed == "true"
            or data_state == "checked"
        )


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def header():
        await reset_page(page)
        return await contains_texts(page, [
            "一刻专注", "把这一刻，留给最重要的事", "用一段专注、一次休息，把大任务慢慢变小。",
            "今日专注", "0分钟", "完成任务", "0项", "25:00", "专注", "短休息", "长休息", "开始", "重置",
            "今日任务", "还没有任务，先写下今天最重要的一件事。", "添加任务", "专注建议",
            "一次只做一件事", "铃响后离开座位休息", "连续完成四轮后进行长休息",
        ])
    await recorder.check("c01_information_organization", header)

    async def mode_switch():
        await reset_page(page)
        await _install_clock(page)
        await click_named(page, "专注")
        await click_named(page, "开始")
        await page.clock.run_for(2000)
        if await _read_timer_text(page) == "25:00":
            return False
        for mode, expected in [("短休息", "05:00"), ("长休息", "15:00"), ("专注", "25:00")]:
            await click_named(page, mode)
            if not await contains_texts(page, [expected, "开始"]):
                return False
        return True
    await recorder.check("c02_content_switching", mode_switch)

    async def controls():
        await reset_page(page)
        await _install_clock(page)
        await click_named(page, "开始")
        await page.clock.run_for(3000)
        started = await contains_texts(page, ["24:57", "暂停"])
        await click_named(page, "暂停")
        paused_time = await _read_timer_text(page)
        await page.clock.run_for(3000)
        stopped = paused_time == await _read_timer_text(page) and await contains_texts(page, ["继续"])
        await click_named(page, "继续")
        await page.clock.run_for(2000)
        continued_time = await _read_timer_text(page)
        continued = paused_time != continued_time
        await click_named(page, "重置")
        reset = await contains_texts(page, ["25:00", "开始"])
        if not (started and stopped and continued and reset):
            raise AssertionError(
                "timer state mismatch: "
                f"started={started}, paused_time={paused_time}, stopped={stopped}, "
                f"continued_time={continued_time}, continued={continued}, reset={reset}"
            )
        return True
    await recorder.check("c03_realtime_auto_progress", controls)

    async def focus_persistence():
        await reset_page(page)
        await _install_clock(page)
        await click_named(page, "开始")
        await page.clock.run_for(1501000)
        focused = await contains_texts(page, ["今日专注", "25分钟"])
        await click_named(page, "短休息")
        await click_named(page, "开始")
        await page.clock.run_for(301000)
        no_increment = await contains_texts(page, ["今日专注", "25分钟"])
        await page.reload(wait_until="domcontentloaded")
        return focused and no_increment and await contains_texts(page, ["今日专注", "25分钟"])
    await recorder.check("c04_rule_settlement", focus_persistence)

    async def task_validation():
        await reset_page(page)
        await click_named(page, "添加任务")
        invalid = await contains_texts(page, ["请输入任务名称"])
        await _add_task(page)
        value = await (await _task_input(page)).input_value()
        return invalid and value == "" and await contains_texts(page, ["整理周会结论"])
    await recorder.check("c05_form_validation", task_validation)

    async def task_completion():
        await reset_page(page)
        await _add_task(page)
        await (await _task_completion_control(page)).click()
        decoration = await page.get_by_text("整理周会结论", exact=True).evaluate("el => getComputedStyle(el).textDecorationLine")
        return "line-through" in decoration and await contains_texts(page, ["完成任务", "1项"])
    await recorder.check("c06_operation_feedback", task_completion)

    async def task_persistence():
        await reset_page(page)
        await _add_task(page)
        await (await _task_completion_control(page)).click()
        await page.reload(wait_until="domcontentloaded")
        checkbox = await _task_completion_control(page)
        return (
            await contains_texts(page, ["整理周会结论", "完成任务", "1项"])
            and await _is_checked(checkbox)
        )
    await recorder.check("c07_state_persistence", task_persistence)

    async def completion_feedback():
        await reset_page(page)
        await _install_clock(page)
        await click_named(page, "开始")
        await page.clock.run_for(1501000)
        return await contains_texts(page, ["00:00", "本轮专注结束，起来休息一下"])
    await recorder.check("c08_realtime_auto_progress", completion_feedback)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    return [await capture(page, screenshot_dir, "desktop-default")]
