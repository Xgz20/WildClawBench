from __future__ import annotations

import re

try:
    from ..common import CheckRecorder, capture, click_named, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_information_organization",
    "c03_operation_feedback", "c04_realtime_auto_progress", "c05_rule_settlement",
    "c06_rule_settlement", "c07_rule_settlement", "c11_rule_settlement",
]
VISUAL_KEYS = [
    "c08_visual_style", "c09_page_layout", "c10_component_style",
    "c12_responsive_layout",
]
FRUITS = ("橙子", "草莓", "蓝莓")


async def _cards(page):
    candidates = [
        page.get_by_role(
            "button",
            name=re.compile(r"卡片|翻开|橙子|草莓|蓝莓"),
        ),
        page.locator("button").filter(has_text=re.compile(r"橙子|草莓|蓝莓")),
        page.locator(".card"),
    ]
    for locator in candidates:
        if await locator.count() == 6:
            return locator
    raise AssertionError("six interactive memory cards not found")


async def _card_fruit(card) -> str:
    values = [
        await card.get_attribute("aria-label") or "",
        await card.get_attribute("data-fruit") or "",
        await card.get_attribute("data-name") or "",
        await card.text_content() or "",
    ]
    for fruit in FRUITS:
        if any(fruit in value for value in values):
            return fruit
    return ""


async def _card_is_hidden(card) -> bool:
    label = await card.get_attribute("aria-label") or ""
    classes = await card.get_attribute("class") or ""
    if any(token in label for token in ("背面", "未翻", "翻开卡片")):
        return True
    if any(token in label for token in (*FRUITS, "已翻", "已配对")):
        return False
    state_classes = ("flipped", "is-flipped", "face-up", "matched", "is-matched")
    return not any(token in classes.split() for token in state_classes)


async def _card_is_matched(card) -> bool:
    label = await card.get_attribute("aria-label") or ""
    classes = await card.get_attribute("class") or ""
    if "已配对" in label or any(token in classes.split() for token in ("matched", "is-matched")):
        return True
    try:
        return await card.is_disabled()
    except Exception:
        return False


async def _all_cards_hidden(cards) -> bool:
    for index in range(await cards.count()):
        if not await _card_is_hidden(cards.nth(index)):
            return False
    return True


async def _visible_card_count(cards) -> int:
    visible = 0
    for index in range(await cards.count()):
        if not await _card_is_hidden(cards.nth(index)):
            visible += 1
    return visible


async def _deck_order(cards) -> list[str]:
    return [await _card_fruit(cards.nth(index)) for index in range(await cards.count())]


async def _reveal_deck(page):
    cards = await _cards(page)
    names = []
    for index in range(await cards.count()):
        card = cards.nth(index)
        if await _card_is_matched(card):
            names.append(await _card_fruit(card))
            continue
        if await _card_is_hidden(card):
            await card.click()
            await page.wait_for_timeout(50)
        names.append(await _card_fruit(card))
        if index % 2 == 1:
            await page.wait_for_timeout(1000)
    return names


async def _solve(page):
    cards = await _cards(page)
    known: dict[str, list[int]] = {}
    for index, name in enumerate(await _deck_order(cards)):
        known.setdefault(name, []).append(index)
    for indices in known.values():
        if len(indices) == 2:
            first, second = indices
            if not await _card_is_matched(cards.nth(first)):
                await cards.nth(first).click()
                await cards.nth(second).click()
                await page.wait_for_timeout(1000)
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
    await recorder.check("c01_information_organization", header)

    async def initial():
        await reset_page(page)
        cards = await _cards(page)
        return await cards.count() == 6 and await _all_cards_hidden(cards)
    await recorder.check("c02_information_organization", initial)

    async def single_flip():
        await reset_page(page)
        cards = await _cards(page)
        await cards.nth(0).click()
        visible_count = await _visible_card_count(cards)
        return (
            await _card_fruit(cards.nth(0)) in FRUITS
            and visible_count == 1
            and await contains_texts(page, ["尝试 0 次", "已配对 0/3"])
        )
    await recorder.check("c03_operation_feedback", single_flip)

    async def mismatch():
        await reset_page(page)
        cards = await _cards(page)
        order = await _deck_order(cards)
        second_index = next(
            index for index in range(1, 6) if order[index] != order[0]
        )
        await cards.nth(0).click()
        await cards.nth(second_index).click()
        await page.wait_for_timeout(1000)
        return (
            await contains_texts(page, ["尝试 1 次", "已配对 0/3"])
            and await _card_is_hidden(cards.nth(0))
            and await _card_is_hidden(cards.nth(second_index))
        )
    await recorder.check("c04_realtime_auto_progress", mismatch)

    async def match_pair():
        await reset_page(page)
        cards = await _cards(page)
        order = await _deck_order(cards)
        second_index = order.index(order[0], 1)
        before_text = await page.locator("body").inner_text()
        before_match = re.search(r"尝试\s*(\d+)\s*次", before_text)
        before_attempts = int(before_match.group(1)) if before_match else -1
        await cards.nth(0).click()
        await cards.nth(second_index).click()
        await page.wait_for_timeout(600)
        after_text = await page.locator("body").inner_text()
        after_match = re.search(r"尝试\s*(\d+)\s*次", after_text)
        after_attempts = int(after_match.group(1)) if after_match else -1
        return (
            await contains_texts(page, ["已配对 1/3"])
            and after_attempts == before_attempts + 1
            and await _card_is_matched(cards.nth(0))
            and await _card_is_matched(cards.nth(second_index))
        )
    await recorder.check("c05_rule_settlement", match_pair)

    async def completion():
        await reset_page(page)
        return await _solve(page)
    await recorder.check("c06_rule_settlement", completion)

    async def restart():
        await reset_page(page)
        cards = await _cards(page)
        old = await _deck_order(cards)
        await click_named(page, "重新开始")
        cards = await _cards(page)
        initial_ok = await _all_cards_hidden(cards)
        new = await _deck_order(cards)
        return initial_ok and old != new and sorted(old) == sorted(new)
    await recorder.check("c07_rule_settlement", restart)

    async def play_again():
        await reset_page(page)
        solved = await _solve(page)
        await click_named(page, "再玩一次")
        cards = await _cards(page)
        return solved and await contains_texts(page, ["尝试 0 次", "已配对 0/3"]) and await _all_cards_hidden(cards)
    await recorder.check("c11_rule_settlement", play_again)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-initial")]
    await _solve(page)
    manifest.append(await capture(page, screenshot_dir, "completed-game", full_page=False))
    return manifest
