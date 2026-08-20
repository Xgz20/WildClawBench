---
id: 07_Website_Generation_task_021_dorm_duty_roster
name: 宿舍值日排班表
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 按周轮换的值日排班表
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 宿舍值日排班表

## Prompt

请在 /tmp_workspace 下从空目录创建一个可运行的中文按周轮换的值日排班表网页项目。项目根目录需要提供 package.json，并支持 npm install、npm run build，以及 npm run start -- --host 127.0.0.1 --port 4173 启动网站。页面运行时不要依赖外部图片、字体、接口或其他网络资源；不要接入真实支付或发送真实请求。

我们宿舍有四个人，小冰、小洁、小晴、小玉，每周换值日生都不记得是谁了，给我一个排班表，每次点进去就知道现在是谁值日。

## Expected Behavior

Agent 应从空目录生成可运行的前端网站，按 Prompt 完成页面内容、交互和视觉要求；项目应能在本地 npm install、npm run build 并通过 npm run start 启动，且不依赖外部网络资源。

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

### Criterion 1: 不做任何点击或输入 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.125)

预设状态：首页刚刚打开，尚未进行任何操作，视口为 1440×900

操作：不做任何点击或输入，直接查看页面上关于当前值日生的呈现

期望结果：页面一打开就直接告诉你现在是谁值日，不需要先选日期、先点按钮或做任何操作。被指为当前值日生的恰好是小冰、小洁、小晴、小玉中的一位，不会同时出现两位，也不会一位都没有。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看排班表，记下四个人的轮值先后顺序以及每一轮对应的时间范围 (key: c02_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.125)

预设状态：首页已打开

操作：查看排班表，记下四个人的轮值先后顺序以及每一轮对应的时间范围

期望结果：排班表把小冰、小洁、小晴、小玉四个人都排了进去，没有人被漏掉；任意相邻的四周恰好是四个不同的人，按固定顺序轮换（排班表可以往后滚动展示更多周，同一个人再次出现属于正常轮回）。每一轮都能看出对应的是哪一周。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 在排班表中找到被标为当前这一周的那一行 (key: c03_cross_region_linkage, primary: interaction_function, secondary: cross_region_linkage, weight: 0.125)

预设状态：首页已打开，页面同时显示了当前值日生和整张排班表

操作：在排班表中找到被标为当前这一周的那一行，把这一行上的人和页面上单独指出的当前值日生做对照

期望结果：排班表里标为当前这一周的那一行，其值日生与页面单独指出的当前值日生是同一个人，两处不会互相矛盾。排班表中被标为当前的这一周有且只有一行。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 在排班表中查看每一轮值日对应的时间范围 (key: c04_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.125)

预设状态：首页已打开，页面同时显示了当前值日生和排班表

操作：在排班表中查看每一轮值日对应的时间范围

期望结果：每一轮值日覆盖完整的一周：同一行的起止日期相差七天（或以周为单位标注），一周之内不出现中途换人的拆分。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 在排班表中查看当前这一周的下一周排的是谁 (key: c05_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.125)

预设状态：首页已打开，已记下排班表中当前这一周的值日生

操作：在排班表中查看当前这一周的下一周排的是谁，并与四人的轮换顺序对照

期望结果：下一周排的是轮换顺序中紧接着当前值日生的下一位，而不是随机的一位或与本周相同的人；整张表相邻两周的值日生都按同一顺序接续。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 从排班表中当前这一周起 (key: c06_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.125)

预设状态：首页已打开，排班表至少能看到连续四周的安排

操作：从排班表中当前这一周起，连续查看四周的值日生

期望结果：从当前这一周起连续四周恰好是小冰、小洁、小晴、小玉四个人各轮到一次，没有人被跳过或连值两周；若表中展示了第五周，第五周回到与当前这一周相同的人，轮换成环。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 不滚动页面，检查当前值日生和排班表的排布 (key: c07_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.125)

预设状态：首页已在 1440×900 视口打开

操作：不滚动页面，检查当前值日生和排班表的排布

期望结果：现在轮到谁是页面上最醒目的信息，不需要滚动就能看到，不会淹没在排班表里。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 检查当前值日生的呈现和整张排班表 (key: c08_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.125)

预设状态：浏览器视口已调整为 375×812 并打开首页（视口 375×812）

操作：检查当前值日生的呈现和整张排班表

期望结果：页面没有横向滚动，没有任何元素宽度超出视口。当前值日生和排班表中四个人的姓名、对应周次都完整可读，没有被截断或互相重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_021_dorm_duty_roster

## Skills

## Env

## Warmup
