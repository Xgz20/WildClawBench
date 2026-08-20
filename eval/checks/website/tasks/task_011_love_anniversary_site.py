from __future__ import annotations

import re

try:
    from ..common import (
        CheckRecorder, capture, click_named, click_named_any, contains_any_texts,
        contains_texts, fill_any_named,
        reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, click_named_any, contains_any_texts,
        contains_texts, fill_any_named,
        reset_page,
    )


RUNTIME_KEYS = [
    "c01_information_organization", "c02_file_upload_and_download", "c03_information_organization",
    "c04_page_navigation", "c05_rule_settlement", "c06_lists_tables", "c07_content_editing",
    "c08_data_visualization", "c09_file_upload_and_download", "c10_file_upload_and_download",
    "c11_cross_region_linkage", "c12_detail_display", "c13_information_organization",
    "c14_content_editing", "c15_detail_display", "c16_operation_feedback",
    "c17_content_editing", "c18_lists_tables", "c19_form_validation", "c20_state_persistence",
    "c23_cross_region_linkage", "c24_file_upload_and_download", "c25_data_visualization",
]
VISUAL_KEYS = ["c21_visual_style", "c22_responsive_layout"]

EVAL = "/tmp_workspace_eval"


async def _setup(page, *, date: str = "2025-01-01") -> bool:
    await reset_page(page)
    try:
        if await contains_texts(
            page, ["首页", "纪念日", "旅行足迹", "心愿", "日常"]
        ) and await page.locator("[role='tab'], .tab, .tabs, nav, [role='tablist']").count():
            return True

        dates = page.locator('input[type="date"]')
        if await dates.count():
            try:
                await dates.first.fill(date)
            except Exception:
                pass

        names = page.locator('input[placeholder*="名字"], input[placeholder*="姓名"], input[placeholder*="Ta"]')
        if await names.count() < 2:
            names = page.locator('input[type="text"], input:not([type])')
        if await names.count() >= 2:
            await names.nth(0).fill("小满")
            await names.nth(1).fill("阿序")
        elif await names.count() == 1:
            await names.first.fill("小满")

        files = page.locator('input[type="file"]')
        if await files.count() >= 2:
            await files.nth(0).set_input_files(f"{EVAL}/avatar-xiaoman.jpg")
            await files.nth(1).set_input_files(f"{EVAL}/avatar-axu.jpg")

        for label in (
            "完成建档",
            "开始记录",
            "开始我们的故事",
            "进入首页",
            "保存资料",
            "继续",
            "确认",
        ):
            try:
                await click_named(page, label)
                if await contains_any_texts(page, ["首页", "纪念日", "旅行足迹"]):
                    return True
            except Exception:
                continue
        return await contains_any_texts(page, ["首页", "纪念日", "旅行足迹"])
    except Exception:
        return False


async def _tab(page, label: str) -> bool:
    for candidate in (label, f"{label}页", f"打开{label}", f"切换到{label}"):
        try:
            await click_named_any(page, [candidate, f"{candidate}（", f"{candidate}:"])
            await page.wait_for_timeout(100)
            return True
        except Exception:
            continue
    return False


async def _person(page, name: str) -> bool:
    try:
        await click_named_any(page, [name, f"切换{name}", f"选择{name}", f"{name}(当前)", f"{name}（"])
        return True
    except Exception:
        return False


async def _select_options_value(page, value: str) -> bool:
    selects = page.locator("select")
    for index in range(await selects.count()):
        options = [option.strip() for option in await selects.nth(index).locator("option").all_text_contents()]
        if any(option == value for option in options):
            await selects.nth(index).select_option(label=value)
            return True
        if any(value in option for option in options):
            await selects.nth(index).select_option(label=next(option for option in options if value in option))
            return True
    return False


async def _upload_file(page, filename: str, *, multiple: bool = False) -> bool:
    inputs = page.locator('input[type="file"]')
    if not await inputs.count():
        return False
    target = inputs.last
    if multiple:
        parts = [part.strip() for part in filename.split(",") if part.strip()]
        paths = [f"{EVAL}/{name}" for name in parts]
    else:
        paths = [f"{EVAL}/{filename}"]
    if not paths:
        return False
    await target.set_input_files(paths)
    return True


async def _travel_upload(page, filename: str, province: str = "浙江省", city: str = "杭州市") -> bool:
    if not await _tab(page, "旅行足迹"):
        return False
    await _person(page, "小满")
    try:
        dates = page.locator('input[type="date"]')
        if await dates.count():
            await dates.last.fill("2025-01-05")
    except Exception:
        pass

    select_ok = await _select_options_value(page, province)
    city_ok = await _select_options_value(page, city)
    if not (select_ok and city_ok):
        try:
            await fill_any_named(page, ["城市", "城市名称", "所在地", "拍摄城市"], city)
        except Exception:
            pass
    if not await _upload_file(page, filename):
        return False
    for label in ("上传照片", "添加旅行照片", "保存照片", "上传", "提交"):
        try:
            await click_named_any(page, [label, f"确定{label}", f"立即{label}"])
            return True
        except Exception:
            continue
    return True


async def _add_anniversary(page, name: str, repeat: str = "不重复") -> bool:
    if not await _tab(page, "纪念日"):
        return False
    try:
        await click_named_any(page, ["新增纪念日", "添加纪念日", "新建纪念日", "创建纪念日"])
        await fill_any_named(page, ["事件名称", "纪念日名称", "名称"], name)
        await fill_any_named(page, ["日期", "事件日期", "纪念日日期"], "2025-02-01")
        for label in (repeat, "每周重复", "每月重复", "每年重复", "不重复"):
            if await _select_options_value(page, label):
                break
        await page.wait_for_timeout(120)
        for label in ("保存纪念日", "添加", "创建", "提交", "确定", "保存"):
            try:
                await click_named_any(page, [label, f"保存{label}"])
                await page.wait_for_timeout(120)
                if await contains_any_texts(page, ["纪念日", "重复", "保存", "新增", "待办"]):
                    return True
            except Exception:
                continue
        return True
    except Exception:
        return False


async def _add_wish(page, title: str, description: str = "") -> bool:
    if not await _tab(page, "心愿"):
        return False
    try:
        await click_named_any(page, ["新增心愿", "添加心愿", "创建心愿"])
        await fill_any_named(page, ["心愿标题", "标题"], title)
        if description:
            await fill_any_named(page, ["描述", "心愿描述"], description)
        await click_named_any(page, ["保存心愿", "发布心愿", "提交", "新增"])
        return True
    except Exception:
        return False


async def _publish_daily(page, text: str = "今天一起做了晚饭", filenames: list[str] | None = None) -> bool:
    if not await _tab(page, "日常"):
        return False
    try:
        await click_named_any(page, ["发布日常", "发布动态", "新增日常", "写日常"])
        await fill_any_named(page, ["写点什么", "日常内容", "正文", "内容"], text)
        if filenames:
            await _upload_file(page, ",".join(filenames), multiple=True)
        for label in ("发布", "保存日常", "发布动态", "提交"):
            try:
                await click_named_any(page, [label])
                return True
            except Exception:
                continue
        return True
    except Exception:
        return False


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def guide():
        await reset_page(page)
        return (
            await contains_texts(page, ["恋爱", "开始日期", "名字", "头像"])
            and await page.locator('input[type="file"]').count() >= 2
            and not await contains_texts(page, ["首页", "纪念日", "旅行足迹", "心愿", "日常"])
        )
    await recorder.check("c01_information_organization", guide)

    async def profile():
        if not await _setup(page):
            return False
        imgs = page.locator("img")
        return (
            await contains_texts(page, ["小满", "阿序"])
            and await imgs.count() >= 2
        )
    await recorder.check("c02_file_upload_and_download", profile)

    async def days():
        if not await _setup(page):
            return False
        text = await page.locator("body").inner_text()
        return await contains_texts(page, ["已恋爱", "小满", "阿序"]) and bool(
            re.search(r"已恋爱[^0-9]{0,12}[1-9][0-9]*[^0-9]{0,4}天", text)
        )
    await recorder.check("c03_information_organization", days)

    async def tabs():
        if not await _setup(page):
            return False
        for label in ["首页", "纪念日", "旅行足迹", "心愿", "日常"]:
            if not await _tab(page, label):
                return False
        return True
    await recorder.check("c04_page_navigation", tabs)

    async def calendar_records():
        if not await _setup(page):
            return False
        await _person(page, "小满")
        await _add_anniversary(page, "半年纪念")
        await _person(page, "阿序")
        await _travel_upload(page, "travel-hangzhou-west-lake.jpg")
        await _person(page, "小满")
        await _add_wish(page, "看一场日出")
        await _person(page, "阿序")
        await _publish_daily(page, "今天也要好好生活")
        await _tab(page, "首页")
        return await contains_texts(
            page,
            ["4", "照片", "纪念日", "心愿", "日常", "小满", "阿序", "看一场日出", "今天也要好好生活"],
        )
    await recorder.check("c05_rule_settlement", calendar_records)

    async def anniversary_list():
        if not await _setup(page):
            return False
        await _add_anniversary(page, "过去的纪念日")
        return await contains_texts(page, ["过去的纪念日", "日期", "不重复"]) and await contains_any_texts(
            page, ["已过去", "还有", "即将"]
        )
    await recorder.check("c06_lists_tables", anniversary_list)

    async def weekly_anniversary():
        if not await _setup(page):
            return False
        ok = await _add_anniversary(page, "第一次旅行", "每周重复")
        return ok and await contains_texts(page, ["第一次旅行", "每周", "天"])
    await recorder.check("c07_content_editing", weekly_anniversary)

    async def map_structure():
        if not await _setup(page) or not await _tab(page, "旅行足迹"):
            return False
        paths = await page.locator("svg path").count()
        named_provinces = await page.locator(
            "svg path[data-name], svg path[aria-label], svg path title"
        ).count()
        return (
            await contains_texts(page, ["旅行足迹", "省份", "城市", "上传", "0"])
            and paths >= 30
            and named_provinces >= 30
        )
    await recorder.check("c08_data_visualization", map_structure)

    async def zhejiang_upload():
        if not await _setup(page) or not await _travel_upload(page, "travel-hangzhou-west-lake.jpg"):
            return False
        return await contains_texts(page, ["浙江", "杭州", "小满", "1"])
    await recorder.check("c09_file_upload_and_download", zhejiang_upload)

    async def shanghai_uploads():
        if not await _setup(page) or not await _tab(page, "旅行足迹"):
            return False
        await _person(page, "阿序")
        try:
            await fill_any_named(page, ["日期", "拍摄日期"], "2025-01-06")
            await fill_any_named(page, ["省份", "拍摄省份"], "上海市")
            await fill_any_named(page, ["城市", "城市名称", "拍摄城市"], "上海市")
            await _upload_file(page, "travel-shanghai-skyline.jpg,travel-shanghai-bund.jpg", multiple=True)
            await click_named_any(page, ["上传照片", "保存", "提交"])
        except Exception:
            return False
        return await contains_texts(page, ["上海", "阿序"]) and await page.locator(
            "img[src^='blob:'], img[src^='data:']"
        ).count() >= 2
    await recorder.check("c10_file_upload_and_download", shanghai_uploads)

    async def map_filter():
        if not await _setup(page):
            return False
        if not await _travel_upload(page, "travel-hangzhou-west-lake.jpg"):
            return False
        if not await _tab(page, "旅行足迹"):
            return False
        zhejiang = page.get_by_text("浙江省", exact=False)
        if await zhejiang.count():
            await zhejiang.first.click()
        filtered = await contains_texts(page, ["浙江", "杭州"]) and not await contains_texts(page, ["上海"])
        try:
            await click_named_any(page, ["查看全部", "全部", "重置", "清除筛选"])
        except Exception:
            pass
        return filtered and await contains_texts(page, ["浙江", "杭州"])
    await recorder.check("c11_cross_region_linkage", map_filter)

    async def photo_modal():
        if not await _setup(page) or not await _travel_upload(page, "travel-hangzhou-west-lake.jpg"):
            return False
        try:
            await page.locator("img").last.click()
        except Exception:
            return False
        return await contains_texts(page, ["杭州", "浙江", "小满"]) and await contains_any_texts(
            page, ["关闭", "×"]
        )
    await recorder.check("c12_detail_display", photo_modal)

    async def wishes_status():
        if not await _setup(page):
            return False
        await _add_wish(page, "已实现愿望")
        return await contains_texts(page, ["心愿", "待实现", "已实现"])
    await recorder.check("c13_information_organization", wishes_status)

    async def create_wish():
        if not await _setup(page):
            return False
        if not await _person(page, "阿序"):
            return False
        return await _add_wish(page, "去看极光", "冬天一起出发") and await contains_texts(
            page, ["去看极光", "阿序", "待实现"]
        )
    await recorder.check("c14_content_editing", create_wish)

    async def wish_detail():
        if not await _setup(page):
            return False
        if not await _add_wish(page, "去看极光", "冬天一起出发"):
            return False
        await _person(page, "阿序")
        try:
            await click_named_any(page, ["去看极光", "详情", "查看详情", "打开"])
        except AssertionError:
            return False
        return await contains_texts(page, ["去看极光", "冬天一起出发", "阿序", "待实现"]) and await contains_any_texts(
            page, ["关闭", "返回"]
        )
    await recorder.check("c15_detail_display", wish_detail)

    async def complete_wish():
        if not await _setup(page):
            return False
        if not await _add_wish(page, "去看极光", "冬天一起出发"):
            return False
        try:
            await click_named_any(page, ["去看极光", "详情"])
            await click_named_any(page, ["标记为已实现", "设为已实现", "已实现", "完成", "完成任务"])
        except Exception:
            return False
        return await contains_texts(page, ["已实现"]) and not await contains_texts(page, ["待实现 1"])
    await recorder.check("c16_operation_feedback", complete_wish)

    async def daily_publish():
        if not await _setup(page):
            return False
        if not await _person(page, "小满"):
            return False
        return (
            await _publish_daily(page)
            and await contains_texts(page, ["今天一起做了晚饭", "小满"])
            and await contains_any_texts(page, ["刚刚", "分钟前", "发布时间", "发布成功"])
        )
    await recorder.check("c17_content_editing", daily_publish)

    async def daily_timeline():
        if not await _setup(page):
            return False
        await _person(page, "小满")
        await _publish_daily(page, "小满的日常")
        await _person(page, "阿序")
        await _publish_daily(page, "阿序的日常")
        body = await page.locator("body").inner_text()
        return (
            await contains_texts(page, ["小满的日常", "阿序的日常", "小满", "阿序"])
            and body.find("阿序的日常") < body.find("小满的日常")
        )
    await recorder.check("c18_lists_tables", daily_timeline)

    async def validations():
        if not await _setup(page):
            return False
        await _tab(page, "旅行足迹")
        try:
            await click_named_any(page, ["上传照片", "提交", "保存"])
        except Exception:
            pass
        travel_error = await contains_any_texts(page, ["请选择照片", "请上传照片", "照片不能为空"])
        await _tab(page, "心愿")
        try:
            await click_named_any(page, ["新增心愿", "添加心愿"])
            await fill_any_named(page, ["描述", "心愿描述"], "只有描述")
            await click_named_any(page, ["保存心愿", "发布心愿", "提交"])
        except Exception:
            pass
        wish_error = await contains_any_texts(page, ["请输入标题", "标题不能为空", "标题必填"])
        await _tab(page, "日常")
        try:
            await click_named_any(page, ["发布日常", "发布动态", "新增日常"])
            await click_named_any(page, ["发布", "提交", "发布动态"])
        except Exception:
            pass
        daily_error = await contains_any_texts(page, ["正文和照片不能都为空", "请输入内容或选择照片", "至少填写正文或选择照片"])
        return travel_error and wish_error and daily_error
    await recorder.check("c19_form_validation", validations)

    async def persistence():
        if not await _setup(page):
            return False
        if not await _add_anniversary(page, "持久化纪念日"):
            return False
        await page.reload(wait_until="domcontentloaded")
        return (
            await contains_any_texts(page, ["小满", "阿序", "纪念日"])
            and await _tab(page, "纪念日")
            and await contains_any_texts(page, ["持久化纪念日"])
        )
    await recorder.check("c20_state_persistence", persistence)

    async def person_switch():
        if not await _setup(page):
            return False
        first = await _person(page, "小满")
        second = await _person(page, "阿序")
        return first and second and await contains_any_texts(page, ["小满", "阿序"])
    await recorder.check("c23_cross_region_linkage", person_switch)

    async def nine_photos():
        if not await _setup(page) or not await _tab(page, "日常"):
            return False
        await _person(page, "小满")
        files = [f"daily-{index:02d}-{name}.jpg" for index, name in enumerate(["coffee", "dinner", "flowers", "sunset", "plant", "books", "lake", "picnic", "cat"], 1)]
        before_images = await page.locator("img").count()
        if not await _publish_daily(page, "九张照片", files):
            return False
        nine_visible = (
            await contains_texts(page, ["九张照片", "小满"])
            and await page.locator("img").count() >= before_images + 9
        )
        await _tab(page, "日常")
        try:
            await click_named_any(page, ["发布日常", "发布动态", "新增日常", "写日常"])
            await _upload_file(
                page,
                ",".join(files + ["daily-10-cooking.jpg"]),
                multiple=True,
            )
        except Exception:
            return False
        too_many_rejected = await contains_any_texts(
            page, ["最多9张", "最多上传9张", "不能超过9张", "最多选择9张"]
        )
        return nine_visible and too_many_rejected
    await recorder.check("c24_file_upload_and_download", nine_photos)

    async def month_alignment():
        if not await _setup(page):
            return False
        await _tab(page, "首页")
        text = await page.locator("body").inner_text()
        return (
            all(f"{month}月" in text or f"{month:02d}" in text for month in range(1, 13))
            and await contains_any_texts(page, ["年度", "贡献日历"])
            and await page.locator("[data-date], [role='gridcell'], .calendar-cell").count() >= 365
        )
    await recorder.check("c25_data_visualization", month_alignment)
    return recorder.results


async def capture_visual(page, screenshot_dir):
    if not await _setup(page):
        await reset_page(page)
    manifest = [await capture(page, screenshot_dir, "desktop-home", full_page=False)]
    try:
        await _tab(page, "旅行足迹")
        manifest.append(await capture(page, screenshot_dir, "travel-map", full_page=False))
    except Exception:
        pass
    await page.set_viewport_size({"width": 375, "height": 812})
    if not await _setup(page):
        await reset_page(page, clear_storage=False)
    manifest.append(await capture(page, screenshot_dir, "mobile-home", full_page=False))
    try:
        await _tab(page, "旅行足迹")
        manifest.append(await capture(page, screenshot_dir, "mobile-travel", full_page=False))
    except Exception:
        pass
    return manifest
