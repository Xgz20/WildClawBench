from __future__ import annotations
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
RUNTIME_KEYS=["c01_information_organization","c02_file_upload_and_download","c03_rule_settlement","c04_content_switching","c06_content_editing","c07_content_editing","c08_content_editing","c09_file_upload_and_download"]
VISUAL_KEYS=["c05_page_layout","c10_page_layout","c11_responsive_layout"]
EVAL="/tmp_workspace_eval"
async def _fresh(page): await reset_page(page)
async def _upload(page,names):
    inp=page.locator("input[type=file]")
    if not await inp.count(): return False
    await inp.first.set_input_files([f"{EVAL}/{n}" for n in names]); await page.wait_for_timeout(120); return True
async def _images(page): return page.locator(".collage img,.canvas img,[data-collage] img")
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c1(): await _fresh(page); return await page.locator("input[type=file]").count()>0 and await contains_any_texts(page,["自动排布","自动布局"]) and await contains_any_texts(page,["横排一行","横向"]) and await contains_any_texts(page,["竖排一列","纵向"]) and await contains_any_texts(page,["自由拖拽","自由布局"]) and await contains_any_texts(page,["导出","下载"])
    await r.check("c01_information_organization",c1)
    async def c2(): await _fresh(page); ok=await _upload(page,["coast-01.jpg","daily-01.jpg","mountain-02.jpg"]); imgs=await _images(page); loaded=await imgs.evaluate_all("els=>els.length===3&&els.every(i=>i.complete&&i.naturalWidth>0)"); return ok and bool(loaded)
    await r.check("c02_file_upload_and_download",c2)
    async def c3():
        await _fresh(page); names=["coast-01.jpg","coast-02.jpg","coast-04.jpg","coast-05.jpg","daily-01.jpg","daily-02.jpg","daily-03.jpg","daily-05.jpg","mountain-02.jpg","mountain-03.jpg","street-05.jpg"]; await _upload(page,names); return await (await _images(page)).count()<=10 and (await contains_any_texts(page,["最多","上限","10 张","10张"]) or await (await _images(page)).count()==10)
    await r.check("c03_rule_settlement",c3)
    async def c4():
        if not await c2(): return False
        await click_named_any(page,["横排一行","横向"]); imgs=await _images(page); boxes=[await imgs.nth(i).bounding_box() for i in range(3)]; horizontal=max(b["y"] for b in boxes)-min(b["y"] for b in boxes)<10
        await click_named_any(page,["竖排一列","纵向"]); boxes=[await imgs.nth(i).bounding_box() for i in range(3)]; vertical=max(b["x"] for b in boxes)-min(b["x"] for b in boxes)<10
        return horizontal and vertical
    await r.check("c04_content_switching",c4)
    async def c6():
        await _fresh(page); await _upload(page,["coast-01.jpg","daily-01.jpg"]); imgs=await _images(page); before=[await imgs.nth(i).bounding_box() for i in range(2)]; await imgs.first.click(); await click_named_any(page,["放大","150%","+"]); after=[await imgs.nth(i).bounding_box() for i in range(2)]; return after[0]["width"]>before[0]["width"] and abs(after[1]["width"]-before[1]["width"])<2
    await r.check("c06_content_editing",c6)
    async def c7():
        await _fresh(page); await _upload(page,["coast-01.jpg","daily-01.jpg"]); imgs=await _images(page); await imgs.first.click(); before=await imgs.first.evaluate("e=>getComputedStyle(e).transform"); await click_named_any(page,["旋转","旋转 90°","90°"]); after=await imgs.first.evaluate("e=>getComputedStyle(e).transform"); return before!=after
    await r.check("c07_content_editing",c7)
    async def c8():
        await _fresh(page); await _upload(page,["coast-01.jpg","daily-01.jpg"]); await click_named_any(page,["自由拖拽","自由布局"]); imgs=await _images(page); before=await imgs.first.bounding_box(); await imgs.first.drag_to(page.locator(".collage,.canvas,[data-collage]").first,target_position={"x":250,"y":180}); after=await imgs.first.bounding_box(); return abs(after["x"]-before["x"])+abs(after["y"]-before["y"])>20
    await r.check("c08_content_editing",c8)
    async def c9():
        if not await c2(): return False
        async with page.expect_download(timeout=1500) as info: await click_named_any(page,["导出","下载拼图","导出图片"])
        return bool((await info.value).suggested_filename)
    await r.check("c09_file_upload_and_download",c9); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); await _upload(page,["coast-01.jpg","daily-01.jpg","mountain-02.jpg"]); shots=[await capture(page,screenshot_dir,"desktop-collage")]; await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile-collage")); return shots
