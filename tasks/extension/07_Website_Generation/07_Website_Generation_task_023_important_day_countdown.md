---
id: 07_Website_Generation_task_023_important_day_countdown
name: 重要日子倒数
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 纪念日倒数提醒页
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 重要日子倒数

## Prompt

请在 /tmp_workspace 下从空目录创建一个可运行的中文纪念日倒数提醒页网页项目。项目根目录需要提供 package.json，并支持 npm install、npm run build，以及 npm run start -- --host 127.0.0.1 --port 4173 启动网站。页面运行时不要依赖外部图片、字体、接口或其他网络资源；不要接入真实支付或发送真实请求。

有几个日子我总是记不住，想要个页面一眼看到离它们还有多少天。

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

### Criterion 1: 检查页面提供的入口和已有内容的呈现方式 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.1)

预设状态：首页已在 1440×900 视口打开，已通过页面添加两个不同日期的日子

操作：检查页面提供的入口和已有内容的呈现方式

期望结果：页面能看出是用来盯着若干个重要日子的，提供了添加一个日子的入口，至少能填写这个日子的名称和具体日期；已添加的两个日子以列表或卡片的形式呈现，每条都同时显示名称和剩余天数。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 添加一个名称为“体检”、日期为从今天算起第 30 天的日子 (key: c02_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.1)

预设状态：首页已打开

操作：添加一个名称为“体检”、日期为从今天算起第 30 天的日子

期望结果：这个日子出现在页面上，名称显示为“体检”，对应的日期与填写的一致，并且同时显示出剩余天数。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 添加一个日期正好是今天的日子 (key: c03_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1)

预设状态：首页已打开

操作：添加一个日期正好是今天的日子，名称填“今天这件事”，查看它显示的天数

期望结果：这一条显示的是“就是今天”这类零天的表述，或者明确的 0 天，既不显示 1 天，也不显示负数或者“已过去 1 天”。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 分别添加日期为明天和从今天算起第 30 天的两个日子 (key: c04_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1)

预设状态：首页已打开

操作：分别添加日期为明天和从今天算起第 30 天的两个日子，查看各自显示的天数

期望结果：明天那条显示还剩 1 天，第 30 天那条显示还剩 30 天，两条都不差一天，也没有把今天算进去。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 添加一个日期是昨天的日子 (key: c05_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1)

预设状态：首页已打开

操作：添加一个日期是昨天的日子，查看它的呈现

期望结果：这一条不会显示成还剩 1 天或还剩 -1 天这类错误数值；页面用可辨认的方式表明它已经过去（显示已过去 1 天、标注今天已过、置灰等形式都算），这条记录不会无故消失。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 添加一个日期为从今天算起第 400 天的日子 (key: c06_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1)

预设状态：首页已打开

操作：添加一个日期为从今天算起第 400 天的日子，查看它显示的天数

期望结果：这一条显示还剩 400 天，跨过年份边界后天数依然准确，没有因为跨年或各月天数不同而出现偏差。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 删除其中一个日子 (key: c07_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.1)

预设状态：页面上已经添加了三个不同名称、不同日期的日子

操作：删除其中一个日子，检查页面上剩下的内容

期望结果：被删除的那一条从页面上消失，另外两条仍在，名称、日期和剩余天数都保持原样没有被牵连改动。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 先在名称留空的情况下提交一次 (key: c08_form_validation, primary: interaction_function, secondary: form_validation, weight: 0.1)

预设状态：页面处于可以添加日子的状态

操作：先在名称留空的情况下提交一次，再在日期留空的情况下提交一次

期望结果：两次提交都被拦下，页面给出可见的提示说明问题所在，列表中不会多出没有名称或没有日期的条目。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 检查每条日子的信息排布和剩余天数的呈现 (key: c09_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.1)

预设状态：页面上已经添加了三个日子，视口为 1440×900

操作：检查每条日子的信息排布和剩余天数的呈现

期望结果：每条日子的名称、日期和剩余天数归属清楚、不会串行；剩余天数在这一条里比名称和日期更突出（字号更大或有明显的视觉强调），扫一眼就能看出还有多久。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 在窄屏下添加一个日子并查看列表 (key: c10_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.1)

预设状态：浏览器视口已调整为 375×812 并打开首页（视口 375×812）

操作：在窄屏下添加一个日子并查看列表

期望结果：页面没有横向滚动，没有任何元素宽度超出视口。添加表单的字段和按钮都能正常填写和点击，每条日子的名称、日期和剩余天数完整可读，没有被截断或互相重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_023_important_day_countdown

## Skills

## Env

## Warmup
