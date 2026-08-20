from __future__ import annotations
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_texts,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_texts,reset_page
RUNTIME_KEYS=["c03_lists_tables","c04_search_filtering","c05_lists_tables","c06_search_filtering","c07_lists_tables","c08_popup_overlay","c09_content_switching","c10_detail_display","c11_detail_display"]
VISUAL_KEYS=["c01_page_layout","c02_visual_style","c12_responsive_layout"]
WORKS=["渡口以北","长夜有雾","候鸟不飞","雨落在铁皮上","八月练习曲","南方来信","旧船票","城市的裂缝","晚风塔台","我们不谈永远"]
async def _fresh(page): await reset_page(page)
async def _nav(page,name): await click_named_any(page,[name]); await page.wait_for_timeout(60)
async def _filter(page,name):
    for i in range(await page.locator("select").count()):
        s=page.locator("select").nth(i); opts=await s.locator("option").all_text_contents(); m=next((o for o in opts if name in o),None)
        if m: await s.select_option(label=m); return True
    await click_named_any(page,[name]); return True
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c3(): await _fresh(page); await _nav(page,"音乐"); imgs=page.locator(".work img,[data-work] img"); return await contains_texts(page,WORKS) and await imgs.count()==10 and bool(await imgs.evaluate_all("els=>els.every(i=>i.complete&&i.naturalWidth>0)"))
    await r.check("c03_lists_tables",c3)
    async def c4(): await _fresh(page); await _nav(page,"音乐"); await _filter(page,"EP"); t=await page.locator("body").inner_text(); return all(x in t for x in ["雨落在铁皮上","八月练习曲","南方来信"]) and all(x not in t for x in ["渡口以北","旧船票"])
    await r.check("c04_search_filtering",c4)
    async def c5(): await _fresh(page); await _nav(page,"行程"); rows=page.locator(".schedule-item,[data-event],tbody tr"); return await rows.count()==8 and await contains_texts(page,["日期","类型","城市","场地","演出","见面会","商务直播"])
    await r.check("c05_lists_tables",c5)
    async def c6(): await _fresh(page); await _nav(page,"行程"); await _filter(page,"商务直播"); t=await page.locator("body").inner_text(); return all(x in t for x in ["声海耳机春季新品直播","木棉吉他联名款发布直播","线上","品牌直播间"]) and "见面会" not in t
    await r.check("c06_search_filtering",c6)
    async def c7(): await _fresh(page); await _nav(page,"相册"); ok=await contains_texts(page,["巡演现场","录音室","在路上"]); await click_named_any(page,["录音室"]); imgs=page.locator(".album img,[data-photo],.gallery img"); return ok and await imgs.count()==5
    await r.check("c07_lists_tables",c7)
    async def c8():
        await _fresh(page); await _nav(page,"相册"); await click_named_any(page,["巡演现场"]); img=page.locator(".album img,[data-photo],.gallery img").first; small=await img.bounding_box(); await img.click(); modal=page.locator("[role=dialog],dialog,.lightbox,.modal"); big=await modal.locator("img").first.bounding_box(); opened=await modal.count() and big and small and big["width"]>=small["width"]*1.5; await click_named_any(page,["关闭","×","Close"]); return bool(opened and not (await modal.count() and await modal.first.is_visible()))
    await r.check("c08_popup_overlay",c8)
    async def c9():
        await _fresh(page); await _nav(page,"相册"); await click_named_any(page,["在路上"]); img=page.locator(".album img,[data-photo],.gallery img").first; await img.click(); modal=page.locator("[role=dialog],dialog,.lightbox,.modal"); before=await modal.locator("img").first.get_attribute("src"); await click_named_any(page,["下一张","下一个","›","Next"]); after=await modal.locator("img").first.get_attribute("src"); return bool(before and after and before!=after)
    await r.check("c09_content_switching",c9)
    async def c10(): await _fresh(page); await _nav(page,"简介"); img=page.locator("img[src*='portrait'],.bio img"); return await contains_texts(page,["2018","旧船票","2019","渡口以北","长夜有雾","第七届云雀音乐奖","年度民谣专辑"]) and await img.count()>0
    await r.check("c10_detail_display",c10)
    async def c11(): await _fresh(page); await _nav(page,"联系方式"); return await contains_texts(page,["booking@shenyu-music.com","@沈屿SHENYU","沈屿的练习室"])
    await r.check("c11_detail_display",c11); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"home",full_page=False)]; await _nav(page,"音乐"); shots.append(await capture(page,screenshot_dir,"music")); await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile")); return shots
