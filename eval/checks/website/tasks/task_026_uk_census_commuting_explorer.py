from __future__ import annotations

try:
    from ..common import CheckRecorder, capture, click_named_any, contains_each_any_texts, contains_texts, reset_page
except ImportError:
    from common import CheckRecorder, capture, click_named_any, contains_each_any_texts, contains_texts, reset_page


RUNTIME_KEYS = [
    "c01_information_organization", "c02_detail_display", "c03_detail_display", "c04_lists_tables",
    "c05_lists_tables", "c06_data_visualization", "c07_lists_tables", "c08_detail_display",
    "c09_lists_tables", "c10_detail_display", "c11_detail_display", "c12_detail_display",
    "c13_popup_overlay", "c14_lists_tables", "c15_page_navigation",
]
VISUAL_KEYS = ["c16_page_layout", "c17_component_style", "c18_component_style", "c19_responsive_layout"]


async def _fresh(page):
    await reset_page(page)


async def _groups(page, *groups):
    return await contains_each_any_texts(page, [list(group) for group in groups])


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def text_check(*groups):
        await _fresh(page)
        return await _groups(page, *groups)

    await recorder.check("c01_information_organization", lambda: text_check(("Jemima Stockton",), ("Oli Duke-Williams",), ("UCL", "伦敦大学学院"), ("人口普查", "census"), ("通勤", "commuting")))
    await recorder.check("c02_detail_display", lambda: text_check(("1801",), ("每十年", "ten years", "decennial"), ("9亿英镑", "£900 million"), ("1210亿英镑", "£121 billion"), ("4.4%",)))
    await recorder.check("c03_detail_display", lambda: text_check(("1%",), ("4/365",), ("1971",), ("2011",), ("四个", "four")))
    await recorder.check("c04_lists_tables", lambda: text_check(("543,884",), ("540,068",), ("585,895",), ("236,598",), ("244,173",), ("279,207",), ("232,638",), ("244,168",), ("279,206",)))
    await recorder.check("c05_lists_tables", lambda: text_check(("132,789",), ("86.3",), ("43.5",), ("30.8",), ("35.9",), ("Car/van driver", "开车"), ("Bicycle", "自行车")))

    async def heatmap():
        await _fresh(page)
        cells = page.locator("td, [role='cell']")
        colors = await cells.evaluate_all("els => [...new Set(els.map(e => getComputedStyle(e).backgroundColor).filter(c => c && c !== 'rgba(0, 0, 0, 0)'))]")
        return len(colors) >= 3 and await _groups(page, ("86.3",), ("Car/van driver", "开车"))
    await recorder.check("c06_data_visualization", heatmap)
    await recorder.check("c07_lists_tables", lambda: text_check(("131,803",), ("47.5",), ("41.3",), ("11.1",), ("88.0", "88"), ("38.7",), ("49.6",)))
    await recorder.check("c08_detail_display", lambda: text_check(("居住密度", "residential density"), ("街道连通性", "street connectivity"), ("土地利用混合度", "land-use mix"), ("633",), ("1",), ("4",)))

    async def switched_results():
        await _fresh(page)
        try:
            await click_named_any(page, ["转向步行", "Switching to walking", "开始步行"])
        except Exception:
            pass
        return await _groups(page, ("3,093",), ("3.01",), ("1.99",), ("4.53",), ("0.001",))
    await recorder.check("c09_lists_tables", switched_results)
    await recorder.check("c10_detail_display", lambda: text_check(("年龄", "age"), ("性别", "sex"), ("汽车可获得性", "car availability"), ("社会经济阶层", "socioeconomic"), ("居住地稳定性", "residential stability"), ("工作地稳定性", "workplace stability"), ("步行通勤", "walking to work")))
    await recorder.check("c11_detail_display", lambda: text_check(("成本低", "lower cost"), ("精度", "precision"), ("不具代表性", "not representative"), ("噪声", "noise"), ("个人特征", "individual characteristics"), ("不是纵向", "not longitudinal")))
    await recorder.check("c12_detail_display", lambda: text_check(("CC BY 4.0",), ("ES/V003488/1",), ("Crown Copyright", "皇家版权"), ("CeLSIUS",), ("ONS",)))

    async def modal():
        await _fresh(page)
        try:
            await click_named_any(page, ["2001 年骑自行车", "2001年骑自行车", "Bicycle"])
        except Exception:
            return False
        dialog = page.locator("[role='dialog'], dialog, .modal, .overlay")
        opened = bool(await dialog.count() and await dialog.first.is_visible())
        try:
            await click_named_any(page, ["关闭", "Close", "×"])
        except Exception:
            await page.keyboard.press("Escape")
        return opened and not bool(await dialog.count() and await dialog.first.is_visible())
    await recorder.check("c13_popup_overlay", modal)

    async def tables():
        await _fresh(page)
        detailed = await _groups(page, ("132,789",), ("86.3",))
        try:
            await click_named_any(page, ["三大类归并表", "归并表", "3-category", "Simplified"])
        except Exception:
            pass
        return detailed and await _groups(page, ("131,803",), ("47.5",), ("88.0", "88"))
    await recorder.check("c14_lists_tables", tables)

    async def navigation():
        await _fresh(page)
        try:
            await click_named_any(page, ["结论", "Conclusion", "研究结论"])
        except Exception:
            return False
        heading = page.get_by_text("结论", exact=False)
        return bool(await heading.count() and await heading.last.is_visible())
    await recorder.check("c15_page_navigation", navigation)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await _fresh(page)
    shots = [await capture(page, screenshot_dir, "desktop-full")]
    try:
        await click_named_any(page, ["2001 年骑自行车", "2001年骑自行车", "Bicycle"])
        shots.append(await capture(page, screenshot_dir, "row-detail", full_page=False))
    except Exception:
        pass
    await page.set_viewport_size({"width": 375, "height": 812})
    shots.append(await capture(page, screenshot_dir, "mobile-full"))
    return shots
