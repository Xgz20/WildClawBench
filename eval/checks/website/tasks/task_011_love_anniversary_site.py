from __future__ import annotations

import re

try:
    from ..common import (
        CheckRecorder, capture, click_named, contains_texts, fill_any_named,
        reset_page,
    )
except ImportError:
    from common import (
        CheckRecorder, capture, click_named, contains_texts, fill_any_named,
        reset_page,
    )


RUNTIME_KEYS = [
    "criterion_01_basic_content", "criterion_02_personalization_settings", "criterion_03_data_visualization",
    "criterion_04_page_navigation", "criterion_05_data_visualization", "criterion_06_lists_and_tables",
    "criterion_07_content_creation_and_editing", "criterion_08_data_visualization", "criterion_09_file_upload_and_download",
    "criterion_10_file_upload_and_download", "criterion_11_cross_section_coordination", "criterion_12_modal_and_overlay",
    "criterion_13_information_organization", "criterion_14_content_creation_and_editing", "criterion_15_modal_and_overlay",
    "criterion_16_operation_feedback", "criterion_17_content_creation_and_editing", "criterion_18_lists_and_tables",
    "criterion_19_form_filling_and_validation", "criterion_20_state_persistence", "criterion_23_personalization_settings",
    "criterion_24_file_upload_and_download", "criterion_25_data_visualization",
]
VISUAL_KEYS = ["criterion_21_visual_style", "criterion_22_responsive_layout"]

EVAL = "/tmp_workspace_eval"


async def _setup(page, *, date: str = "2025-01-01") -> bool:
    await reset_page(page)
    try:
        dates = page.locator('input[type="date"]')
        if await dates.count():
            await dates.first.fill(date)
        await fill_any_named(page, ["小满", "第一个人的名字", "姓名 1", "名字 1"], "小满")
        await fill_any_named(page, ["阿序", "第二个人的名字", "姓名 2", "名字 2"], "阿序")
        files = page.locator('input[type="file"]')
        if await files.count() >= 2:
            await files.nth(0).set_input_files(f"{EVAL}/avatar-xiaoman.jpg")
            await files.nth(1).set_input_files(f"{EVAL}/avatar-axu.jpg")
        for label in ("完成建档", "开始我们的故事", "进入首页", "保存资料"):
            try:
                await click_named(page, label)
                return True
            except Exception:
                continue
    except Exception:
        return False
    return False


async def _tab(page, label: str) -> bool:
    for candidate in (label, f"{label}页", f"打开{label}"):
        try:
            await click_named(page, candidate)
            await page.wait_for_timeout(100)
            return True
        except Exception:
            continue
    return False


async def _person(page, name: str) -> bool:
    try:
        await click_named(page, name)
        return True
    except Exception:
        return False


async def _upload_file(page, filename: str, *, multiple: bool = False) -> bool:
    inputs = page.locator('input[type="file"]')
    if not await inputs.count():
        return False
    target = inputs.last
    paths = [f"{EVAL}/{filename}"] if not multiple else [f"{EVAL}/{name}" for name in filename.split(",")]
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
        selects = page.locator("select")
        for index in range(await selects.count()):
            options = await selects.nth(index).locator("option").all_text_contents()
            if province in options:
                await selects.nth(index).select_option(label=province)
            if city in options:
                await selects.nth(index).select_option(label=city)
        await fill_any_named(page, ["城市", "城市名称"], city)
        await _upload_file(page, filename)
        for label in ("上传照片", "添加旅行照片", "保存照片"):
            try:
                await click_named(page, label)
                return True
            except Exception:
                continue
    except Exception:
        return False
    return False


async def _add_anniversary(page, name: str, repeat: str = "不重复") -> bool:
    if not await _tab(page, "纪念日"):
        return False
    try:
        await click_named(page, "新增纪念日")
        await fill_any_named(page, ["事件名称", "纪念日名称", "名称"], name)
        await fill_any_named(page, ["日期", "事件日期"], "2025-02-01")
        for label in (repeat, "保存纪念日", "添加"):
            try:
                await click_named(page, label)
                if label != repeat:
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


async def _add_wish(page, title: str, description: str = "") -> bool:
    if not await _tab(page, "心愿"):
        return False
    try:
        await click_named(page, "新增心愿")
        await fill_any_named(page, ["心愿标题", "标题"], title)
        if description:
            await fill_any_named(page, ["描述", "心愿描述"], description)
        await click_named(page, "保存心愿")
        return True
    except Exception:
        return False


async def _publish_daily(page, text: str = "今天一起做了晚饭", filenames: list[str] | None = None) -> bool:
    if not await _tab(page, "日常"):
        return False
    try:
        await click_named(page, "发布日常")
        await fill_any_named(page, ["写点什么", "日常内容", "正文"], text)
        if filenames:
            await _upload_file(page, ",".join(filenames), multiple=True)
        for label in ("发布", "保存日常"):
            try:
                await click_named(page, label)
                return True
            except Exception:
                continue
    except Exception:
        return False
    return False


async def run(page, screenshot_dir):
    recorder = CheckRecorder(page, screenshot_dir)

    async def guide():
        await reset_page(page)
        return await contains_texts(page, ["双人", "恋爱", "开始日期", "头像", "小满", "阿序"])
    await recorder.check("criterion_01_basic_content", guide)

    async def profile():
        if not await _setup(page):
            return False
        imgs = page.locator("img")
        return await contains_texts(page, ["小满", "阿序"]) and await imgs.count() >= 2
    await recorder.check("criterion_02_personalization_settings", profile)

    async def days():
        if not await _setup(page):
            return False
        text = await page.locator("body").inner_text()
        return "已恋爱" in text and bool(re.search(r"已恋爱[^0-9]{0,8}[1-9][0-9]*", text))
    await recorder.check("criterion_03_data_visualization", days)

    async def tabs():
        if not await _setup(page):
            return False
        for label in ["首页", "纪念日", "旅行足迹", "心愿", "日常"]:
            if not await _tab(page, label):
                return False
        return True
    await recorder.check("criterion_04_page_navigation", tabs)

    async def calendar_records():
        if not await _setup(page):
            return False
        await _add_anniversary(page, "半年纪念")
        await _travel_upload(page, "travel-hangzhou-west-lake.jpg")
        await _add_wish(page, "看一场日出")
        await _publish_daily(page, "今天也要好好生活")
        await _tab(page, "首页")
        return await contains_texts(page, ["日历", "记录", "看一场日出", "今天也要好好生活"])
    await recorder.check("criterion_05_data_visualization", calendar_records)

    async def anniversary_list():
        if not await _setup(page):
            return False
        await _add_anniversary(page, "过去的纪念日")
        return await contains_texts(page, ["纪念日", "过去", "不重复", "日期"])
    await recorder.check("criterion_06_lists_and_tables", anniversary_list)

    async def weekly_anniversary():
        if not await _setup(page):
            return False
        ok = await _add_anniversary(page, "第一次旅行", "每周重复")
        return ok and await contains_texts(page, ["第一次旅行", "每周", "倒计时"])
    await recorder.check("criterion_07_content_creation_and_editing", weekly_anniversary)

    async def map_structure():
        if not await _setup(page) or not await _tab(page, "旅行足迹"):
            return False
        paths = await page.locator("svg path").count()
        return paths >= 10 and await contains_texts(page, ["旅行足迹", "上传", "省份", "城市", "0"])
    await recorder.check("criterion_08_data_visualization", map_structure)

    async def zhejiang_upload():
        if not await _setup(page) or not await _travel_upload(page, "travel-hangzhou-west-lake.jpg"):
            return False
        return await contains_texts(page, ["浙江", "杭州", "小满", "1 个省份", "1 个城市"])
    await recorder.check("criterion_09_file_upload_and_download", zhejiang_upload)

    async def shanghai_uploads():
        if not await _setup(page) or not await _tab(page, "旅行足迹"):
            return False
        await _person(page, "阿序")
        try:
            await fill_any_named(page, ["城市", "城市名称"], "上海市")
            await _upload_file(page, "travel-shanghai-skyline.jpg,travel-shanghai-bund.jpg", multiple=True)
            await click_named(page, "上传照片")
        except Exception:
            return False
        text = await page.locator("body").inner_text()
        return text.count("上海") >= 2 and "阿序" in text
    await recorder.check("criterion_10_file_upload_and_download", shanghai_uploads)

    async def map_filter():
        if not await _setup(page) or not await _travel_upload(page, "travel-hangzhou-west-lake.jpg"):
            return False
        await _tab(page, "旅行足迹")
        zhejiang = page.get_by_text("浙江省", exact=True)
        if await zhejiang.count():
            await zhejiang.first.click()
        filtered = await contains_texts(page, ["浙江", "筛选", "杭州"])
        try:
            await click_named(page, "查看全部")
        except Exception:
            pass
        return filtered
    await recorder.check("criterion_11_cross_section_coordination", map_filter)

    async def photo_modal():
        if not await _setup(page) or not await _travel_upload(page, "travel-hangzhou-west-lake.jpg"):
            return False
        try:
            await page.locator("img").last.click()
        except Exception:
            return False
        return await contains_texts(page, ["杭州", "浙江", "小满", "关闭"])
    await recorder.check("criterion_12_modal_and_overlay", photo_modal)

    async def wishes_status():
        if not await _setup(page):
            return False
        await _add_wish(page, "已实现愿望")
        return await contains_texts(page, ["待实现", "已实现", "心愿"])
    await recorder.check("criterion_13_information_organization", wishes_status)

    async def create_wish():
        if not await _setup(page) or not await _person(page, "阿序"):
            return False
        return await _add_wish(page, "去看极光", "冬天一起出发") and await contains_texts(page, ["去看极光", "阿序", "待实现"])
    await recorder.check("criterion_14_content_creation_and_editing", create_wish)

    async def wish_detail():
        if not await _setup(page) or not await _add_wish(page, "去看极光", "冬天一起出发"):
            return False
        try:
            await click_named(page, "去看极光")
        except Exception:
            return False
        return await contains_texts(page, ["去看极光", "冬天一起出发", "阿序", "待实现", "关闭"])
    await recorder.check("criterion_15_modal_and_overlay", wish_detail)

    async def complete_wish():
        if not await _setup(page) or not await _add_wish(page, "去看极光", "冬天一起出发"):
            return False
        try:
            await click_named(page, "去看极光")
            await click_named(page, "标记为已实现")
        except Exception:
            return False
        return await contains_texts(page, ["已实现"]) and not await contains_texts(page, ["待实现 1"])
    await recorder.check("criterion_16_operation_feedback", complete_wish)

    async def daily_publish():
        if not await _setup(page) or not await _person(page, "小满"):
            return False
        return await _publish_daily(page) and await contains_texts(page, ["今天一起做了晚饭", "小满"])
    await recorder.check("criterion_17_content_creation_and_editing", daily_publish)

    async def daily_timeline():
        if not await _setup(page):
            return False
        await _publish_daily(page, "小满的日常")
        await _person(page, "阿序")
        await _publish_daily(page, "阿序的日常")
        return await contains_texts(page, ["小满的日常", "阿序的日常", "小满", "阿序"])
    await recorder.check("criterion_18_lists_and_tables", daily_timeline)

    async def validations():
        if not await _setup(page):
            return False
        await _tab(page, "旅行足迹")
        try:
            await click_named(page, "上传照片")
        except Exception:
            pass
        travel_error = await contains_texts(page, ["照片", "日期", "省份", "城市", "请输入"])
        await _tab(page, "心愿")
        try:
            await click_named(page, "新增心愿")
            await fill_any_named(page, ["描述", "心愿描述"], "只有描述")
            await click_named(page, "保存心愿")
        except Exception:
            pass
        wish_error = await contains_texts(page, ["标题", "不能为空", "请输入"])
        await _tab(page, "日常")
        try:
            await click_named(page, "发布日常")
            await click_named(page, "发布")
        except Exception:
            pass
        daily_error = await contains_texts(page, ["正文", "照片", "不能为空", "请输入"])
        return travel_error and wish_error and daily_error
    await recorder.check("criterion_19_form_filling_and_validation", validations)

    async def persistence():
        if not await _setup(page) or not await _add_anniversary(page, "持久化纪念日"):
            return False
        await page.reload(wait_until="domcontentloaded")
        return await contains_texts(page, ["小满", "阿序"]) and await _tab(page, "纪念日") and await contains_texts(page, ["持久化纪念日"])
    await recorder.check("criterion_20_state_persistence", persistence)

    async def person_switch():
        if not await _setup(page):
            return False
        first = await _person(page, "小满")
        second = await _person(page, "阿序")
        return first and second and await contains_texts(page, ["小满", "阿序"])
    await recorder.check("criterion_23_personalization_settings", person_switch)

    async def nine_photos():
        if not await _setup(page) or not await _tab(page, "日常"):
            return False
        await _person(page, "小满")
        files = [f"daily-{index:02d}-{name}.jpg" for index, name in enumerate(["coffee", "dinner", "flowers", "sunset", "plant", "books", "lake", "picnic", "cat"], 1)]
        if not await _publish_daily(page, "九张照片", files):
            return False
        return await contains_texts(page, ["九张照片", "小满"])
    await recorder.check("criterion_24_file_upload_and_download", nine_photos)

    async def month_alignment():
        if not await _setup(page):
            return False
        await _tab(page, "首页")
        text = await page.locator("body").inner_text()
        return all(month in text for month in [f"{index}月" for index in range(1, 13)]) and await page.locator("[data-date], [role='gridcell'], .calendar-cell").count() >= 28
    await recorder.check("criterion_25_data_visualization", month_alignment)
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
    return manifest
