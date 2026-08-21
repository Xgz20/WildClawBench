from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization",
    "c02_detail_display",
    "c03_rule_settlement",
    "c04_rule_settlement",
    "c05_operation_feedback",
    "c06_rule_settlement",
    "c07_operation_feedback",
]
VISUAL_KEYS = [
    "c08_component_style",
    "c09_component_style",
    "c10_responsive_layout",
]

CATEGORIES = ["可回收物", "厨余垃圾", "有害垃圾", "其他垃圾"]
ITEM_CATEGORIES = {
    "矿泉水瓶": "可回收物",
    "塑料瓶": "可回收物",
    "旧报纸": "可回收物",
    "报纸": "可回收物",
    "易拉罐": "可回收物",
    "西瓜皮": "厨余垃圾",
    "香蕉皮": "厨余垃圾",
    "鸡蛋壳": "厨余垃圾",
    "蛋壳": "厨余垃圾",
    "废电池": "有害垃圾",
    "电池": "有害垃圾",
    "过期药品": "有害垃圾",
    "废灯管": "有害垃圾",
    "一次性筷子": "其他垃圾",
    "用过的纸巾": "其他垃圾",
    "纸巾": "其他垃圾",
    "烟头": "其他垃圾",
}
RIGHT_WORDS = ["投对", "正确", "答对", "成功", "太棒", "真棒", "✓", "✔"]
WRONG_WORDS = ["投错", "错误", "答错", "不对", "错了", "再试", "✗", "✘"]


async def _enter_game(page, *, mobile=False):
    if mobile:
        await page.set_viewport_size({"width": 375, "height": 812})
    else:
        await page.set_viewport_size({"width": 1440, "height": 900})
    await reset_page(page)
    for names in (["开始游戏", "开始", "进入游戏", "马上开始"],):
        try:
            await click_named_any(page, names)
            await page.wait_for_timeout(120)
            break
        except AssertionError:
            pass


async def _visible_first(locator):
    for index in range(await locator.count()):
        candidate = locator.nth(index)
        if await candidate.is_visible():
            return candidate
    return None


async def _current_source(page):
    selectors = [
        "[aria-label*='待投放']",
        "[aria-label*='当前'][draggable]",
        "[draggable='true']",
        ".item-card",
        ".trash-item",
        ".waste-item",
        ".garbage-item",
        "[data-item]",
    ]
    for selector in selectors:
        candidate = await _visible_first(page.locator(selector))
        if candidate is not None:
            return candidate

    for name in ITEM_CATEGORIES:
        label = await _visible_first(page.get_by_text(name, exact=True))
        if label is not None:
            ancestor = label.locator(
                "xpath=ancestor-or-self::*[@draggable='true' or @role='img' "
                "or contains(@class,'item') or contains(@class,'trash') or contains(@class,'waste')][1]"
            )
            if await ancestor.count():
                return ancestor.first
    return None


async def _current_item(page):
    source = await _current_source(page)
    if source is None:
        return None, None
    parts = [await source.inner_text()]
    for attribute in ("aria-label", "title", "alt", "data-name"):
        value = await source.get_attribute(attribute)
        if value:
            parts.append(value)
    text = " ".join(parts)
    for name, category in ITEM_CATEGORIES.items():
        if name in text:
            return name, category
    body = await page.locator("body").inner_text()
    visible = [name for name in ITEM_CATEGORIES if name in body]
    if len(visible) == 1:
        name = visible[0]
        return name, ITEM_CATEGORIES[name]
    return None, None


async def _bin_target(page, category):
    label = await _visible_first(page.get_by_text(category, exact=True))
    if label is None:
        label = await _visible_first(page.get_by_text(category, exact=False))
    if label is None:
        return None
    ancestor = label.locator(
        "xpath=ancestor-or-self::*[@data-category or @role='group' or @ondrop "
        "or self::button or contains(@class,'bin') or contains(@class,'bucket') "
        "or contains(@class,'trash-can')][1]"
    )
    return ancestor.first if await ancestor.count() else label


async def _feedback_text(page):
    selectors = [
        "[role='status']",
        "[aria-live]",
        ".feedback",
        ".message",
        ".result",
        ".toast",
        ".notice",
    ]
    values = []
    for selector in selectors:
        locator = page.locator(selector)
        for index in range(await locator.count()):
            candidate = locator.nth(index)
            if await candidate.is_visible():
                text = (await candidate.inner_text()).strip()
                if text and text not in values:
                    values.append(text)
    return " ".join(values)


async def _drop(page, category):
    source = await _current_source(page)
    target = await _bin_target(page, category)
    if source is None or target is None:
        return None
    before_name, before_category = await _current_item(page)
    before_feedback = await _feedback_text(page)
    await source.drag_to(target, force=True)
    await page.wait_for_timeout(350)
    after_name, after_category = await _current_item(page)
    after_feedback = await _feedback_text(page)
    return {
        "before_name": before_name,
        "before_category": before_category,
        "after_name": after_name,
        "after_category": after_category,
        "before_feedback": before_feedback,
        "after_feedback": after_feedback,
    }


def _has_any(text, words):
    return any(word in text for word in words)


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def categories():
        await _enter_game(page)
        if not await contains_texts(page, CATEGORIES):
            return False
        targets = []
        for category in CATEGORIES:
            target = await _bin_target(page, category)
            if target is None or not await target.is_visible():
                return False
            targets.append(category)
        return len(targets) == 4

    await recorder.check("c01_information_organization", categories)

    async def item_is_identifiable():
        await _enter_game(page)
        source = await _current_source(page)
        if source is None:
            return False
        name, _ = await _current_item(page)
        visual_count = await source.locator("svg, canvas, img, [role='img']").count()
        return bool(name or visual_count)

    await recorder.check("c02_detail_display", item_is_identifiable)

    async def correct_drop():
        await _enter_game(page)
        _, category = await _current_item(page)
        if not category:
            return False
        result = await _drop(page, category)
        if not result:
            return False
        feedback = result["after_feedback"]
        advanced = result["after_name"] != result["before_name"] or result["after_name"] is not None
        return advanced and _has_any(feedback, RIGHT_WORDS) and not _has_any(feedback, WRONG_WORDS)

    await recorder.check("c03_rule_settlement", correct_drop)

    async def wrong_drop():
        await _enter_game(page)
        _, category = await _current_item(page)
        if not category:
            return False
        wrong_category = next(item for item in CATEGORIES if item != category)
        result = await _drop(page, wrong_category)
        return bool(result and _has_any(result["after_feedback"], WRONG_WORDS))

    await recorder.check("c04_rule_settlement", wrong_drop)

    async def feedback_differs():
        await _enter_game(page)
        _, category = await _current_item(page)
        if not category:
            return False
        right = await _drop(page, category)
        if not right:
            return False
        _, next_category = await _current_item(page)
        if not next_category:
            return False
        wrong_category = next(item for item in CATEGORIES if item != next_category)
        wrong = await _drop(page, wrong_category)
        if not wrong:
            return False
        right_text = right["after_feedback"]
        wrong_text = wrong["after_feedback"]
        return (
            right_text != wrong_text
            and _has_any(right_text, RIGHT_WORDS)
            and _has_any(wrong_text, WRONG_WORDS)
        )

    await recorder.check("c05_operation_feedback", feedback_differs)

    async def four_correct():
        await _enter_game(page)
        seen = []
        for _ in range(4):
            name, category = await _current_item(page)
            if not name or not category:
                return False
            result = await _drop(page, category)
            if not result or not _has_any(result["after_feedback"], RIGHT_WORDS):
                return False
            if _has_any(result["after_feedback"], WRONG_WORDS):
                return False
            seen.append(name)
        return len(seen) == 4

    await recorder.check("c06_rule_settlement", four_correct)

    async def next_item_appears():
        await _enter_game(page)
        _, category = await _current_item(page)
        if not category:
            return False
        result = await _drop(page, category)
        source = await _current_source(page)
        return bool(
            result
            and source is not None
            and await source.is_visible()
            and result["after_name"]
        )

    await recorder.check("c07_operation_feedback", next_item_appears)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await _enter_game(page)
    shots = [await capture(page, screenshot_dir, "waste-sorting-desktop", full_page=True)]
    _, category = await _current_item(page)
    if category:
        await _drop(page, category)
        shots.append(await capture(page, screenshot_dir, "waste-sorting-feedback", full_page=False))
    await _enter_game(page, mobile=True)
    shots.append(await capture(page, screenshot_dir, "waste-sorting-mobile", full_page=True))
    return shots
