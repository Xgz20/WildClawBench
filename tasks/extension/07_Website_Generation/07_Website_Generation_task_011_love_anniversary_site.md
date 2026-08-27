---
id: 07_Website_Generation_task_011_love_anniversary_site
name: 双人恋爱纪念站
category: 07_Website_Generation
sub_category: 关系与纪念
task_type: 恋爱纪念与生活记录网站
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 双人恋爱纪念站

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

我想做一个只属于两个人的恋爱纪念网站，把我们一起经历的重要日子、旅行照片、心愿和日常都收在一个地方。网站要能区分两个人：两个人都可以设置自己的名字和头像。页面右上角可以随时切换当前记录者，新增纪念日、上传照片、添加心愿和发布日常都会记在当前记录者名下。

第一次打开网站时，先引导完成建档，填写恋爱开始日期和两个人的名字，也可以上传各自头像。完成后进入首页，首页突出展示两个人的头像、名字和“已恋爱多少天”。下面放一个类似 GitHub 贡献日历的年度图表，按照片上传、纪念日和心愿新增、日常发布的实际时间统计次数。同一天新增的内容越多，颜色越深；点击日期可以查看当天新增了哪些内容、共有多少条以及分别是谁留下的。

顶部页签包括首页、纪念日、旅行足迹、心愿和日常。纪念日页面像 Days Matter：每张卡片显示事件名称、日期、重复规则，并根据日期显示已经过去多久或者还有多久到来。可以新增纪念日，填写名称和日期，并选择不重复、每周、每月或每年重复。列表先显示即将到来的纪念日，再显示已经发生的纪念日，两组内都按距离今天由近到远排序；重复事件按下一次发生日期计算。

旅行足迹页面展示完整、可辨认的标准中国省级行政区地图，省级边界和位置关系应准确，不能用矩形网格、方块或散点位置代替。去过且上传过照片的省份会直接点亮对应的行政区地图块，同一省份的照片越多，地图块颜色越深，不能用地图旁边的色块或标签代替。省名如果展示，需要位于对应行政区内，或者在悬停、点击时显示，不能与地图错位。地图旁边显示已经走过多少个省份和多少个城市，点击省份地图块后只查看该省的照片。照片支持单张或批量上传，上传时填写拍摄日期、省份和城市，记录者使用页面右上角当前记录者。地图下方铺开全部旅行照片；点击单张照片可以放大，并看到日期、地点和上传者等详细信息。

心愿页面分别显示待实现和已实现的数量。可以添加心愿，填写标题和描述，记录者使用页面右上角当前记录者；可以打开详情查看完整内容，也可以把心愿标记为已实现。

日常页面做成类似朋友圈的时间线，文字和图片可以单独或一起发布，每次最多选择九张照片，并以朋友圈式九宫格或等价的多图布局展示。两个人的记录按发布时间从新到旧排列，清楚标出发布人和发布时间。

整体风格希望可爱、甜蜜但不幼稚，可以使用柔和的粉色、奶油色、圆润卡片和少量爱心或手绘感装饰。首页的贡献日历要一眼能看出哪天记录多、哪天少，深浅代表什么要有说明；右上角要能看清当前是谁在记录，两个人都好认、好切换，手机上可以收缩成头像。桌面端要让地图、统计和照片区层次清楚，手机上也要方便切换页签、填写表单、浏览照片和查看详情。

## Expected Behavior

Agent 应按 Prompt 完成页面内容、交互和视觉要求。

评分由 Playwright 运行时检查（内容与交互类评分点）和基于截图的视觉判分（视觉与布局类评分点）共同完成；每个评分点按“预设状态 → 操作 → 期望结果”独立判定。

## Grading Criteria

本题仅使用 LLM Judge 评分。评分点全部放在 `## LLM Judge Rubric` 中，每个 Criterion 只有 1.0 和 0.0 两档：非视觉类评分点由 Playwright 检查器按 key 给出运行时结果，视觉类评分点由 LLM 依据截图判定。

## Automated Checks

## LLM Judge Rubric

说明：

- 每个 Criterion 都按同一结构书写：`预设状态`、`操作`、`期望结果`。
- `Score 1.0` 表示符合预设状态、操作要求，且结果与期望结果一致。
- `Score 0.0` 表示任一部分不符合。
- 未特别说明时，页面在 1440×900 桌面视口打开；标注 375×812 的评分点在手机视口检查。

### Criterion 1: 首次打开网站 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0384)

预设状态：浏览器中没有保存过该网站的数据

操作：首次打开网站

期望结果：先显示双人建档引导，可以填写恋爱开始日期和两个人的名字，并分别提供头像上传入口；尚未完成必填项时不会直接进入空白主页。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 填写开始日期 (key: c02_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0384)

预设状态：停留在首次建档引导

操作：填写开始日期，将两个人命名为“小满”和“阿序”，分别上传 /tmp_workspace_eval/avatar-xiaoman.jpg 与 /tmp_workspace_eval/avatar-axu.jpg 后完成建档

期望结果：进入首页并同时显示小满和阿序的名字与各自头像；两个人的资料彼此独立，没有被同一个名字或头像覆盖。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看首页主视觉区 (key: c03_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0384)

预设状态：已用一个早于今天的日期完成建档

操作：查看首页主视觉区

期望结果：首页并排或成对展示两个人的头像和名字，中间醒目显示“已恋爱”以及根据开始日期计算的天数，天数不是固定占位值。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 依次切换首页、纪念日、旅行足迹、心愿和日常 (key: c04_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0384)

预设状态：已完成建档并位于首页

操作：依次切换首页、纪念日、旅行足迹、心愿和日常

期望结果：顶部能找到五个页签，每次切换都显示对应页面的独立内容，页面标题或当前内容与所选页签一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 在同一天完成以下操作 (key: c05_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0384)

预设状态：已用“小满”和“阿序”完成建档，纪念日、旅行照片、心愿和日常均为空

操作：在同一天完成以下操作：切换为小满，新增事件日期为未来 30 天、名称为“半年纪念”的不重复纪念日；切换为阿序，选择过去 30 天的拍摄日期、浙江省杭州市并上传 /tmp_workspace_eval/travel-hangzhou-west-lake.jpg；切换为小满，新增心愿“看一场日出”；切换为阿序，发布日常“今天也要好好生活”。随后返回首页，点击今天的年度记录日历格，并检查日历上其它日期格历格

期望结果：今天的日期格显示为有记录，点击后详情明确显示共 4 条，包含照片、纪念日、心愿和日常各 1 条，并显示小满 2 条、阿序 2 条；日历上其它日期格没有因为照片的拍摄日期或纪念日的事件日期而出现记录——按业务日期归档到别的格子、把新增日期算错，都不算通过。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 打开纪念日页面查看卡片 (key: c06_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0384)

预设状态：已存在一个过去的不重复纪念日和一个未来或每年重复的纪念日

操作：打开纪念日页面查看卡片

期望结果：每张卡片显示事件名称、日期和重复规则；过去事件显示已过去多久，未来或下一次重复事件显示还有多久到来；列表先排即将到来的事件，再排已经发生的事件，同组按距离今天的时间远近排列。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 新增名为“第一次旅行”的纪念日 (key: c07_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0384)

预设状态：已打开纪念日页面

操作：新增名为“第一次旅行”的纪念日，选择一个日期和“每周重复”

期望结果：新增成功后出现“第一次旅行”卡片，显示所选日期、每周重复以及按下一次发生日期计算的倒计时或已经过去时间，并按当前记录者归属。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 打开旅行足迹页面 (key: c08_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.0384)

预设状态：已完成建档但还没有旅行照片

操作：打开旅行足迹页面，以地图轮廓的位置为准，依次悬停或点击实际位于浙江、上海、北京、广东的省级行政区地图块，观察地图反馈的省名

期望结果：页面显示完整、可辨认的标准中国省级行政区地图，省级边界和位置关系清楚，不是矩形网格、方块或散点近似图；每个可交互区域就是对应的省级行政区地图块，所有抽查区域悬停或点击后显示的省名都必须与该区域实际代表的省级行政区一致，不得出现点的是浙江却反馈上海这类错配，也不能用旁边的文字标签、孤立点位或色块代替真实省级轮廓。省名可以在悬停、点击或其他等价交互反馈中显示，不要求全部永久印在地图上；同时显示旅行照片上传入口以及省份数和城市数统计，空状态下两个统计均为 0，所有省级地图块均为未点亮状态。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 先在右上角切换当前记录者为“小满” (key: c09_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0384)

预设状态：旅行足迹还没有照片

操作：先在右上角切换当前记录者为“小满”，填写日期、浙江省和杭州市，单张上传 /tmp_workspace_eval/travel-hangzhou-west-lake.jpg

期望结果：上传后浙江省真实行政区轮廓本身被点亮，不是只点亮旁边的标签或色块；统计更新为走过 1 个省份和 1 个城市，照片墙出现该图片并显示杭州市与小满。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 先在右上角切换当前记录者为“阿序” (key: c10_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0384)

预设状态：旅行足迹中已有一张浙江省照片

操作：先在右上角切换当前记录者为“阿序”，填写拍摄日期，省份选择上海市、城市填写上海市，一次上传 /tmp_workspace_eval/travel-shanghai-skyline.jpg 与 /tmp_workspace_eval/travel-shanghai-bund.jpg

期望结果：两张图片作为两条独立照片记录加入照片墙，均保留阿序、所选日期和上海市信息；省份和城市统计同步增加，不会只保留批量中的一张。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 点击中国地图中浙江省的真实行政区地图块 (key: c11_cross_region_linkage, primary: interaction_function, secondary: cross_region_linkage, weight: 0.0384)

预设状态：当前记录者任意，已分别上传 /tmp_workspace_eval/travel-hangzhou-west-lake.jpg（拍摄日期任填，浙江省杭州市）和 /tmp_workspace_eval/travel-shanghai-bund.jpg（拍摄日期任填，上海市）各一张

操作：点击中国地图中浙江省的真实行政区地图块，再切换为查看全部

期望结果：点击浙江省轮廓后照片墙只显示浙江省照片，并清楚提示当前筛选范围；查看全部后恢复两个省份的照片。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 点击该照片 (key: c12_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0384)

预设状态：当前记录者为小满，已填写拍摄日期、浙江省杭州市并上传 /tmp_workspace_eval/travel-hangzhou-west-lake.jpg

操作：点击该照片

期望结果：出现可关闭的大图详情，清楚显示放大的图片、拍摄日期、浙江省杭州市和上传者小满。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 打开心愿页面 (key: c13_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0384)

预设状态：心愿中同时存在待实现和已实现项目

操作：打开心愿页面

期望结果：页面分别显示待实现和已实现数量，心愿卡片能区分两种状态，并显示标题和该心愿各自的记录者。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 先在右上角切换当前记录者为“阿序” (key: c14_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0384)

预设状态：已打开心愿页面

操作：先在右上角切换当前记录者为“阿序”，添加标题“去看极光”、描述“冬天一起出发”的心愿

期望结果：列表新增待实现的“去看极光”，显示当前记录者阿序，待实现数量增加 1。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 打开该心愿的详情 (key: c15_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0384)

预设状态：已存在带描述的心愿“去看极光”

操作：打开该心愿的详情

期望结果：详情中完整显示标题、描述“冬天一起出发”、记录者和当前实现状态，并提供关闭方式。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 将该心愿标记为已实现 (key: c16_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0384)

预设状态：“去看极光”处于待实现状态

操作：将该心愿标记为已实现

期望结果：心愿状态立即变为已实现，待实现数量减少 1、已实现数量增加 1，项目不会同时出现在两种状态中。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 先在右上角切换当前记录者为“小满” (key: c17_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0384)

预设状态：已打开日常页面

操作：先在右上角切换当前记录者为“小满”，发布“今天一起做了晚饭”

期望结果：时间线顶部出现这条完整文字，同时显示小满的名字或头像和发布时间，页面给出发布成功的可见结果。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 18: 浏览日常时间线 (key: c18_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0384)

预设状态：已完成双人建档；当前记录者为小满，发布一条正文“周末小记”并附 /tmp_workspace_eval/daily-01-coffee.jpg、/tmp_workspace_eval/daily-02-dinner.jpg、/tmp_workspace_eval/daily-03-flowers.jpg、/tmp_workspace_eval/daily-04-sunset.jpg、/tmp_workspace_eval/daily-05-plant.jpg、/tmp_workspace_eval/daily-06-books.jpg、/tmp_workspace_eval/daily-07-lake.jpg、/tmp_workspace_eval/daily-08-picnic.jpg、/tmp_workspace_eval/daily-09-cat.jpg 九张照片的日常；随后切换为阿序，发布一条仅正文“今天也要好好生活”的日常

操作：浏览日常时间线

期望结果：日常按时间串流排列，较新的“今天也要好好生活”排在前面；每条都显示正文、对应记录者和时间，两个人的内容不会混淆作者；九张照片的那条以朋友圈式九宫格或等价的多图布局展示，九张都在。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 19: 分别打开旅行照片、心愿和日常的新增表单 (key: c19_form_validation, primary: interaction_function, secondary: form_validation, weight: 0.0384)

预设状态：已完成双人建档

操作：分别打开旅行照片、心愿和日常的新增表单，确认表单沿用右上角当前记录者；旅行照片表单不选照片直接提交，心愿表单只填写描述不填写标题提交，日常表单在正文和照片都为空时提交

期望结果：三个表单都沿用右上角当前记录者，不再要求重复选择作者；旅行照片缺照片、心愿缺标题、日常正文和照片都为空时分别给出中文提示且不生成记录。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 20: 刷新页面后重新查看五个页签 (key: c20_state_persistence, primary: interaction_function, secondary: state_persistence, weight: 0.0384)

预设状态：已设置双人资料，并新增纪念日、旅行照片、心愿和日常各至少一条

操作：刷新页面后重新查看五个页签

期望结果：不再要求重新建档；两个人的资料、恋爱开始日期以及新增的纪念日、旅行照片信息、心愿和日常都仍然存在。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 21: 观察首页及旅行足迹页面 (key: c21_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0384)

预设状态：在 1440×900 桌面视口打开已建档的网站

操作：观察首页及旅行足迹页面

期望结果：整体呈现可爱甜蜜但不过分幼稚的风格，柔和粉色与奶油色、圆润卡片和少量爱心或手绘装饰协调统一；首页贡献日历放在独立卡片中，格子颜色由浅到深表达记录多少，并配有说明深浅含义的图例；右上角能看出当前记录者是谁，选中与未选中有可见的状态区别；地图、统计和照片区层次清楚。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 22: 切换页签并查看旅行上传表单、照片墙和详情 (key: c22_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0384)

预设状态：在 375×812 手机视口打开已建档的网站；已填写拍摄日期、浙江省杭州市并上传 /tmp_workspace_eval/travel-hangzhou-west-lake.jpg 一张（视口 375×812）

操作：切换页签并查看旅行上传表单、照片墙和详情

期望结果：页面适配窄屏且无横向滚动，五个页签仍可操作，表单控件、照片、主要按钮和详情内容没有被截断。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 23: 点击右上角两个人的头像或名字 (key: c23_cross_region_linkage, primary: interaction_function, secondary: cross_region_linkage, weight: 0.0384)

预设状态：已完成双人建档并停留在任一新增内容页面

操作：点击右上角两个人的头像或名字，在小满与阿序之间来回切换

期望结果：右上角能明确看出当前记录者是谁，切换后选中状态随之变化；旅行照片、心愿和日常的新增表单都沿用新的当前记录者，提交后的记录作者与切换结果一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 24: 切换右上角当前记录者为小满 (key: c24_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0384)

预设状态：已完成双人建档并打开日常页面

操作：切换右上角当前记录者为小满，填写一段文字，选择 /tmp_workspace_eval/daily-01-coffee.jpg、/tmp_workspace_eval/daily-02-dinner.jpg、/tmp_workspace_eval/daily-03-flowers.jpg、/tmp_workspace_eval/daily-04-sunset.jpg、/tmp_workspace_eval/daily-05-plant.jpg、/tmp_workspace_eval/daily-06-books.jpg、/tmp_workspace_eval/daily-07-lake.jpg、/tmp_workspace_eval/daily-08-picnic.jpg 与 /tmp_workspace_eval/daily-09-cat.jpg 后发布；随后再尝试把 /tmp_workspace_eval/daily-10-cooking.jpg 与前九张一起选择并发布

期望结果：日常发布成功，时间线中的这条记录显示小满、正文和 9 张照片；照片以朋友圈式九宫格或等价多图布局展示，尝试选择超过 9 张时有中文提示且不会多传。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 25: 对照每个月份标题与下方日期格 (key: c25_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.0384)

预设状态：已完成建档并进入首页，年度贡献日历完整可见

操作：对照每个月份标题与下方日期格，重点查看 1 月 1 日以及相邻月份交界处

期望结果：1 月至 12 月的月份标题分别对齐该月 1 日所在的周列，月份位置由真实日期计算；标题不会脱离日期格后被简单等距均分，也不会明显错位到前一个或后一个月份。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 26: 通读首页和地图、照片墙、心愿等各区域 (key: c26_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.04)

预设状态：已完成双人建档，首页可见已恋爱天数；已分别上传 /tmp_workspace_eval/travel-hangzhou-west-lake.jpg（浙江省杭州市）和 /tmp_workspace_eval/travel-shanghai-bund.jpg（上海市）各一张

操作：通读首页和地图、照片墙、心愿等各区域，把页面展示的每一个数字连同名目记下来

期望结果：页面展示哪些数字不作要求；但凡展示出来的，都必须与建档信息和已有记录推算一致——已恋爱天数必须与开始日期和当天日期算得上，走过的省份、城市数必须与照片记录对得上——页面各处的数字之间也不得互相矛盾。出现任何一处矛盾，本条不通过。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_011_love_anniversary_site

## Skills

## Env

## Warmup
