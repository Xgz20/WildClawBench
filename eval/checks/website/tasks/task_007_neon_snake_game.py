from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named, contains_texts, reset_page


RUNTIME_KEYS = [
    "criterion_01_basic_content", "criterion_02_information_organization",
    "criterion_03_operation_feedback", "criterion_04_cross_section_coordination",
    "criterion_05_cross_section_coordination", "criterion_06_operation_feedback",
    "criterion_07_operation_feedback", "criterion_08_operation_feedback",
    "criterion_09_operation_feedback", "criterion_10_modal_and_overlay",
    "criterion_11_operation_feedback", "criterion_12_content_switching",
]
VISUAL_KEYS = ["criterion_13_visual_style", "criterion_14_page_layout"]


async def _start_game(page) -> bool:
    await reset_page(page)
    try:
        await click_named(page, "开始游戏")
    except Exception:
        return False
    await page.wait_for_timeout(250)
    return True


async def _board_count(page) -> int:
    count = await page.locator("canvas").count()
    if count >= 2:
        return count
    for selector in ("[data-player]", "[data-board]", "[aria-label*='棋盘']"):
        count = await page.locator(selector).count()
        if count >= 2:
            return count
    return 0


async def _force_end(page) -> None:
    # Keep the interaction deterministic without depending on a particular
    # board implementation: repeated edge turns eventually end both snakes.
    for _ in range(18):
        await page.keyboard.press("ArrowLeft")
        await page.keyboard.press("KeyA")
        await page.wait_for_timeout(80)


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def basic():
        await reset_page(page)
        return await contains_texts(page, ["霓虹贪吃蛇", "W", "A", "S", "D", "上", "下", "左", "右", "开始游戏"])
    await recorder.check("criterion_01_basic_content", basic)

    async def preparation_and_start():
        await reset_page(page)
        before = await _board_count(page) == 0
        started = await _start_game(page)
        return before and started and await _board_count(page) >= 2 and await contains_texts(page, ["分数", "长度", "胜场", "胜率"])
    await recorder.check("criterion_02_information_organization", preparation_and_start)

    async def both_running():
        if not await _start_game(page):
            return False
        await page.wait_for_timeout(500)
        return await contains_texts(page, ["能量果", "爆炸果"]) and await contains_texts(page, ["进行中", "游戏中"])
    await recorder.check("criterion_03_operation_feedback", both_running)

    async def left_controls():
        if not await _start_game(page):
            return False
        await page.keyboard.press("KeyW")
        await page.wait_for_timeout(120)
        return await contains_texts(page, ["左", "W"]) and not await contains_texts(page, ["右侧已出局"])
    await recorder.check("criterion_04_cross_section_coordination", left_controls)

    async def right_controls():
        if not await _start_game(page):
            return False
        await page.keyboard.press("ArrowUp")
        await page.wait_for_timeout(120)
        return await contains_texts(page, ["右", "上"]) and not await contains_texts(page, ["左侧已出局"])
    await recorder.check("criterion_05_cross_section_coordination", right_controls)

    async def no_reverse():
        if not await _start_game(page):
            return False
        await page.keyboard.press("ArrowLeft")
        await page.wait_for_timeout(150)
        return await contains_texts(page, ["进行中", "游戏中"]) and not await contains_texts(page, ["立即出局"])
    await recorder.check("criterion_06_operation_feedback", no_reverse)

    async def energy_feedback():
        if not await _start_game(page):
            return False
        before = await page.locator("body").inner_text()
        for key in ("KeyD", "KeyW", "ArrowUp", "ArrowRight"):
            await page.keyboard.press(key)
            await page.wait_for_timeout(150)
        after = await page.locator("body").inner_text()
        return "能量果" in before and "能量果" in after and any(token in after for token in ("分数 1", "+1", "得分"))
    await recorder.check("criterion_07_operation_feedback", energy_feedback)

    async def explosion_feedback():
        if not await _start_game(page):
            return False
        has_explosion = await contains_texts(page, ["爆炸果"])
        await page.keyboard.press("KeyD")
        await page.wait_for_timeout(200)
        return has_explosion and await contains_texts(page, ["出局", "爆炸果"])
    await recorder.check("criterion_08_operation_feedback", explosion_feedback)

    async def one_side_continues():
        if not await _start_game(page):
            return False
        await page.keyboard.press("KeyA")
        await page.wait_for_timeout(250)
        return await contains_texts(page, ["出局", "等待", "另一方", "进行中", "游戏中"])
    await recorder.check("criterion_09_operation_feedback", one_side_continues)

    async def result_modal():
        if not await _start_game(page):
            return False
        await _force_end(page)
        return await contains_texts(page, ["得分", "存活时间"]) and await contains_texts(page, ["再来一局", "获胜", "平局"])
    await recorder.check("criterion_10_modal_and_overlay", result_modal)

    async def survival_tiebreak():
        if not await _start_game(page):
            return False
        await _force_end(page)
        text = await page.locator("body").inner_text()
        return ("存活时间" in text and ("获胜" in text or "平局" in text))
    await recorder.check("criterion_11_operation_feedback", survival_tiebreak)

    async def replay():
        if not await _start_game(page):
            return False
        await _force_end(page)
        try:
            await click_named(page, "再来一局")
        except Exception:
            return False
        return await _board_count(page) >= 2 and await contains_texts(page, ["分数", "长度", "进行中", "游戏中"])
    await recorder.check("criterion_12_content_switching", replay)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    if not await _start_game(page):
        await reset_page(page)
    return [await capture(page, screenshot_dir, "desktop-game", full_page=False)]
