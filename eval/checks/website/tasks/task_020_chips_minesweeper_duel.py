from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_rule_settlement", "c03_information_organization",
    "c04_rule_settlement", "c05_rule_settlement", "c06_operation_feedback",
    "c07_rule_settlement", "c08_rule_settlement", "c09_rule_settlement",
]
VISUAL_KEYS = ["c10_visual_style", "c11_visual_style", "c12_page_layout", "c13_responsive_layout"]


def _board(page, name):
    return page.locator("article, section, [class*='board']").filter(has_text=name).first


async def _chips(page, name):
    board = _board(page, name)
    buttons = board.locator("button")
    if await buttons.count() < 9:
        raise AssertionError(f"{name} 没有九片可操作薯片")
    return buttons


async def _prepare_play(page):
    await reset_page(page)
    p2 = await _chips(page, "玩家二")
    for i in (0, 1, 2): await p2.nth(i).click()
    await click_named_any(page, ["藏好了", "换玩家二藏雷", "下一步"])
    p1 = await _chips(page, "玩家一")
    for i in (0, 1, 2): await p1.nth(i).click()
    await click_named_any(page, ["藏好了，去掷骰子", "藏好了", "下一步"])
    await click_named_any(page, ["掷骰子", "掷骰"])
    body = await page.locator("body").inner_text()
    current = "玩家一" if "轮到玩家一" in body else "玩家二"
    return current, "玩家二" if current == "玩家一" else "玩家一"


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def initial():
        await reset_page(page)
        p1, p2 = await _chips(page, "玩家一"), await _chips(page, "玩家二")
        return await p1.count() == 9 and await p2.count() == 9 and await contains_texts(page, ["玩家一", "玩家二", "3/3", "藏雷", "轮到"])
    await r.check("c01_information_organization", initial)

    async def mine_limit():
        await reset_page(page); chips = await _chips(page, "玩家二")
        for i in range(4): await chips.nth(i).click()
        return await page.get_by_text("已藏雷", exact=True).count() == 3 and await contains_texts(page, ["3/3"])
    await r.check("c02_rule_settlement", mine_limit)

    async def hidden_mines():
        await _prepare_play(page)
        p1, p2 = await _chips(page, "玩家一"), await _chips(page, "玩家二")
        labels = [(await p1.nth(i).get_attribute("aria-label"), await p2.nth(i).get_attribute("aria-label")) for i in range(9)]
        return all(a == b for a, b in labels) and not await page.get_by_text("已藏雷", exact=True).count()
    await r.check("c03_information_organization", hidden_mines)

    async def dice_turn():
        current, other = await _prepare_play(page)
        current_chips, other_chips = await _chips(page, current), await _chips(page, other)
        return await contains_texts(page, ["骰子", "点", "先吃", f"轮到{current}"]) and await current_chips.nth(3).is_enabled() and not await other_chips.nth(3).is_enabled()
    await r.check("c04_rule_settlement", dice_turn)

    async def alternating():
        current, other = await _prepare_play(page)
        a, b = await _chips(page, current), await _chips(page, other)
        await a.nth(3).click()
        switched = await b.nth(3).is_enabled() and not await a.nth(4).is_enabled()
        await b.nth(3).click()
        return switched and await a.nth(4).is_enabled()
    await r.check("c05_rule_settlement", alternating)

    async def safe_result():
        current, other = await _prepare_play(page); chips = await _chips(page, current)
        await chips.nth(3).click()
        return await contains_texts(page, ["安全", f"轮到{other}"]) and await _board(page, current).get_by_text("3/3", exact=False).count() == 1
    await r.check("c06_operation_feedback", safe_result)

    async def bomb_result():
        current, other = await _prepare_play(page); chips = await _chips(page, current)
        await chips.nth(0).click()
        return await contains_texts(page, ["中雷", f"轮到{other}"]) and await _board(page, current).get_by_text("2/3", exact=False).count() == 1
    await r.check("c07_rule_settlement", bomb_result)

    async def game_over():
        loser, winner = await _prepare_play(page)
        losing, safe = await _chips(page, loser), await _chips(page, winner)
        for bomb, safe_index in zip((0, 1, 2), (3, 4, 5)):
            await losing.nth(bomb).click()
            if bomb != 2: await safe.nth(safe_index).click()
        return await contains_texts(page, ["对局结束", winner, "赢", loser, "输", "再来一局"]) and not await losing.nth(6).is_enabled()
    await r.check("c08_rule_settlement", game_over)

    async def replay():
        loser, winner = await _prepare_play(page); losing, safe = await _chips(page, loser), await _chips(page, winner)
        for bomb, safe_index in zip((0, 1, 2), (3, 4, 5)):
            await losing.nth(bomb).click()
            if bomb != 2: await safe.nth(safe_index).click()
        await click_named_any(page, ["再来一局"])
        return await contains_texts(page, ["藏雷", "玩家一", "3/3", "玩家二", "3/3"]) and not await page.get_by_text("对局结束", exact=False).count()
    await r.check("c09_rule_settlement", replay)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900})
    try:
        current, other = await _prepare_play(page); chips = await _chips(page, current); await chips.nth(3).click(); await (await _chips(page, other)).nth(0).click()
    except Exception: await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-chips-duel", full_page=False)]
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-chips-duel", full_page=True))
    return shots
