from __future__ import annotations

import re

try:
    from ..common import (
        CheckRecorder, capture, click_named_any, contains_any_texts,
        contains_each_any_texts, contains_texts, reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named_any, contains_any_texts,
        contains_each_any_texts, contains_texts, reset_page,
    )


RUNTIME_KEYS = [
    "c01_information_organization", "c02_detail_display", "c03_data_visualization",
    "c04_data_visualization", "c05_lists_tables", "c06_lists_tables", "c07_lists_tables",
    "c08_search_filtering", "c09_cross_region_linkage", "c10_cross_region_linkage",
    "c11_cross_region_linkage", "c12_cross_region_linkage", "c13_cross_region_linkage",
    "c14_search_filtering", "c15_cross_region_linkage", "c16_cross_region_linkage",
    "c17_content_switching", "c18_search_filtering", "c19_search_filtering",
    "c20_search_filtering", "c23_page_navigation", "c24_page_navigation",
]
VISUAL_KEYS = ["c21_page_layout", "c22_visual_style", "c25_responsive_layout", "c26_page_layout"]


async def _select_value(page, value: str) -> bool:
    selects = page.locator("select")
    for index in range(await selects.count()):
        options = [option.strip() for option in await selects.nth(index).locator("option").all_text_contents()]
        if any(opt == value for opt in options):
            await selects.nth(index).select_option(label=value)
            await page.wait_for_timeout(100)
            return True
    try:
        await click_named_any(page, [value, f"{value}（", f"切换{value}", f"选择{value}"])
        return True
    except Exception:
        return False


async def _open_alert(page, label: str) -> bool:
    try:
        await click_named_any(page, [label, f"{label}项", f"{label}状态"])
        return True
    except Exception:
        return False


async def _contains_chart(page) -> bool:
    return (
        await page.locator("canvas").count() > 0
        or await page.locator("svg").count() > 0
        or await page.locator("[role='img'], .recharts-wrapper, .chart-container").count() > 0
    )


def _contains_any_terms(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


async def _data_item_count(region) -> int:
    selectors = (
        "tr", "[role='row']", "[data-row]", ".table-row",
        ".school-row", ".warning-row", ".list-item",
    )
    for selector in selectors:
        items = region.locator(selector)
        visible = 0
        for index in range(await items.count()):
            item = items.nth(index)
            if not await item.is_visible() or await item.locator("th").count():
                continue
            visible += 1
        if visible:
            return visible
    return 0


async def _paginate_section(
    page,
    headings: list[str],
    *,
    expected_total: int,
    expected_after_count: int | tuple[int, int],
    prefer_last_heading: bool = False,
) -> bool:
    heading = None
    for text in headings:
        locator = page.get_by_text(text, exact=False)
        if await locator.count():
            heading = locator.last if prefer_last_heading else locator.first
            break
    if heading is None:
        return False
    region = heading.locator(
        "xpath=ancestor::*[.//*[self::button or @role='button']"
        "[contains(normalize-space(.), '下一页') or contains(normalize-space(.), '下页')"
        " or contains(@aria-label, '下一页') or contains(@aria-label, 'Next')]][1]"
    )
    if not await region.count():
        return False
    next_buttons = region.get_by_role(
        "button", name=re.compile(r"下一页|下页|后一页|next", re.IGNORECASE)
    )
    if not await next_buttons.count():
        return False
    next_button = next_buttons.first
    before_text = await region.inner_text()
    before_count = await _data_item_count(region)
    if await next_button.is_disabled():
        return False
    await next_button.click()
    await page.wait_for_timeout(100)
    after_text = await region.inner_text()
    after_count = await _data_item_count(region)
    if isinstance(expected_after_count, tuple):
        after_count_ok = expected_after_count[0] <= after_count <= expected_after_count[1]
    else:
        after_count_ok = after_count == expected_after_count
    return (
        before_count == 10
        and after_count_ok
        and before_text != after_text
        and str(expected_total) in before_text + after_text
    )


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def basic():
        await reset_page(page)
        return await contains_each_any_texts(page, [
            ["智慧教学"], ["学期"], ["省", "省份"], ["市", "城市"],
            ["区", "区县"], ["整体概览"], ["产品活跃趋势"], ["区域分布"],
            ["学校明细", "学校使用明细"], ["预警"],
        ])
    await recorder.check("c01_information_organization", basic)

    async def overview_latest():
        await reset_page(page)
        await _select_value(page, "2025-2026学年第二学期")
        return await contains_texts(page, ["32", "28", "220", "87.5%", "80", "140"])
    await recorder.check("c02_detail_display", overview_latest)

    async def trend():
        await reset_page(page)
        return await contains_texts(
            page, ["产品活跃趋势", "总体", "教师", "学生"]
        ) and await _contains_chart(page)
    await recorder.check("c03_data_visualization", trend)

    async def regional_distribution():
        await reset_page(page)
        return await contains_texts(page, ["区域分布", "授权学校", "活跃学校", "活跃用户", "应用率"])
    await recorder.check("c04_data_visualization", regional_distribution)

    async def school_table():
        await reset_page(page)
        return await contains_each_any_texts(page, [
            ["学校明细", "学校使用明细"], ["学校名称", "学校"],
            ["省", "省份"], ["市", "城市"], ["区", "区县"], ["授权"],
            ["活跃用户"], ["应用状态", "授权状态", "学期有效"],
        ])
    await recorder.check("c05_lists_tables", school_table)

    async def expiry_table():
        await reset_page(page)
        await _open_alert(page, "产品到期预警")
        return await contains_texts(page, ["到期预警", "授权时间", "到期时间", "剩余", "逾期"])
    await recorder.check("c06_lists_tables", expiry_table)

    async def unused_table():
        await reset_page(page)
        await _open_alert(page, "产品未应用预警")
        return await contains_texts(page, ["未应用", "最近一次活跃", "授权"])
    await recorder.check("c07_lists_tables", unused_table)

    async def semester_switch():
        await reset_page(page)
        await _select_value(page, "2024-2025学年第一学期")
        return await contains_texts(page, ["252", "96", "156", "100%", "2024-2025学年第一学期"])
    await recorder.check("c08_search_filtering", semester_switch)

    async def province_city_options():
        await reset_page(page)
        await _select_value(page, "浙江省")
        return await contains_texts(page, ["杭州市", "宁波市", "8", "6", "47", "75%"])
    await recorder.check("c09_cross_region_linkage", province_city_options)

    async def city_district_options():
        await reset_page(page)
        await _select_value(page, "浙江省")
        await _select_value(page, "杭州市")
        return await contains_texts(page, ["西湖区", "余杭区", "4", "3", "23"])
    await recorder.check("c10_cross_region_linkage", city_district_options)

    async def district_filter():
        await reset_page(page)
        await _select_value(page, "浙江省")
        await _select_value(page, "杭州市")
        await _select_value(page, "西湖区")
        return await contains_texts(page, ["2", "1", "8", "文澜实验学校", "翠苑中学"])
    await recorder.check("c11_cross_region_linkage", district_filter)

    async def province_change_resets():
        await reset_page(page)
        await _select_value(page, "浙江省")
        await _select_value(page, "杭州市")
        await _select_value(page, "西湖区")
        await _select_value(page, "江苏省")
        text = await page.locator("body").inner_text()
        return (
            "南京市" in text
            and "苏州市" in text
            and not _contains_any_terms(text, ["杭州市", "西湖区", "余杭区"])
        )
    await recorder.check("c12_cross_region_linkage", province_change_resets)

    async def all_sections_share_filter():
        await reset_page(page)
        await _select_value(page, "2025-2026学年第二学期")
        await _select_value(page, "浙江省")
        text = await page.locator("body").inner_text()
        return all(
            token in text
            for token in ["整体概览", "产品活跃趋势", "区域分布", "学校明细", "未应用"]
        ) and "广东省" not in text
    await recorder.check("c13_cross_region_linkage", all_sections_share_filter)

    async def trend_switches():
        await reset_page(page)
        before = await page.locator("body").inner_text()
        await _select_value(page, "2024-2025学年第一学期")
        after = await page.locator("body").inner_text()
        return before != after and "2024-2025学年第一学期" in after
    await recorder.check("c14_search_filtering", trend_switches)

    async def region_levels():
        await reset_page(page)
        national = await contains_texts(page, ["省份", "区域分布"])
        await _select_value(page, "浙江省")
        provincial = await contains_texts(page, ["杭州市", "宁波市"])
        await _select_value(page, "杭州市")
        city = await contains_texts(page, ["西湖区", "余杭区"])
        return national and provincial and city
    await recorder.check("c15_cross_region_linkage", region_levels)

    async def drill_down():
        await reset_page(page)
        region = page.get_by_text("浙江省", exact=True)
        visible_regions = [
            region.nth(index)
            for index in range(await region.count())
            if await region.nth(index).is_visible()
        ]
        if not visible_regions:
            return False
        await visible_regions[-1].click()
        return await contains_texts(page, ["浙江省", "杭州市", "宁波市"])
    await recorder.check("c16_cross_region_linkage", drill_down)

    async def alert_switch():
        await reset_page(page)
        await _open_alert(page, "产品到期预警")
        expiry = await contains_texts(page, ["到期预警"])
        await _open_alert(page, "产品未应用预警")
        unused = await contains_texts(page, ["未应用"])
        return expiry and unused
    await recorder.check("c17_content_switching", alert_switch)

    async def unused_latest():
        await reset_page(page)
        await _open_alert(page, "产品未应用预警")
        return await contains_texts(
            page, ["4", "文澜实验学校", "鄞州新城学校", "金陵汇文学校", "海珠实验学校"]
        )
    await recorder.check("c18_search_filtering", unused_latest)

    async def unused_first_semester_empty():
        await reset_page(page)
        await _open_alert(page, "产品未应用预警")
        await _select_value(page, "2025-2026学年第一学期")
        return await contains_texts(page, ["0"]) and await contains_any_texts(
            page, ["没有未应用学校", "暂无未应用学校", "无未应用学校"]
        )
    await recorder.check("c19_search_filtering", unused_first_semester_empty)

    async def guangdong_expiry_empty():
        await reset_page(page)
        await _open_alert(page, "产品到期预警")
        await _select_value(page, "广东省")
        return (
            await contains_texts(page, ["0"])
            and await contains_any_texts(page, ["没有到期", "暂无到期", "无到期"])
            and not await contains_texts(page, ["文澜实验学校"])
        )
    await recorder.check("c20_search_filtering", guangdong_expiry_empty)

    async def pagination_school():
        await reset_page(page)
        return await _paginate_section(
            page,
            ["学校明细", "学校使用明细"],
            expected_total=32,
            expected_after_count=(1, 10),
        )
    await recorder.check("c23_page_navigation", pagination_school)

    async def pagination_alert():
        await reset_page(page)
        await _open_alert(page, "产品到期预警")
        return await _paginate_section(
            page,
            ["产品到期预警", "到期预警"],
            expected_total=16,
            expected_after_count=6,
            prefer_last_heading=True,
        )
    await recorder.check("c24_page_navigation", pagination_alert)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    await reset_page(page)
    manifest = [
        await capture(page, screenshot_dir, "desktop-dashboard", full_page=False),
        await capture(page, screenshot_dir, "desktop-dashboard-order", full_page=True),
    ]
    try:
        await _open_alert(page, "产品到期预警")
        manifest.append(await capture(page, screenshot_dir, "desktop-alert", full_page=False))
    except Exception:
        pass
    return manifest
