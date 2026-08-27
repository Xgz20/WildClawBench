---
id: 07_Website_Generation_task_019_meal_lottery_wheel
name: 吃饭抽签转盘
category: 07_Website_Generation
sub_category: 日常管理与家庭事务
task_type: 生活决策／抽签转盘
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 吃饭抽签转盘

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

每顿饭我都不知道吃什么，用一个转盘来抽签帮我决定每顿饭吃什么。

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

### Criterion 1: 检查转盘本体以及转盘上每一块扇区的文字 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.1428)

预设状态：首页已在 1440×900 视口打开，尚未进行任何抽签

操作：检查转盘本体以及转盘上每一块扇区的文字

期望结果：页面上有一个可辨认的转盘，被分成至少 3 块扇区，每块扇区都带有可读文字，没有空白扇区。这些文字是具体的餐品或菜式名称（例如“番茄炒蛋盖饭”“兰州拉面”“汉堡”），而不是“选项 1”“A”“待定”这类占位符。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 记录转盘当前的角度或各扇区所在位置 (key: c02_realtime_auto_progress, primary: interaction_function, secondary: realtime_auto_progress, weight: 0.1428)

预设状态：首页已打开，转盘静止，尚未抽签

操作：记录转盘当前的角度或各扇区所在位置，点击页面上用于开始抽签的控件，在转盘仍在运动时观察一次，再等待至转盘自行停止，最多等待 10 秒

期望结果：点击后转盘开始转动，转动过程中转盘的角度或扇区位置与点击前明显不同。转动无需用户再做任何操作即会自行减速并停下，停下后转盘保持静止不再移动。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 点击开始抽签 (key: c03_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1428)

预设状态：首页已打开，转盘静止，尚未抽签

操作：点击开始抽签，等待转盘完全停止（最多等待 10 秒），然后同时查看指针或固定标记所指向的那块扇区上的文字，以及页面上给出的本次抽签结果文字

期望结果：转盘停止后页面明确给出了本次抽中的餐品名称，并且该名称与指针、固定标记或高亮扇区所指向的那块扇区上的文字完全一致。页面上不存在两个互相矛盾的中选结果。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 连续抽签 5 次 (key: c04_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1428)

预设状态：首页已打开，转盘静止，尚未抽签

操作：连续抽签 5 次：每次点击开始抽签后等待转盘完全停止（最多等待 10 秒），记下该次的结果文字，再进行下一次

期望结果：5 次抽签每次都给出了一个非空的餐品名称作为结果，并且 5 次结果不全部相同，至少出现过两个不同的餐品名称。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 点击开始抽签 (key: c05_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.1428)

预设状态：首页已打开，转盘静止，尚未抽签

操作：点击开始抽签，不等转盘停下，在转盘仍在转动时再次点击同一个控件，然后等待至转盘完全停止，最多等待 10 秒

期望结果：第二次点击不会产生另一个并行的抽签过程。转盘最终停在唯一一个位置，页面上只显示一个抽中的餐品名称，且该名称与指针、固定标记或高亮扇区所指的扇区文字一致；不出现两个结果同时展示、结果文字持续跳变或转盘无法停下的情况。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 不滚动页面，检查转盘、开始抽签的控件和抽签结果的展示位置 (key: c06_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.1428)

预设状态：首页已在 1440×900 视口打开，尚未抽签

操作：不滚动页面，检查转盘、开始抽签的控件和抽签结果的展示位置

期望结果：转盘完整可见没有被裁切，开始抽签的控件在同一屏内可见并可点击，抽签结果出现的位置也在同一屏内（抽签前该位置可以为空或显示引导文字）。用户打开页面后不需要滚动就能完成一次抽签并看到结果。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 检查转盘与抽签控件的呈现 (key: c07_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.1432)

预设状态：浏览器视口已调整为 375×812 并打开首页（视口 375×812）

操作：检查转盘与抽签控件的呈现，然后完成一次抽签并查看结果

期望结果：页面没有横向滚动，没有任何元素宽度超出视口。转盘完整可见，没有被裁切也没有与其他元素重叠，开始抽签的控件可以正常点击，抽签结果在窄屏下同样清楚可读。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_019_meal_lottery_wheel

## Skills

## Env

## Warmup
