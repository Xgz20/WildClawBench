from __future__ import annotations

import re

try:
    from ..common import CheckRecorder, capture, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_lists_tables", "c03_cross_region_linkage",
    "c04_rule_settlement", "c05_rule_settlement", "c06_rule_settlement",
]
VISUAL_KEYS = ["c07_page_layout", "c08_responsive_layout"]
PEOPLE = ["小冰", "小洁", "小晴", "小玉"]


async def _rows(page):
    candidates = page.locator("tr, li, [class*='row']")
    rows = []
    for i in range(await candidates.count()):
        text = (await candidates.nth(i).inner_text()).strip()
        if sum(name in text for name in PEOPLE) == 1 and ("周" in text or "—" in text or "-" in text):
            rows.append(text)
    return rows


def _person(text):
    return next((name for name in PEOPLE if name in text), None)


async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)

    async def current():
        await reset_page(page)
        body = await page.locator("body").inner_text()
        marked = [name for name in PEOPLE if re.search(rf"(当前|本周|现在)[^\n]{{0,30}}{name}|{name}[^\n]{{0,30}}(当前|本周|现在)", body)]
        return len(set(marked)) == 1
    await r.check("c01_information_organization", current)

    async def roster():
        await reset_page(page); rows = await _rows(page); people = [_person(row) for row in rows]
        return len(rows) >= 4 and set(people[:4]) == set(PEOPLE) and all("周" in row for row in rows[:4])
    await r.check("c02_lists_tables", roster)

    async def linkage():
        await reset_page(page); rows = await _rows(page)
        current_rows = [row for row in rows if "本周" in row or "现在" in row or "当前" in row]
        if len(current_rows) != 1: return False
        current_name = _person(current_rows[0])
        hero = page.locator("[class*='current'], [class*='hero'], [aria-label*='当前']")
        hero_text = " ".join(await hero.all_text_contents())
        return current_name is not None and current_name in hero_text
    await r.check("c03_cross_region_linkage", linkage)

    async def whole_weeks():
        await reset_page(page); rows = await _rows(page)
        return len(rows) >= 4 and all(len(re.findall(r"\d{1,2}\s*月\s*\d{1,2}\s*日", row)) >= 2 or "周" in row for row in rows[:4])
    await r.check("c04_rule_settlement", whole_weeks)

    async def next_person():
        await reset_page(page); rows = await _rows(page); names = [_person(row) for row in rows]
        if len(names) < 2 or None in names: return False
        return PEOPLE[(PEOPLE.index(names[0]) + 1) % 4] == names[1]
    await r.check("c05_rule_settlement", next_person)

    async def cycle():
        await reset_page(page); names = [_person(row) for row in await _rows(page)]
        if len(names) < 4 or set(names[:4]) != set(PEOPLE): return False
        order_ok = all(PEOPLE[(PEOPLE.index(names[i]) + 1) % 4] == names[i + 1] for i in range(3))
        return order_ok and (len(names) < 5 or names[4] == names[0])
    await r.check("c06_rule_settlement", cycle)
    return r.results


async def capture_visual(page, screenshot_dir):
    await page.set_viewport_size({"width": 1440, "height": 900}); await reset_page(page)
    shots = [await capture(page, screenshot_dir, "desktop-duty-roster", full_page=False)]
    await page.set_viewport_size({"width": 375, "height": 812}); await reset_page(page, clear_storage=False)
    shots.append(await capture(page, screenshot_dir, "mobile-duty-roster", full_page=True))
    return shots
