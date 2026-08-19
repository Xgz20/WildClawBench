from __future__ import annotations
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
RUNTIME_KEYS=["c01_information_organization","c02_cross_region_linkage","c03_rule_settlement","c04_rule_settlement","c05_rule_settlement","c06_rule_settlement","c07_detail_display","c08_state_persistence","c09_popup_overlay"]
VISUAL_KEYS=["c10_page_layout","c11_visual_style","c12_responsive_layout"]
async def _fresh(page): await reset_page(page)
async def _choose(page,*names): await click_named_any(page,list(names)); await page.wait_for_timeout(60)
async def _to_confront(page,delay=False,ask_doctor=False):
    await _choose(page,"请皇上宽限一日，臣妾愿以此身自证" if delay else "臣妾愿验，请皇上明鉴")
    await _choose(page,"唤院判裴仲上前，问一句药材出入" if ask_doctor else "借更衣之机，绕到盆前看一眼")
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c1(): await _fresh(page); return await contains_texts(page,["滴血验亲","承平十九年秋","昭仪沈氏","皇六子","柳美人","御前受质","顶回验亲","愿验","宽限一日"]) and await contains_any_texts(page,["暂无证据","没有证据","尚无证据"])
    await r.check("c01_information_organization",c1)
    async def c2(): await _fresh(page); await _to_confront(page); return await contains_texts(page,["当庭对质","水盆底的白色结晶","铜盆底沿积着未化尽的白色细屑","涩而微咸"])
    await r.check("c02_cross_region_linkage",c2)
    async def c3():
        if not await c2(): return False
        opt=page.get_by_role("button",name="请换一盆清水，当着众人的面重验一次",exact=False); before=await page.locator("body").inner_text(); disabled=await opt.first.is_disabled() if await opt.count() else False
        if await opt.count() and not disabled: await opt.first.click()
        return (disabled or (await opt.first.get_attribute("aria-disabled"))=="true") and "当庭对质" in await page.locator("body").inner_text()
    await r.check("c03_rule_settlement",c3)
    async def c4(): await _fresh(page); await _to_confront(page,delay=True); await _choose(page,"请换一盆清水，当着众人的面重验一次"); return await contains_texts(page,["太医院白矾领用记档","水盆底的白色结晶","真相大白"])
    await r.check("c04_rule_settlement",c4)
    async def c5(): await _fresh(page); await _to_confront(page,delay=True,ask_doctor=True); await _choose(page,"请换一盆清水，当着众人的面重验一次"); return await contains_texts(page,["险中得脱","太医院白矾领用记档"]) and await page.get_by_text("太医院白矾领用记档",exact=False).count()==1
    await r.check("c05_rule_settlement",c5)
    async def c6(): await _fresh(page); await _choose(page,"祖宗家法从无验亲之例，臣妾不敢受此辱"); return await contains_texts(page,["不验而废","沈氏降为贵人","迁居西所","六皇子交由淑妃抚养"]) and not await contains_texts(page,["验前片刻","当庭对质"])
    await r.check("c06_rule_settlement",c6)
    async def c7(): return await c4() and await contains_texts(page,["两滴血相融","白矾入水则血凝而不合","洗冤集录","慎刑司"])
    await r.check("c07_detail_display",c7)
    async def c8(): await _fresh(page); await _to_confront(page); await page.reload(wait_until="domcontentloaded"); return await contains_texts(page,["当庭对质","水盆底的白色结晶"])
    await r.check("c08_state_persistence",c8)
    async def c9():
        if not await c5(): return False
        await click_named_any(page,["重新开一局","重新开始"]); dialog=page.locator("[role=dialog],dialog,.modal,.overlay"); opened=await dialog.count() and await dialog.first.is_visible(); await click_named_any(page,["取消"]); stayed=await contains_texts(page,["险中得脱"]); await click_named_any(page,["重新开一局","重新开始"]); await click_named_any(page,["确认","确定"]); return bool(opened and stayed and await contains_texts(page,["御前受质"]) and await contains_any_texts(page,["暂无证据","没有证据"]))
    await r.check("c09_popup_overlay",c9); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"opening",full_page=False)]; await _to_confront(page); shots.append(await capture(page,screenshot_dir,"confrontation",full_page=False)); await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile",full_page=False)); return shots
