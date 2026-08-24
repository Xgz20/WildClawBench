from __future__ import annotations
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,fill_any_named,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,fill_any_named,reset_page
RUNTIME_KEYS=["c01_information_organization","c02_information_organization","c03_content_editing","c04_data_visualization","c05_data_visualization","c06_cross_region_linkage","c07_state_persistence","c08_form_validation","c11_lists_tables","c12_information_organization","c13_rule_settlement"]
VISUAL_KEYS=["c09_page_layout","c10_responsive_layout"]
async def _fresh(page): await reset_page(page)
async def _add(page,weight,date=None):
    try: await click_named_any(page,["新增记录","记录体重","添加体重"])
    except Exception: pass
    await fill_any_named(page,["体重","体重数值"],str(weight))
    if date: await fill_any_named(page,["日期","记录日期"],date)
    await click_named_any(page,["保存","添加","记录","提交"]); await page.wait_for_timeout(60)
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c1(): await _fresh(page); return await contains_any_texts(page,["新增记录","记录体重","添加体重"]) and await contains_any_texts(page,["记录列表","历史记录","体重记录"]) and await contains_any_texts(page,["趋势","变化"])
    await r.check("c01_information_organization",c1)
    async def c2(): await _fresh(page); t=await page.locator("body").inner_text(); return not any(x in t for x in ["NaN","Infinity","undefined","null"]) and await contains_any_texts(page,["还没有记录","暂无记录","趋势"])
    await r.check("c02_information_organization",c2)
    async def c3(): await _fresh(page); await _add(page,"66.4"); return await contains_texts(page,["66.4"])
    await r.check("c03_content_editing",c3)
    async def seed3():
        await _fresh(page); await _add(page,"69.0","2025-12-30"); await _add(page,"68.0","2025-12-28"); await _add(page,"70.5","2025-12-29"); return True
    async def c4():
        await seed3(); labels=page.locator("svg text,.chart-label,[data-date]"); text=" ".join(await labels.all_inner_texts()); return all(x in text for x in ["12-28","12-29","12-30"]) and text.index("12-28")<text.index("12-29")<text.index("12-30")
    await r.check("c04_data_visualization",c4)
    async def c5(): await _fresh(page); await _add(page,"70.5","2025-12-29"); await _add(page,"69.0","2025-12-30"); return await page.locator("svg path,svg circle,svg rect,canvas,.bar,.point").count()>=2
    await r.check("c05_data_visualization",c5)
    async def c6(): await _fresh(page); await _add(page,"70.5","2025-12-29"); before=await page.locator("svg circle,svg rect,.bar,.point").count(); await _add(page,"69.0","2025-12-30"); after=await page.locator("svg circle,svg rect,.bar,.point").count(); return after>before and await contains_texts(page,["2025-12-30","69.0"])
    await r.check("c06_cross_region_linkage",c6)
    async def c7(): await _fresh(page); await _add(page,"66.4","2025-12-30"); await page.reload(wait_until="domcontentloaded"); return await contains_texts(page,["66.4","2025-12-30"])
    await r.check("c07_state_persistence",c7)
    async def c8():
        await _fresh(page)
        try: await click_named_any(page,["新增记录","记录体重","添加体重"])
        except Exception: pass
        try: await click_named_any(page,["保存","添加","记录","提交"])
        except Exception: pass
        return not await page.locator("[data-weight],tbody tr,.record-item").count()
    await r.check("c08_form_validation",c8)
    async def c11(): await seed3(); return await contains_texts(page,["2025-12-28","68.0","2025-12-29","70.5","2025-12-30","69.0"])
    await r.check("c11_lists_tables",c11)
    async def c12(): await _fresh(page); await _add(page,"70.5","2025-12-28"); await _add(page,"69.0","2025-12-29"); await _add(page,"68.0","2025-12-30"); return await contains_any_texts(page,["下降","减少","变轻","↓","-2.5"])
    await r.check("c12_information_organization",c12)
    async def c13():
        await seed3(); body=await page.locator("body").inner_text()
        return await contains_texts(page,["2025-12-28","68.0","2025-12-29","70.5","2025-12-30","69.0"]) and await contains_any_texts(page,["2.5","+2.5","-1.5","69.2","69.17"]) and not any(x in body for x in ["NaN","Infinity","undefined"])
    await r.check("c13_rule_settlement",c13); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); await _add(page,"70.5","2025-12-29"); await _add(page,"69.0","2025-12-30"); shots=[await capture(page,screenshot_dir,"desktop")]; await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile")); return shots
