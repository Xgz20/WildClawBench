from __future__ import annotations
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
RUNTIME_KEYS=["c01_detail_display","c02_information_organization","c03_detail_display","c04_lists_tables","c05_rule_settlement","c06_content_switching","c07_cross_region_linkage","c08_rule_settlement","c09_operation_feedback"]
VISUAL_KEYS=["c10_visual_style","c11_component_style","c12_responsive_layout"]
async def _fresh(page): await reset_page(page)
async def _click(page,name): await click_named_any(page,[name,f"选择{name}"]); await page.wait_for_timeout(80)
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c1(): await _fresh(page); t=await page.locator("body").inner_text(); return all(x in t for x in ["银色","星宇橙色","深蓝色"])
    await r.check("c01_detail_display",c1)
    async def c2(): await _fresh(page); ok=await contains_texts(page,["选购","外观设计","A19 Pro","后置摄像头","前置摄像头","电池续航","规格对比"]); imgs=page.locator("img"); loaded=await imgs.evaluate_all("els => els.length>=4 && els.every(i=>i.complete&&i.naturalWidth>0)"); return ok and bool(loaded)
    await r.check("c02_information_organization",c2)
    async def c3(): await _fresh(page); return await contains_texts(page,["4800 万","8 倍","16 倍"])
    await r.check("c03_detail_display",c3)
    async def c4(): await _fresh(page); return await contains_texts(page,["iPhone 17 Pro","6.3 英寸","204 克","31 小时","iPhone 17 Pro Max","6.9 英寸","231 克","37 小时"])
    await r.check("c04_lists_tables",c4)
    async def configured(): await _fresh(page); await _click(page,"iPhone 17 Pro Max"); await _click(page,"深蓝色"); await _click(page,"512GB"); return await contains_any_texts(page,["¥11,999","￥11,999","11,999 元","11999 元"])
    await r.check("c05_rule_settlement",configured)
    async def c6():
        await _fresh(page); await _click(page,"银色"); img=page.locator("img[data-product],.product-image img,.hero img").first; before=await img.get_attribute("src") if await img.count() else ""; await _click(page,"星宇橙色"); after=await img.get_attribute("src") if await img.count() else ""; return bool(before and after and before!=after)
    await r.check("c06_content_switching",c6)
    async def c7(): await _fresh(page); await _click(page,"iPhone 17 Pro Max"); await _click(page,"2TB"); await _click(page,"iPhone 17 Pro"); b=page.get_by_role("button",name="2TB",exact=False); return not await b.count() or await b.first.is_disabled() or (await b.first.get_attribute("aria-disabled"))=="true"
    await r.check("c07_cross_region_linkage",c7)
    async def c8(): await _fresh(page); await _click(page,"iPhone 17 Pro Max"); await _click(page,"2TB"); await _click(page,"iPhone 17 Pro"); return await contains_any_texts(page,["8999","10999","12999"]) and not await contains_texts(page,["17999"])
    await r.check("c08_rule_settlement",c8)
    async def c9():
        await _fresh(page); video=page.locator("video");
        if not await video.count(): return False
        try: await click_named_any(page,["播放","Play"])
        except Exception: await video.first.click()
        before=await video.first.evaluate("v=>v.currentTime"); await page.wait_for_timeout(1200); after=await video.first.evaluate("v=>v.currentTime"); return after>before
    await r.check("c09_operation_feedback",c9); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"desktop")]; await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile")); return shots
