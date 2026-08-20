from __future__ import annotations
from datetime import date,timedelta
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,fill_any_named,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_any_texts,contains_texts,fill_any_named,reset_page
RUNTIME_KEYS=["c01_information_organization","c02_detail_display","c03_content_editing","c04_rule_settlement","c05_content_switching","c06_operation_feedback","c07_state_persistence","c08_form_validation","c09_lists_tables","c10_information_organization"]
VISUAL_KEYS=["c11_page_layout","c12_responsive_layout"]
async def _fresh(page): await reset_page(page)
async def _add(page,text,day):
    try: await click_named_any(page,["新增待办","添加待办","新建待办"])
    except Exception: pass
    await fill_any_named(page,["待办内容","内容","要做什么"],text); await fill_any_named(page,["日期","待办日期"],day); await click_named_any(page,["添加","保存","提交"]); await page.wait_for_timeout(50)
async def _all(page):
    try: await click_named_any(page,["全部待办","全部"])
    except Exception: pass
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir); today=date.today().isoformat(); tomorrow=(date.today()+timedelta(days=1)).isoformat()
    async def c1(): await _fresh(page); return await contains_any_texts(page,["新增待办","添加待办","新建待办"]) and await contains_any_texts(page,["今天要做","今日待办"]) and await contains_any_texts(page,["全部待办","所有待办"])
    await r.check("c01_information_organization",c1)
    async def c2(): await _fresh(page); text=await page.locator("body").inner_text(); return (str(date.today().month) in text and str(date.today().day) in text) and not any(x in text for x in ["NaN","Invalid Date","undefined","null"])
    await r.check("c02_detail_display",c2)
    async def c3(): await _fresh(page); await _add(page,"取快递",today); return await page.get_by_text("取快递",exact=True).count()==1
    await r.check("c03_content_editing",c3)
    async def seed2(): await _fresh(page); await _add(page,"取快递",today); await _add(page,"换季收纳",tomorrow)
    async def c4(): await seed2(); area=page.get_by_text("今天要做",exact=False).locator("xpath=ancestor::*[self::section or self::div][1]"); t=await area.inner_text() if await area.count() else await page.locator("body").inner_text(); return "取快递" in t and "换季收纳" not in t
    await r.check("c04_rule_settlement",c4)
    async def c5(): await seed2(); await _all(page); return await contains_texts(page,["取快递","换季收纳"])
    await r.check("c05_content_switching",c5)
    async def c6():
        await _fresh(page); await _add(page,"取快递",today); row=page.get_by_text("取快递",exact=True).locator("xpath=ancestor::*[self::li or contains(@class,'todo')][1]"); ctrl=row.locator("input[type=checkbox],button").first
        if not await ctrl.count(): return False
        await ctrl.click(); await _all(page); item=page.get_by_text("取快递",exact=True); style=await item.evaluate("e=>getComputedStyle(e).textDecorationLine+' '+getComputedStyle(e).opacity"); return await item.count()>0 and ("line-through" in style or "0." in style or await row.locator("input[type=checkbox]:checked,.completed,.done").count()>0)
    await r.check("c06_operation_feedback",c6)
    async def c7():
        await _fresh(page); await _add(page,"取快递",today); await _add(page,"交水电费",today); row=page.get_by_text("取快递",exact=True).locator("xpath=ancestor::*[self::li or contains(@class,'todo')][1]"); await row.locator("input[type=checkbox],button").first.click(); await page.reload(wait_until="domcontentloaded"); await _all(page); return await contains_texts(page,["取快递","交水电费"]) and await page.locator("input[type=checkbox]:checked,.completed,.done").count()>0
    await r.check("c07_state_persistence",c7)
    async def c8():
        await _fresh(page)
        try: await click_named_any(page,["新增待办","添加待办","新建待办"])
        except Exception: pass
        try: await click_named_any(page,["添加","保存","提交"])
        except Exception: pass
        return not await page.locator(".todo-item,[data-todo],li input[type=checkbox]").count()
    await r.check("c08_form_validation",c8)
    async def c9(): await _fresh(page); [await _add(page,x,today) for x in ["取快递","交水电费","订体检"]]; return await contains_texts(page,["取快递","交水电费","订体检"])
    await r.check("c09_lists_tables",c9)
    async def c10(): await _fresh(page); t=await page.locator("body").inner_text(); return not any(x in t for x in ["NaN","Infinity","undefined","null","Invalid Date"]) and await contains_any_texts(page,["没有","暂无","今天要做","全部待办"])
    await r.check("c10_information_organization",c10); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"desktop")]; await page.set_viewport_size({"width":375,"height":812}); await _add(page,"取快递",date.today().isoformat()); shots.append(await capture(page,screenshot_dir,"mobile")); return shots
