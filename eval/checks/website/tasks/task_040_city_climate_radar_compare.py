from __future__ import annotations
try:
    from ..common import CheckRecorder,capture,click_named_any,contains_texts,reset_page
except ImportError:
    from common import CheckRecorder,capture,click_named_any,contains_texts,reset_page
RUNTIME_KEYS=["c01_data_visualization","c02_search_filtering","c03_rule_settlement","c04_lists_tables","c05_data_visualization","c06_data_visualization","c07_data_visualization","c08_content_switching","c09_cross_region_linkage","c13_rule_settlement"]
VISUAL_KEYS=["c10_page_layout","c11_visual_style","c12_responsive_layout"]
async def _fresh(page): await reset_page(page)
async def _toggle(page,name): await click_named_any(page,[name,f"选择{name}"]); await page.wait_for_timeout(60)
async def _set_month(page,text):
    for i in range(await page.locator("select").count()):
        s=page.locator("select").nth(i); opts=await s.locator("option").all_text_contents(); m=next((o for o in opts if text in o),None)
        if m: await s.select_option(label=m); return True
    await click_named_any(page,[text,f"{text}月"]); return True
async def _selected(page): return page.locator("input[type=checkbox]:checked,[aria-pressed=true],[aria-selected=true],.city.selected,.city.active")
async def run(page,screenshot_dir):
    r=CheckRecorder(page,screenshot_dir)
    async def c1():
        await _fresh(page); radar=page.locator("svg,canvas,[role=img]"); axes=page.locator("svg line,svg .axis,[data-axis]"); polygons=page.locator("svg polygon,svg path[data-city],canvas")
        return await radar.count()>0 and await axes.count()>=5 and await polygons.count()>=3 and await contains_texts(page,["月均气温","月降水量","晴天数","平均相对湿度","平均风力"])
    await r.check("c01_data_visualization",c1)
    async def choose_three():
        await _fresh(page); selected=await _selected(page)
        for i in range(await selected.count()):
            label=await selected.nth(i).get_attribute("aria-label") or await selected.nth(i).get_attribute("value") or ""
            if label and label not in ["广州","哈尔滨","拉萨"]: await selected.nth(i).click()
        for city in ["广州","哈尔滨","拉萨"]:
            control=page.get_by_role("checkbox",name=city,exact=False)
            if await control.count() and not await control.first.is_checked(): await control.first.check()
            elif not await control.count():
                active=page.locator("[aria-pressed=true],.selected,.active").filter(has_text=city)
                if not await active.count(): await _toggle(page,city)
        return await (await _selected(page)).count()==3 and await contains_texts(page,["广州","哈尔滨","拉萨"])
    await r.check("c02_search_filtering",choose_three)
    async def max_four():
        await _fresh(page)
        for city in ["广州","昆明","乌鲁木齐","哈尔滨"]:
            try: await _toggle(page,city)
            except Exception: pass
        before=await (await _selected(page)).count();
        try: await _toggle(page,"拉萨")
        except Exception: pass
        return before==4 and await (await _selected(page)).count()==4
    await r.check("c03_rule_settlement",max_four)
    async def c4(): await _fresh(page); row=page.get_by_text("广州",exact=True).locator("xpath=ancestor::tr[1]"); return bool(await row.count() and await contains_texts(row,["28.9","286","16","82","2.5"]))
    await r.check("c04_lists_tables",c4)
    async def radar_values(metric,values):
        await _fresh(page); visual=page.locator("svg,canvas,[role=img]"); return await visual.count()>0 and await contains_texts(page,[metric]+values)
    await r.check("c05_data_visualization",lambda:radar_values("月降水量",["广州","286","昆明","210","乌鲁木齐","28"]))
    await r.check("c06_data_visualization",lambda:radar_values("晴天数",["乌鲁木齐","23","广州","16","昆明","7"]))
    await r.check("c07_data_visualization",lambda:radar_values("月均气温",["哈尔滨","-18.4","广州","13.9"]))
    async def c8(): await _fresh(page); await _set_month(page,"1月"); return await contains_texts(page,["广州","40"]) and not await contains_texts(page,["286"])
    await r.check("c08_content_switching",c8)
    async def c9():
        await _fresh(page); await _toggle(page,"乌鲁木齐"); before=await page.get_by_text("乌鲁木齐",exact=True).count(); await _toggle(page,"乌鲁木齐"); table=page.locator("table"); return before>0 and (not await table.count() or "乌鲁木齐" not in await table.inner_text())
    await r.check("c09_cross_region_linkage",c9)
    async def c13():
        await _fresh(page); body=await page.locator("body").inner_text(); visual=page.locator("svg,canvas,[role=img]")
        return await visual.count()>0 and await contains_texts(page,["广州","28.9","286","16","82","2.5","昆明","210","乌鲁木齐","28","23"]) and not any(x in body for x in ["NaN","Infinity","undefined"])
    await r.check("c13_rule_settlement",c13); return r.results
async def capture_visual(page,screenshot_dir):
    await _fresh(page); shots=[await capture(page,screenshot_dir,"desktop-radar",full_page=False)]; await page.set_viewport_size({"width":375,"height":812}); shots.append(await capture(page,screenshot_dir,"mobile-radar")); return shots
