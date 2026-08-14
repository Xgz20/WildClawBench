---
id: 07_Website_Generation_task_009_smart_teaching_dashboard
name: 智慧教学数据看板
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 数据分析看板
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 智慧教学数据看板

## Prompt

请在 /tmp_workspace 下从空目录创建一个可运行的中文智慧教学数据看板项目。项目根目录需要提供 package.json，并支持 npm install、npm run build，以及 npm run start -- --host 127.0.0.1 --port 4173 启动网站。不要接入真实网络请求，也不要使用需要联网才能显示的图片、字体或外部数据。

请帮我做一个智慧教学产品的数据分析看板，主要给运营和管理人员查看各地学校的产品授权和使用情况，也方便及时找到需要跟进的学校。

所需数据都放在 `/tmp_workspace` 目录中，请直接使用。

看板顶部可以按学期、省、市、区筛选。省、市、区要逐级联动，选择上一级后，下一级只显示对应地区；切换筛选条件后，页面中与当前范围相关的指标、图表和学校明细一起更新，并能看出当前查看的是哪个学期和地区。

整体概览展示授权学校数、活跃学校数、活跃用户数和学校应用率，同时能看出教师、学生各自的活跃人数。产品活跃趋势用图表展示所选学期内的变化，既能看到总体活跃情况，也能比较教师和学生的活跃变化。

区域分布用图表和排行展示各地区的授权学校、活跃学校、活跃用户和应用率，方便比较哪些地区使用得好，哪些地区还需要重点推动。查看某个地区时，可以继续看到该地区下属学校的使用明细。

预警分析分为“产品到期预警”和“产品未应用预警”。到期预警需要区分已经到期和即将到期的学校，并显示学校名称、所属地区、授权时间、到期时间以及剩余或逾期天数。未应用预警列出已经授权、但在所选学期没有产生活跃记录的学校，并显示学校名称、所属地区、授权情况和最近一次活跃时间。两类预警可以切换查看，也能直接看到当前预警学校数量和对应明细。

学校明细和预警明细每页最多显示 10 条，超过后分页查看。

整体做成清爽、稳重的教育产品后台风格。概览数字要醒目，趋势、区域对比和预警信息要有清楚的层级；普通数据和需要关注的风险状态在视觉上容易区分，图表和表格在常见桌面尺寸下方便阅读。

## Expected Behavior

Agent 应从空目录生成可运行的前端网站，按 Prompt 完成页面内容、交互和视觉要求；项目应能在本地安装、构建并启动，且不依赖外部网络资源。

## Grading Criteria

本题使用 LLM Judge 评分。评分点统一放在 `## LLM Judge Rubric` 中；每个 Criterion 仅有 `Score 1.0`（符合预设状态、操作和期望结果）与 `Score 0.0`（不符合其中任一项）两档。

## Automated Checks

## LLM Judge Rubric

说明：

- 每个 Criterion 都按同一结构书写：`预设状态`、`操作`、`期望结果`。
- `Score 1.0` 表示符合预设状态、操作要求，且结果与期望结果一致。
- `Score 0.0` 表示任一部分不符合。

### Criterion 1: 页面清楚展示智慧教学产品数据分析看板，并包含学期、省、市 (key: criterion_01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.041)

预设状态：首次打开看板。

操作：检查页面主要区域和筛选项。

期望结果：页面清楚展示智慧教学产品数据分析看板，并包含学期、省、市、区筛选，以及整体概览、产品活跃趋势、区域分布、学校明细和预警分析区域。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 2: 概览显示授权学校 32 所、活跃学校 28 所、活跃用户 (key: criterion_02_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.041)

预设状态：选择“2025-2026学年第二学期”，地域保持全国范围。

操作：查看整体概览。

期望结果：概览显示授权学校 32 所、活跃学校 28 所、活跃用户 220 人、学校应用率 87.5%，并显示教师活跃 80 人、学生活跃 140 人。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 3: 趋势图覆盖所选学期的时间范围，能同时辨认总体、教师和学生 (key: criterion_03_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.041)

预设状态：选择任一有活跃数据的学期。

操作：查看产品活跃趋势。

期望结果：趋势图覆盖所选学期的时间范围，能同时辨认总体、教师和学生三类活跃变化，并有日期和数值刻度或等价的可读提示。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 4: 区域分布展示各省的授权学校、活跃学校、活跃用户和应用率， (key: criterion_04_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.041)

预设状态：地域保持全国范围。

操作：查看区域分布。

期望结果：区域分布展示各省的授权学校、活跃学校、活跃用户和应用率，既能直观看出地区差异，也能查看对应数值。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 5: 学校明细包含学校名称、所属省市区、授权或到期信息、活跃用 (key: criterion_05_lists_and_tables, primary: content_structure, secondary: lists_tables, weight: 0.041)

预设状态：选择“2025-2026学年第二学期”并查看学校明细。

操作：检查学校明细字段。

期望结果：学校明细包含学校名称、所属省市区、授权或到期信息、活跃用户以及应用状态，能区分有活跃和未应用学校。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 6: 页面显示当前到期预警学校数量，明细包含学校名称、所属地区 (key: criterion_06_lists_and_tables, primary: content_structure, secondary: lists_tables, weight: 0.041)

预设状态：打开产品到期预警。

操作：检查预警统计和学校明细。

期望结果：页面显示当前到期预警学校数量，明细包含学校名称、所属地区、授权时间、到期时间和剩余或逾期天数，并能区分已经到期和即将到期。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 7: 页面显示当前未应用学校数量，明细包含学校名称、所属地区、 (key: criterion_07_lists_and_tables, primary: content_structure, secondary: lists_tables, weight: 0.041)

预设状态：打开产品未应用预警。

操作：检查预警统计和学校明细。

期望结果：页面显示当前未应用学校数量，明细包含学校名称、所属地区、授权情况和最近一次活跃时间。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 8: 概览更新为活跃学校 32 所、活跃用户 252 人、教师 (key: criterion_08_filtering_and_sorting, primary: interaction_function, secondary: filtering_sorting, weight: 0.041)

预设状态：地域保持全国范围。

操作：选择“2024-2025学年第一学期”。

期望结果：概览更新为活跃学校 32 所、活跃用户 252 人、教师活跃 96 人、学生活跃 156 人、学校应用率 100%，当前范围同步显示所选学期。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 9: 市级选项只出现杭州市和宁波市，区级筛选等待选择城市；选择 (key: criterion_09_cross_section_coordination, primary: interaction_function, secondary: cross_region_linkage, weight: 0.041)

预设状态：省、市、区都未选择。

操作：选择省份“浙江省”。

期望结果：市级选项只出现杭州市和宁波市，区级筛选等待选择城市；选择最新学期时概览同步变为授权学校 8 所、活跃学校 6 所、活跃用户 47 人、学校应用率 75%。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 10: 区级选项只出现西湖区和余杭区，概览更新为授权学校 4 所 (key: criterion_10_cross_section_coordination, primary: interaction_function, secondary: cross_region_linkage, weight: 0.041)

预设状态：已选择浙江省和最新学期。

操作：选择城市“杭州市”。

期望结果：区级选项只出现西湖区和余杭区，概览更新为授权学校 4 所、活跃学校 3 所、活跃用户 23 人，学校明细只包含杭州市学校。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 11: 概览更新为授权学校 2 所、活跃学校 1 所、活跃用户  (key: criterion_11_cross_section_coordination, primary: interaction_function, secondary: cross_region_linkage, weight: 0.041)

预设状态：已选择浙江省、杭州市和最新学期。

操作：选择“西湖区”。

期望结果：概览更新为授权学校 2 所、活跃学校 1 所、活跃用户 8 人，学校明细只显示文澜实验学校和翠苑中学。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 12: 原来的杭州市和西湖区选择被清除，市级选项改为南京市和苏州 (key: criterion_12_cross_section_coordination, primary: interaction_function, secondary: cross_region_linkage, weight: 0.041)

预设状态：已经选择浙江省、杭州市和西湖区。

操作：将省份改为“江苏省”。

期望结果：原来的杭州市和西湖区选择被清除，市级选项改为南京市和苏州市，页面不残留浙江省学校或统计。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 13: 所有区域都使用同一组学期和地域条件：概览为浙江省统计，趋 (key: criterion_13_filtering_and_sorting, primary: interaction_function, secondary: filtering_sorting, weight: 0.041)

预设状态：选择“2025-2026学年第二学期”和“浙江省”。

操作：同时观察概览、趋势、区域分布、学校明细和未应用预警。

期望结果：所有区域都使用同一组学期和地域条件：概览为浙江省统计，趋势只计算浙江省用户，区域分布进入浙江省下的城市层级，学校和未应用预警中不出现其他省份。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 14: 趋势图的时间范围和各时间点数据随学期更新，不继续显示最新 (key: criterion_14_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.041)

预设状态：先查看最新学期的活跃趋势。

操作：切换到“2024-2025学年第一学期”。

期望结果：趋势图的时间范围和各时间点数据随学期更新，不继续显示最新学期的日期或数值。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 15: 全国范围比较省份，选择浙江省后比较其下城市，选择杭州市后 (key: criterion_15_cross_section_coordination, primary: interaction_function, secondary: cross_region_linkage, weight: 0.041)

预设状态：先后处于全国、浙江省、杭州市三个地域层级。

操作：依次查看区域分布的统计对象。

期望结果：全国范围比较省份，选择浙江省后比较其下城市，选择杭州市后比较其下区县；区域图表和排行不会混用其他层级。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 16: 看板进入对应的下一级地域范围，顶部筛选和当前范围同步变化 (key: criterion_16_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.041)

预设状态：区域分布处于全国、省或市层级。

操作：点击一个可继续查看的地区。

期望结果：看板进入对应的下一级地域范围，顶部筛选和当前范围同步变化，概览、图表与明细随之更新。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 17: 预警数量、说明和学校明细随类型切换，两类预警不会混在同一 (key: criterion_17_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.041)

预设状态：停留在预警分析区域。

操作：在“产品到期预警”和“产品未应用预警”之间切换。

期望结果：预警数量、说明和学校明细随类型切换，两类预警不会混在同一份明细中。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 18: 未应用预警显示 4 所学校，分别为文澜实验学校、鄞州新城 (key: criterion_18_filtering_and_sorting, primary: interaction_function, secondary: filtering_sorting, weight: 0.041)

预设状态：选择最新学期和全国范围。

操作：打开产品未应用预警。

期望结果：未应用预警显示 4 所学校，分别为文澜实验学校、鄞州新城学校、金陵汇文学校和海珠实验学校；这些学校在所选学期的活跃用户均为 0。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 19: 未应用预警数量变为 0，并显示当前筛选范围内没有未应用学 (key: criterion_19_filtering_and_sorting, primary: interaction_function, secondary: filtering_sorting, weight: 0.041)

预设状态：产品未应用预警已打开，地域为全国范围。

操作：将学期切换为“2025-2026学年第一学期”。

期望结果：未应用预警数量变为 0，并显示当前筛选范围内没有未应用学校的清楚提示。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 20: 到期预警和明细只计算广东省学校；当前数据中没有已到期或  (key: criterion_20_filtering_and_sorting, primary: interaction_function, secondary: filtering_sorting, weight: 0.041)

预设状态：打开产品到期预警并保持全国范围。

操作：选择省份“广东省”。

期望结果：到期预警和明细只计算广东省学校；当前数据中没有已到期或 90 天内到期学校时，显示清楚的空状态，不继续显示其他省份的预警。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 21: 页面按照筛选、概览、趋势与区域分析、学校明细和预警的阅读 (key: criterion_21_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.041)

预设状态：在 1440×900 桌面视口打开看板。

操作：观察筛选区、概览、图表、表格和预警区域。

期望结果：页面按照筛选、概览、趋势与区域分析、学校明细和预警的阅读顺序组织，关键数据醒目，图表与表格有足够空间，主要信息容易浏览。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 22: 页面呈现清爽、稳重的教育产品后台风格；总体、教师和学生趋 (key: criterion_22_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.041)

预设状态：页面同时显示普通数据和预警状态。

操作：观察整体风格、图表系列和风险标记。

期望结果：页面呈现清爽、稳重的教育产品后台风格；总体、教师和学生趋势容易区分，正常、即将到期、已到期和未应用状态有清楚但不过度刺眼的视觉差异。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 23: 学校明细每页最多显示 10 条，页面提供清楚的页码或前后 (key: criterion_23_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.041)

预设状态：选择最新学期和全国范围，学校明细共有 32 所学校。

操作：查看学校明细第一页并切换到下一页。

期望结果：学校明细每页最多显示 10 条，页面提供清楚的页码或前后翻页操作；切换到下一页后显示另一组学校记录，并能看出当前页和总数据量。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 24: 预警明细第一页最多显示 10 条，并提供分页操作；切换到 (key: criterion_24_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.057)

预设状态：保持全国范围并打开产品到期预警，当前共有 16 所预警学校。

操作：查看预警明细第一页并切换到下一页。

期望结果：预警明细第一页最多显示 10 条，并提供分页操作；切换到下一页后显示其余 6 条预警记录，当前预警总数仍为 16。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

## Workspace Path

workspace/extension/07_Website_Generation/task_009_smart_teaching_dashboard

## Skills

## Env

无

## Warmup
