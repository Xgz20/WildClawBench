from __future__ import annotations

try:
    from ..common import (
        CheckRecorder, capture, click_named, contains_any_texts,
        contains_each_any_texts, contains_texts, reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, contains_any_texts,
        contains_each_any_texts, contains_texts, reset_page,
    )


RUNTIME_KEYS = [
    "c01_information_organization", "c02_information_organization",
    "c03_realtime_auto_progress", "c04_operation_feedback", "c05_operation_feedback",
    "c06_rule_settlement", "c07_rule_settlement", "c08_rule_settlement",
    "c09_rule_settlement", "c10_rule_settlement", "c11_rule_settlement",
    "c12_rule_settlement",
]
VISUAL_KEYS = ["c13_visual_style", "c14_page_layout", "c15_responsive_layout"]


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


async def _player_panel_text(page, side: str) -> str:
    labels = ["左侧玩家", "左边玩家", "玩家一"] if side == "left" else ["右侧玩家", "右边玩家", "玩家二"]
    for label in labels:
        anchors = page.get_by_text(label, exact=True)
        for index in range(await anchors.count()):
            anchor = anchors.nth(index)
            if not await anchor.is_visible():
                continue
            text = await anchor.evaluate(
                """(node) => {
                    let current = node;
                    for (let depth = 0; current && depth < 7; depth += 1) {
                        const text = current.innerText || '';
                        if (text.includes('分数') && text.includes('长度')) return text;
                        current = current.parentElement;
                    }
                    return node.parentElement?.innerText || node.innerText || '';
                }"""
            )
            return str(text or "")
    return ""


async def _player_is_out(page, side: str) -> bool:
    text = await _player_panel_text(page, side)
    return "出局" in text or "淘汰" in text or "结束" in text


async def _force_out(page, side: str, timeout_ms: int = 5000) -> bool:
    await page.keyboard.press("KeyW" if side == "left" else "ArrowUp")
    deadline = timeout_ms
    while deadline > 0:
        if await _player_is_out(page, side):
            return True
        await page.wait_for_timeout(100)
        deadline -= 100
    return False


async def _force_end(page) -> bool:
    # Drive both snakes toward a boundary and poll the actual per-player state.
    # This is independent of the board dimensions and avoids fixed-duration
    # key spam being mistaken for a completed round.
    await page.keyboard.press("KeyW")
    await page.keyboard.press("ArrowUp")
    for _ in range(60):
        left_out = await _player_is_out(page, "left")
        right_out = await _player_is_out(page, "right")
        if left_out and right_out:
            return True
        await page.wait_for_timeout(100)
    left_out = await _player_is_out(page, "left") or await _force_out(page, "left")
    right_out = await _player_is_out(page, "right") or await _force_out(page, "right")
    return left_out and right_out


async def _force_left_out_while_right_continues(page, timeout_ms: int = 3000) -> bool:
    await page.keyboard.press("KeyW")
    right_turns = ("ArrowUp", "ArrowRight", "ArrowDown", "ArrowLeft")
    elapsed = 0
    turn_index = 0
    while elapsed < timeout_ms:
        if await _player_is_out(page, "left"):
            return not await _player_is_out(page, "right")
        if elapsed % 300 == 0:
            await page.keyboard.press(right_turns[turn_index % len(right_turns)])
            turn_index += 1
        await page.wait_for_timeout(100)
        elapsed += 100
    return False


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def basic():
        await reset_page(page)
        return (
            await contains_texts(page, ["霓虹贪吃蛇", "W", "A", "S", "D", "开始游戏"])
            and await contains_each_any_texts(
                page, [["上", "↑"], ["下", "↓"], ["左", "←"], ["右", "→"]]
            )
        )
    await recorder.check("c01_information_organization", basic)

    async def preparation_and_start():
        await reset_page(page)
        before = await _board_count(page) == 0
        started = await _start_game(page)
        return (
            before
            and started
            and await _board_count(page) >= 2
            and await contains_texts(page, ["左", "右", "分数", "长度", "胜率"])
            and await contains_any_texts(page, ["胜场", "玩家胜"])
        )
    await recorder.check("c02_information_organization", preparation_and_start)

    async def both_running():
        if not await _start_game(page):
            return False
        await page.wait_for_timeout(500)
        return (
            await page.get_by_text("能量果", exact=True).count() >= 2
            and await page.get_by_text("爆炸果", exact=True).count() >= 2
            and await contains_any_texts(page, ["进行中", "游戏中", "前进中"])
        )
    await recorder.check("c03_realtime_auto_progress", both_running)

    async def left_controls():
        if not await _start_game(page):
            return False
        await page.keyboard.press("KeyW")
        await page.wait_for_timeout(120)
        return await contains_texts(page, ["左", "W"]) and not await contains_texts(page, ["右侧已出局"])
    await recorder.check("c04_operation_feedback", left_controls)

    async def right_controls():
        if not await _start_game(page):
            return False
        await page.keyboard.press("ArrowUp")
        await page.wait_for_timeout(120)
        return await contains_texts(page, ["右", "上"]) and not await contains_texts(page, ["左侧已出局"])
    await recorder.check("c05_operation_feedback", right_controls)

    async def no_reverse():
        if not await _start_game(page):
            return False
        await page.keyboard.press("ArrowLeft")
        await page.wait_for_timeout(150)
        return await contains_any_texts(page, ["进行中", "游戏中"]) and not await contains_texts(page, ["立即出局"])
    await recorder.check("c06_rule_settlement", no_reverse)

    async def energy_feedback():
        if not await _start_game(page):
            return False
        before = await page.locator("body").inner_text()
        for key in ("KeyD", "KeyW", "ArrowUp", "ArrowRight"):
            await page.keyboard.press(key)
            await page.wait_for_timeout(150)
        after = await page.locator("body").inner_text()
        return "能量果" in before and "能量果" in after and any(token in after for token in ("分数 1", "+1", "得分"))
    await recorder.check("c07_rule_settlement", energy_feedback)

    async def explosion_feedback():
        if not await _start_game(page):
            return False
        has_explosion = await contains_texts(page, ["爆炸果"])
        await page.keyboard.press("KeyD")
        await page.wait_for_timeout(200)
        return has_explosion and await contains_texts(page, ["出局", "爆炸果"])
    await recorder.check("c08_rule_settlement", explosion_feedback)

    async def one_side_continues():
        if not await _start_game(page):
            return False
        if not await _force_left_out_while_right_continues(page):
            return False
        return (
            await _player_is_out(page, "left")
            and not await _player_is_out(page, "right")
            and await contains_any_texts(page, ["等待", "另一方", "继续"])
        )
    await recorder.check("c09_rule_settlement", one_side_continues)

    async def result_modal():
        if not await _start_game(page):
            return False
        if not await _force_end(page):
            return False
        return (
            await contains_texts(page, ["存活时间", "再来一局"])
            and await contains_any_texts(page, ["得分", "分数"])
            and await contains_any_texts(page, ["获胜", "平局"])
        )
    await recorder.check("c10_rule_settlement", result_modal)

    async def survival_tiebreak():
        if not await _start_game(page):
            return False
        if not await _force_left_out_while_right_continues(page):
            return False
        await page.wait_for_timeout(300)
        if not await _force_out(page, "right", timeout_ms=3000):
            return False
        text = await page.locator("body").inner_text()
        return "存活时间" in text and "右" in text and "获胜" in text
    await recorder.check("c11_rule_settlement", survival_tiebreak)

    async def replay():
        if not await _start_game(page):
            return False
        if not await _force_end(page):
            return False
        try:
            await click_named(page, "再来一局")
        except Exception:
            return False
        return await _board_count(page) >= 2 and await contains_texts(page, ["分数", "长度", "0"]) and await contains_any_texts(
            page, ["进行中", "游戏中", "前进中"]
        )
    await recorder.check("c12_rule_settlement", replay)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    if not await _start_game(page):
        await reset_page(page)
    return [await capture(page, screenshot_dir, "desktop-game", full_page=False)]
