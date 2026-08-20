from __future__ import annotations
try:
    from ..common import CheckRecorder, capture, click_named_any, contains_each_any_texts, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_each_any_texts, contains_texts, reset_page

RUNTIME_KEYS=["c01_information_organization","c02_information_organization","c03_lists_tables","c04_page_navigation","c05_popup_overlay","c06_detail_display","c07_content_switching","c08_popup_overlay","c09_detail_display"]
VISUAL_KEYS=["c10_visual_style","c11_page_layout","c12_responsive_layout"]
async def _fresh(page): await reset_page(page)
async def _groups(page,*groups): return await contains_each_any_texts(page,[list(g) for g in groups])
async def _open_photo(page, chapter="日常"):
    try: await click_named_any(page,[chapter])
    except Exception: pass
    section=page.get_by_text(chapter,exact=True).locator("xpath=ancestor::*[self::section or self::article][1]")
    imgs=section.locator("img") if await section.count() else page.locator("img")
    if not await imgs.count(): return False
    await imgs.first.click(); await page.wait_for_timeout(80); return True
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c1(): await _fresh(page); return await _groups(page,("林知远",),("摄影","作品集","照片"))
    await r.check("c01_information_organization",c1)
    async def c2(): await _fresh(page); return await contains_texts(page,["山野","海边","街巷","日常"])
    await r.check("c02_information_organization",c2)
    async def c3():
        await _fresh(page); sec=page.get_by_text("海边",exact=True).locator("xpath=ancestor::*[self::section or self::article][1]")
        return bool(await sec.count() and await sec.locator("img").count()==5)
    await r.check("c03_lists_tables",c3)
    async def c4(): await _fresh(page); await click_named_any(page,["街巷"]); h=page.get_by_text("街巷",exact=True); return bool(await h.count() and await h.first.is_visible())
    await r.check("c04_page_navigation",c4)
    async def c5():
        await _fresh(page); before=page.url
        if not await _open_photo(page): return False
        modal=page.locator("[role=dialog],dialog,.lightbox,.modal"); opened=await modal.count() and await modal.first.is_visible() and page.url==before
        try: await click_named_any(page,["关闭","×","Close"])
        except Exception: await page.keyboard.press("Escape")
        return bool(opened and not (await modal.count() and await modal.first.is_visible()))
    await r.check("c05_popup_overlay",c5)
    async def c6(): await _fresh(page); return await _open_photo(page) and await contains_texts(page,["2023-08-02","西班牙 瓦伦西亚","在阳台上等了一个多小时","闪电"])
    await r.check("c06_detail_display",c6)
    async def c7():
        await _fresh(page)
        if not await _open_photo(page,"日常"): return False
        old=await page.locator("[role=dialog] img,.lightbox img,.modal img").first.get_attribute("src")
        await click_named_any(page,["下一张","下一个","›","Next"])
        new=await page.locator("[role=dialog] img,.lightbox img,.modal img").first.get_attribute("src")
        return old!=new and await _groups(page,("2024-04-02","2023-06-18","2023-12-24","2024-05-07","2023-11-12"),("家中","杭州"))
    await r.check("c07_content_switching",c7)
    async def c8():
        await _fresh(page); await click_named_any(page,["日常"])
        if not await _open_photo(page,"日常"): return False
        await click_named_any(page,["关闭","×","Close"]); return await page.get_by_text("日常",exact=True).first.is_visible()
    await r.check("c08_popup_overlay",c8)
    async def c9(): await _fresh(page); return await contains_texts(page,["linzhiyuan.photo@foxmail.com","linzy_photo"])
    await r.check("c09_detail_display",c9); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"portfolio-full")]
    if await _open_photo(page,"日常"): shots.append(await capture(page,screenshot_dir,"photo-lightbox",full_page=False))
    await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile")); return shots
