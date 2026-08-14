---
id: 07_Website_Generation_task_006_xingji_travel_planner
name: 行迹旅行规划
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 旅行行程规划器
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 行迹旅行规划

## Prompt

请在 /tmp_workspace 下从空目录创建一个可运行的中文旅行行程规划器网页项目。项目根目录需要提供 package.json，并支持 npm install、npm run build，以及 npm run start -- --host 127.0.0.1 --port 4173 启动网站。不要接入真实网络请求，也不要使用需要联网才能显示的图片、字体或外部数据。

我想做一个叫“行迹 Planner”的中文旅行行程规划器，方便把一次旅行按天整理清楚。不需要登录，保存过的行程直接留在浏览器里，下次打开还能从历史行程继续编辑。

首页可以选择目的地城市和旅行日期来创建新行程，也能看到以前保存的行程。创建时如果没选城市，或者结束日期早于开始日期，要给出容易看懂的提示。进入规划后，根据城市和天数自动起一个行程名，用户可以再改成自己喜欢的名字，也可以调整旅行的起止日期。

规划页按日期分别展示每天的安排，没有内容时给出空状态。用户可以往当天添加目的地，记录名称、类型、时间和备注；类型包括住宿、交通、景点、吃饭、购物和其他。添加后的卡片要把这些信息展示清楚，名称没填时不要生成空项目。

同一天的多个目的地可以拖动调整顺序，也可以随时修改或删除。切换日期时，只显示对应那一天的安排。调整旅行日期后，新增的日期从空白行程开始，不在新日期范围内的日期不再显示。

用户可以保存当前行程，回到首页后从历史记录继续编辑。历史记录里要看得到行程名、城市、日期、天数和目的地数量；同一条行程再次保存时更新原记录，不要重复新增。规划好的内容还可以导出成一张行程图，先看到包含行程名、日期和每天安排的预览，再下载到本地。

整体做成清爽的旅行规划工作台，使用浅色背景和白色卡片，主要操作用蓝绿色，重要信息可以加一点暖橙色。首页的创建入口和历史行程要容易区分；进入规划后，日期切换、添加区域和每天的行程列表要层次清楚，方便一边添加一边查看。

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

### Criterion 1: 首页显示品牌名“行迹 Planner”和旅行规划用途说明 (key: criterion_01_basic_content, primary: content_structure, secondary: basic_content, weight: 0.050)

预设状态：首次打开首页，浏览器中没有保存过本题数据。

操作：检查首页品牌和创建入口。

期望结果：首页显示品牌名“行迹 Planner”和旅行规划用途说明；创建区域提供目的地城市、开始日期、结束日期和进入规划的入口。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 2: 首页有清楚的历史行程区域，并显示“还没有保存的行程”等真 (key: criterion_02_lists_and_tables, primary: content_structure, secondary: lists_tables, weight: 0.050)

预设状态：首次打开首页，尚未保存任何行程。

操作：查看历史行程区域。

期望结果：首页有清楚的历史行程区域，并显示“还没有保存的行程”等真实空状态，没有虚假的历史记录。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 3: 页面进入规划界面，自动生成“成都市3日游”或意思相同的行 (key: criterion_03_content_creation_and_editing, primary: interaction_function, secondary: content_editing, weight: 0.050)

预设状态：首页创建区已选择“成都市”，开始日期为 2026-10-03，结束日期为 2026-10-05。

操作：点击“进入规划”。

期望结果：页面进入规划界面，自动生成“成都市3日游”或意思相同的行程名，并显示城市、日期范围，以及返回首页、保存和导出行程图的入口。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 4: 创建区提示用户选择目的地城市，页面仍停留在首页，不会创建 (key: criterion_04_form_filling_and_validation, primary: interaction_function, secondary: form_validation, weight: 0.050)

预设状态：停留在首页创建区。

操作：清空城市选择后尝试进入规划。

期望结果：创建区提示用户选择目的地城市，页面仍停留在首页，不会创建缺少城市的行程。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 5: 创建区说明结束日期不能早于开始日期，页面仍停留在首页，不 (key: criterion_05_form_filling_and_validation, primary: interaction_function, secondary: form_validation, weight: 0.050)

预设状态：停留在首页创建区并已选择城市。

操作：把结束日期设为早于开始日期后尝试进入规划。

期望结果：创建区说明结束日期不能早于开始日期，页面仍停留在首页，不会创建日期范围无效的行程。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 6: 规划界面显示 2026-10-03、2026-10-04 (key: criterion_06_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.050)

预设状态：已创建 2026-10-03 至 2026-10-05 的三日行程。

操作：查看日期切换区和其中一天的内容。

期望结果：规划界面显示 2026-10-03、2026-10-04、2026-10-05 三个可切换日期，并能分辨第 1 天至第 3 天；当前日期没有安排时显示“这一天还没有目的地”等空状态。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 7: 当前日期新增一张目的地卡片，显示序号 1、“宽窄巷子”、 (key: criterion_07_content_creation_and_editing, primary: interaction_function, secondary: content_editing, weight: 0.050)

预设状态：规划界面当前日期为空，添加目的地表单可用。

操作：填写目的地名称“宽窄巷子”，类型选“景点”，时间填 09:30，备注填“上午拍照”，然后添加到当天。

期望结果：当前日期新增一张目的地卡片，显示序号 1、“宽窄巷子”、“景点”、09:30 和“上午拍照”，原来的空状态消失。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 8: 表单提示用户输入目的地名称，当前日期不会新增空白目的地。 (key: criterion_08_form_filling_and_validation, primary: interaction_function, secondary: form_validation, weight: 0.050)

预设状态：规划界面的添加目的地表单可用。

操作：不填写目的地名称，尝试添加到当天。

期望结果：表单提示用户输入目的地名称，当前日期不会新增空白目的地。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 9: 类型可以选择住宿、交通、景点、吃饭、购物和其他；添加后的 (key: criterion_09_information_organization, primary: content_structure, secondary: information_organization, weight: 0.050)

预设状态：规划界面的添加目的地表单可见。

操作：查看目的地类型选项，并观察添加后的类型信息。

期望结果：类型可以选择住宿、交通、景点、吃饭、购物和其他；添加后的目的地能清楚显示所选类型。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 10: 拖动后“酒店入住”排在第一位并显示序号 1，“宽窄巷子” (key: criterion_10_content_creation_and_editing, primary: interaction_function, secondary: content_editing, weight: 0.050)

预设状态：当前日期依次已有“宽窄巷子”和“酒店入住”两个目的地。

操作：把“酒店入住”拖到“宽窄巷子”前面。

期望结果：拖动后“酒店入住”排在第一位并显示序号 1，“宽窄巷子”排在第二位并显示序号 2，排列和序号保持一致。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 11: 原目的地更新为“人民公园”，并显示类型“吃饭”、时间 1 (key: criterion_11_content_creation_and_editing, primary: interaction_function, secondary: content_editing, weight: 0.050)

预设状态：当前日期已有“宽窄巷子”目的地。

操作：打开这条目的地的编辑入口，将名称改为“人民公园”、类型改为“吃饭”、时间改为 12:00、备注改为“午饭后散步”，然后保存。

期望结果：原目的地更新为“人民公园”，并显示类型“吃饭”、时间 12:00 和备注“午饭后散步”，不会额外生成一条重复记录。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 12: “宽窄巷子”从当天行程中移除，只剩“酒店入住”，且剩余项 (key: criterion_12_content_creation_and_editing, primary: interaction_function, secondary: content_editing, weight: 0.050)

预设状态：当前日期依次已有“宽窄巷子”和“酒店入住”两个目的地。

操作：删除“宽窄巷子”。

期望结果：“宽窄巷子”从当天行程中移除，只剩“酒店入住”，且剩余项目重新显示为序号 1。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 13: “春熙路”只出现在第 2 天；切回第 1 天后仍显示第  (key: criterion_13_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.050)

预设状态：第 1 天已有一个目的地，第 2 天仍为空。

操作：切换到第 2 天添加“春熙路”，然后再切回第 1 天。

期望结果：“春熙路”只出现在第 2 天；切回第 1 天后仍显示第 1 天原有的目的地，两天的安排不会混在一起。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 14: 页面给出保存成功的反馈，顶部继续显示“成都亲子慢游”，保 (key: criterion_14_content_creation_and_editing, primary: interaction_function, secondary: content_editing, weight: 0.050)

预设状态：规划界面已有一个尚未保存的行程。

操作：把行程名改为“成都亲子慢游”，然后保存行程。

期望结果：页面给出保存成功的反馈，顶部继续显示“成都亲子慢游”，保存后仍可继续编辑当前行程。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 15: 历史记录中出现“成都亲子慢游”，并显示对应城市、日期范围 (key: criterion_15_state_persistence, primary: interaction_function, secondary: state_persistence, weight: 0.050)

预设状态：已经保存名为“成都亲子慢游”的行程。

操作：返回首页并查看历史行程。

期望结果：历史记录中出现“成都亲子慢游”，并显示对应城市、日期范围、总天数和目的地数量，同时提供继续编辑的入口。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 16: 原有内容会被带回规划界面；再次保存后更新原来的历史记录， (key: criterion_16_content_creation_and_editing, primary: interaction_function, secondary: content_editing, weight: 0.050)

预设状态：首页历史记录中已有“成都亲子慢游”。

操作：继续编辑这条行程，修改或新增一个目的地后再次保存，再返回首页。

期望结果：原有内容会被带回规划界面；再次保存后更新原来的历史记录，首页不会出现两条重复的“成都亲子慢游”。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 17: 日期增加后出现 2026-10-06，并且这一天从空白行 (key: criterion_17_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.050)

预设状态：规划界面的日期范围为 2026-10-03 至 2026-10-05。

操作：先把结束日期调整为 2026-10-06，再调整为 2026-10-04。

期望结果：日期增加后出现 2026-10-06，并且这一天从空白行程开始；日期缩短后只显示 2026-10-03 和 2026-10-04，不在新范围内的日期不再显示。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 18: 页面显示一张可见的行程图预览，预览包含行程名、日期范围和 (key: criterion_18_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.050)

预设状态：规划界面已有一个命名完成的行程，并在不同日期添加了至少两个目的地。

操作：打开导出行程图功能。

期望结果：页面显示一张可见的行程图预览，预览包含行程名、日期范围和每天的目的地摘要，并提供可点击的下载入口；关闭预览后回到原来的规划界面。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 19: 刷新后历史记录仍然存在；继续编辑时，行程名称、日期和各天 (key: criterion_19_state_persistence, primary: interaction_function, secondary: state_persistence, weight: 0.050)

预设状态：首页历史记录中已有保存过的“成都亲子慢游”行程。

操作：刷新页面，再从历史记录继续编辑这条行程。

期望结果：刷新后历史记录仍然存在；继续编辑时，行程名称、日期和各天已经保存的目的地内容都能正确恢复。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 20: 页面使用浅色背景和白色卡片，主要操作采用蓝绿色，并有暖橙 (key: criterion_20_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.050)

预设状态：在桌面视口分别打开首页和规划界面。

操作：检查整体配色、信息层级和主要工作区域。

期望结果：页面使用浅色背景和白色卡片，主要操作采用蓝绿色，并有暖橙色重点信息。首页的创建入口和历史行程容易区分；规划界面的日期切换、添加区域和当天行程列表层次清楚，主要操作和内容不会互相遮挡。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

## Workspace Path

workspace/extension/07_Website_Generation/task_006_xingji_travel_planner

## Skills

## Env

无

## Warmup
