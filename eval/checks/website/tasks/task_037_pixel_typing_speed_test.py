from __future__ import annotations
import re
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,reset_page
RUNTIME_KEYS=["c01_information_organization","c02_detail_display","c03_realtime_auto_progress","c04_realtime_auto_progress","c05_realtime_auto_progress","c06_rule_settlement","c07_rule_settlement"]
VISUAL_KEYS=["c08_visual_style","c09_page_layout","c10_responsive_layout"]
TEXT="那刘姥姥入了坐，拿起箸来，沉甸甸的不伏手"
async def _fresh(page): await reset_page(page)
async def _start(page): await click_named_any(page,["开始","开始测试","开始这一轮"])
async def _input(page):
    box=page.locator("textarea,input[type=text],[contenteditable=true]"); return box.first
async def _numbers(page): return [float(x) for x in re.findall(r"\d+(?:\.\d+)?",await page.locator("body").inner_text())]
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c1(): await _fresh(page); return await contains_texts(page,["倒计时","速度","正确率"]) and await contains_any_texts(page,["60","01:00"]) and await (await _input(page)).count()>0
    await r.check("c01_information_organization",c1)
    async def c2(): await _fresh(page); return await contains_texts(page,[TEXT,"这个叉巴子，比我们那里的铁锨还沉","老刘，老刘，食量大如牛：吃个老母猪，不抬头！","独有凤姐鸳鸯二人掌着，还只管让刘姥姥。"])
    await r.check("c02_detail_display",c2)
    async def c3(): await _fresh(page); before=await page.locator("body").inner_text(); await page.wait_for_timeout(1100); idle=await page.locator("body").inner_text(); await _start(page); await page.wait_for_timeout(1100); active=await page.locator("body").inner_text(); return before==idle and active!=idle
    await r.check("c03_realtime_auto_progress",c3)
    async def c4(): await _fresh(page); await _start(page); box=await _input(page); await box.fill(TEXT); await page.wait_for_timeout(1100); n1=await _numbers(page); await page.wait_for_timeout(1100); n2=await _numbers(page); return n1!=n2 and await contains_any_texts(page,["100%","100 %"])
    await r.check("c04_realtime_auto_progress",c4)
    async def c5():
        await _fresh(page); await page.clock.install(); await page.reload(wait_until="domcontentloaded"); await _start(page); await page.clock.fast_forward(61000); return await contains_any_texts(page,["再来一次","重新开始","本轮成绩"]) and (await (await _input(page)).is_disabled() or await (await _input(page)).get_attribute("readonly") is not None)
    await r.check("c05_realtime_auto_progress",c5)
    async def c6(): await _fresh(page); await _start(page); box=await _input(page); await box.fill("那刘姥姥入了座，拿起筷来，沉甸甸的不伏手"); await page.wait_for_timeout(200); marked=page.locator(".wrong,.incorrect,[data-status=wrong]"); return await marked.count()>=2 and not await contains_any_texts(page,["正确率 100%","正确率：100%"])
    await r.check("c06_rule_settlement",c6)
    async def c7(): await _fresh(page); await _start(page); box=await _input(page); await box.fill(TEXT); await click_named_any(page,["再来一次","重新开始"]); return await box.input_value()=="" and await contains_any_texts(page,["60","01:00"])
    await r.check("c07_rule_settlement",c7); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"desktop",full_page=False)]; await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile",full_page=False)); return shots
