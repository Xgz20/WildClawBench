from __future__ import annotations

import re

try:
    from ..common import CheckRecorder, capture, click_named, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named, contains_texts, reset_page


RUNTIME_KEYS = [
    "header_game_instructions", "card_initial_state", "single_card_flip",
    "mismatch_flip_back", "matching_pair", "game_completion",
    "restart_randomization", "play_again_restart",
]
VISUAL_KEYS = ["color_heading_hierarchy", "desktop_page_layout", "card_success_style"]


async def _cards(page):
    return page.get_by_role(
        "button", name=re.compile(r"^(背面朝上的卡片|橙子|草莓|蓝莓)$")
    )


async def _all_cards_have_label(cards, expected: str) -> bool:
    for index in range(await cards.count()):
        if await cards.nth(index).get_attribute("aria-label") != expected:
            return False
    return True


async def _reveal_deck(page):
    cards = await _cards(page)
    names = []
    for index in range(await cards.count()):
        card = cards.nth(index)
        if await card.get_attribute("aria-label") == "背面朝上的卡片":
            await card.click()
            await page.wait_for_timeout(50)
        names.append(await card.get_attribute("aria-label"))
        if index % 2 == 1:
            await page.wait_for_timeout(1000)
    return names


async def _solve(page):
    cards = await _cards(page)
    known: dict[str, list[int]] = {}
    pending_index = None
    pending_name = None
    for index in range(await cards.count()):
        if await cards.nth(index).is_disabled():
            continue
        await cards.nth(index).click()
        name = await cards.nth(index).get_attribute("aria-label")
        known.setdefault(name, []).append(index)
        if pending_index is None:
            pending_index, pending_name = index, name
        else:
            await page.wait_for_timeout(1000)
            pending_index = pending_name = None
    for indices in known.values():
        if len(indices) == 2:
            first, second = indices
            if not await cards.nth(first).is_disabled():
                await cards.nth(first).click()
                await cards.nth(second).click()
                await page.wait_for_timeout(500)
    return await contains_texts(page, ["已配对 3/3", "全部配对完成！", "再玩一次"])


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def header():
        await reset_page(page)
        return await contains_texts(page, [
            "果园翻翻乐", "轻松记忆 · 随时重来", "翻开一张，记住一颗果实",
            "用最少的尝试，找出三组藏在果园里的水果。", "每次翻开两张",
            "相同保留，不同翻回", "找齐三组完成挑战", "尝试 0 次", "已配对 0/3", "重新开始",
        ])
    await recorder.check("header_game_instructions", header)

    async def initial():
        await reset_page(page)
        cards = await _cards(page)
        labels = [await cards.nth(i).get_attribute("aria-label") for i in range(await cards.count())]
        return len(labels) == 6 and labels == ["背面朝上的卡片"] * 6
    await recorder.check("card_initial_state", initial)

    async def single_flip():
        await reset_page(page)
        cards = await _cards(page)
        await cards.nth(0).click()
        labels = [await cards.nth(i).get_attribute("aria-label") for i in range(6)]
        return labels[0] in {"橙子", "草莓", "蓝莓"} and labels.count("背面朝上的卡片") == 5 and await contains_texts(page, ["尝试 0 次", "已配对 0/3"])
    await recorder.check("single_card_flip", single_flip)

    async def mismatch():
        await reset_page(page)
        cards = await _cards(page)
        await cards.nth(0).click()
        first = await cards.nth(0).get_attribute("aria-label")
        second_index = 1
        while second_index < 6:
            await cards.nth(second_index).click()
            second = await cards.nth(second_index).get_attribute("aria-label")
            if second != first:
                break
            await page.wait_for_timeout(500)
            await click_named(page, "重新开始")
            await cards.nth(0).click()
            first = await cards.nth(0).get_attribute("aria-label")
            second_index += 1
        await page.wait_for_timeout(1000)
        return await contains_texts(page, ["尝试 1 次", "已配对 0/3"]) and await cards.nth(0).get_attribute("aria-label") == "背面朝上的卡片"
    await recorder.check("mismatch_flip_back", mismatch)

    async def match_pair():
        await reset_page(page)
        cards = await _cards(page)
        await cards.nth(0).click()
        first_name = await cards.nth(0).get_attribute("aria-label")
        for index in range(1, 6):
            before_text = await page.locator("body").inner_text()
            before_match = re.search(r"尝试\s*(\d+)\s*次", before_text)
            before_attempts = int(before_match.group(1)) if before_match else -1
            await cards.nth(index).click()
            name = await cards.nth(index).get_attribute("aria-label")
            if name == first_name:
                await page.wait_for_timeout(600)
                after_text = await page.locator("body").inner_text()
                after_match = re.search(r"尝试\s*(\d+)\s*次", after_text)
                after_attempts = int(after_match.group(1)) if after_match else -1
                return (
                    await contains_texts(page, ["已配对 1/3"])
                    and after_attempts == before_attempts + 1
                    and await cards.nth(0).get_attribute("aria-label") == first_name
                    and await cards.nth(index).get_attribute("aria-label") == first_name
                )
            await page.wait_for_timeout(1000)
            if index < 5:
                await cards.nth(0).click()
                first_name = await cards.nth(0).get_attribute("aria-label")
        return False
    await recorder.check("matching_pair", match_pair)

    async def completion():
        await reset_page(page)
        return await _solve(page)
    await recorder.check("game_completion", completion)

    async def restart():
        await reset_page(page)
        old = await _reveal_deck(page)
        await click_named(page, "重新开始")
        cards = await _cards(page)
        initial_ok = await _all_cards_have_label(cards, "背面朝上的卡片")
        new = await _reveal_deck(page)
        return initial_ok and old != new and sorted(old) == sorted(new)
    await recorder.check("restart_randomization", restart)

    async def play_again():
        await reset_page(page)
        solved = await _solve(page)
        await click_named(page, "再玩一次")
        cards = await _cards(page)
        return solved and await contains_texts(page, ["尝试 0 次", "已配对 0/3"]) and await _all_cards_have_label(cards, "背面朝上的卡片")
    await recorder.check("play_again_restart", play_again)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-initial")]
    await _solve(page)
    manifest.append(await capture(page, screenshot_dir, "completed-game", full_page=False))
    return manifest
