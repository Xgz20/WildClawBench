from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_any_texts, contains_texts, reset_page

RUNTIME_KEYS = ["c01_lists_tables", "c02_information_organization", "c03_rule_settlement", "c04_operation_feedback", "c05_rule_settlement", "c06_state_persistence", "c07_operation_feedback", "c08_rule_settlement", "c09_data_visualization"]
VISUAL_KEYS = ["c10_page_layout", "c11_visual_style", "c12_responsive_layout"]
A_NAMES = ["千早爱音", "阿米娅", "芙莉莲", "藤丸立香", "樱岛麻衣", "星野瑠美衣", "小栗帽", "菲伦"]

async def _fresh(page): await reset_page(page)

async def _pick(page, name):
    await click_named_any(page, [name])
    await page.wait_for_timeout(60)

async def _advance_groups(page):
    for _ in range(8):
        buttons = page.locator("button[data-action='pick'], button[aria-pressed], .grid button, .character-card")
        if await buttons.count() < 2: return False
        await buttons.nth(0).click(); await page.wait_for_timeout(30)
        await buttons.nth(1).click(); await page.wait_for_timeout(60)
    return True

async def run(page, screenshot_dir):
    r = CheckRecorder(page, screenshot_dir)
    async def roster():
        await _fresh(page)
        cards = page.locator(".roster-card, [data-character], img[alt]")
        imgs = page.locator("img")
        loaded = await imgs.evaluate_all("els => els.length && els.every(i => i.complete && i.naturalWidth > 0)")
        return await cards.count() >= 64 and bool(loaded) and await contains_texts(page, ["千早爱音", "元祖！BanG Dream Chan", "猫猫", "药屋少女的呢喃 第二季", "灶门祢豆子", "鬼灭之刃"])
    await r.check("c01_lists_tables", roster)
    async def first_group():
        await _fresh(page); text = await page.locator("body").inner_text()
        return all(x in text for x in A_NAMES) and await contains_any_texts(page, ["A 组", "A组", "小组赛 1/8", "第 1 组"])
    await r.check("c02_information_organization", first_group)
    async def auto_advance():
        await _fresh(page); await _pick(page, "千早爱音"); await _pick(page, "芙莉莲")
        return await contains_any_texts(page, ["B 组", "B组", "小组赛 2/8", "第 2 组"])
    await r.check("c03_rule_settlement", auto_advance)
    await r.check("c04_operation_feedback", auto_advance)
    async def sixteen():
        await _fresh(page)
        if not await _advance_groups(page): return False
        duel = page.locator(".duel button, [data-action='pick']")
        return await contains_texts(page, ["16 强"]) and await duel.count() == 2
    await r.check("c05_rule_settlement", sixteen)
    async def persistence():
        if not await auto_advance(): return False
        await page.reload(wait_until="domcontentloaded")
        return await contains_any_texts(page, ["B 组", "B组", "小组赛 2/8", "第 2 组"])
    await r.check("c06_state_persistence", persistence)
    async def restart():
        if not await auto_advance(): return False
        await click_named_any(page, ["重新开始", "重置比赛"])
        try: await click_named_any(page, ["确认", "确定", "重新开始"])
        except Exception: pass
        return await contains_any_texts(page, ["A 组", "A组", "小组赛 1/8", "第 1 组"])
    await r.check("c07_operation_feedback", restart)
    async def complete():
        await _fresh(page)
        if not await _advance_groups(page): return False
        for _ in range(15):
            buttons = page.locator(".duel button, button[data-action='pick']")
            if not await buttons.count(): break
            await buttons.first.click(); await page.wait_for_timeout(30)
        return await contains_texts(page, ["本届萌王", "比赛结束"]) and await page.locator(".champion img, [data-champion] img").count() > 0
    await r.check("c08_rule_settlement", complete)
    async def bracket():
        if not await complete(): return False
        return await contains_texts(page, ["16 强", "8 强", "4 强", "决赛", "萌王"]) and await page.locator(".match, [data-match]").count() >= 15
    await r.check("c09_data_visualization", bracket)
    return r.results

async def capture_visual(page, screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"group-stage")]
    await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile-group"))
    return shots
