---
id: 07_Website_Generation_task_034_iphone17pro_product_page
name: iPhone 17 Pro 商品详情页
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 电商商品详情页
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# iPhone 17 Pro 商品详情页

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

帮我做一个 iPhone 17 Pro 的商品详情页。产品图片、影片和文案都放在 `/tmp_workspace/assets` 目录里，请直接使用，页面上的信息要和文案一致。

页面上半部分是选购区：能挑机型、颜色和存储容量，选完马上看到这套配置的价格，主图也换成所选颜色的机身。两个机型能选的容量不一样，别让人选出买不到的组合。

下半部分讲清楚这台机器好在哪，外观设计、A19 Pro 芯片、后置摄像头、前置摄像头和电池续航都要有，素材里给了配图的那几块把图用上，摄像头那块把变焦能力说到位。再放一段产品影片，点一下就能播。最后给一张两个机型的规格对比表，屏幕大小、重量和续航这几项要能直接比出来。

整体走深色调，配上产品图会更有科技感，重点信息一眼能看到。手机上也要能正常浏览。

## Expected Behavior

Agent 应按 Prompt 完成页面内容、交互和视觉要求。

题目素材位于 /tmp_workspace/assets，页面内容必须与素材一致，不得用编造数据替代。

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

### Criterion 1: 找到选购区的颜色选项 (key: c01_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0833)

预设状态：在 1440×900 视口打开首页。

操作：找到选购区的颜色选项，读出全部可选颜色的名称。

期望结果：可选颜色恰好是银色、星宇橙色、深蓝色三种，名称写法与素材一致，没有多出素材里没有的颜色。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 从页面顶部滚动到底部 (key: c02_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0833)

预设状态：在 1440×900 视口打开首页。

操作：从页面顶部滚动到底部，记录页面分成了哪几块内容。

期望结果：页面至少能找到选购（机型、颜色、容量与价格）、外观设计、A19 Pro 芯片、后置摄像头、前置摄像头、电池续航、两个机型的规格对比这几块内容，每一块都有可辨认的标题或独立区域。素材里配了图的那几块（外观设计、芯片、后置摄像头、前置摄像头等）都用上了对应的配图，图片正常渲染、不是破图或占位块。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 滚动到讲后置摄像头的那一块 (key: c03_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0833)

预设状态：在 1440×900 视口打开首页。

操作：滚动到讲后置摄像头的那一块，读出像素和变焦的说明。

期望结果：能读到后置三颗摄像头都是 4800 万像素，以及 8 倍光学品质变焦和 16 倍光学变焦范围这两个数值，数值与素材一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 滚动到两个机型的规格对比处 (key: c04_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0833)

预设状态：在 1440×900 视口打开首页。

操作：滚动到两个机型的规格对比处，读出显示屏尺寸、重量和视频播放时间这三项。

期望结果：iPhone 17 Pro 一侧是 6.3 英寸、204 克、视频播放最长可达 31 小时，iPhone 17 Pro Max 一侧是 6.9 英寸、231 克、视频播放最长可达 37 小时，六个数值都能读到且没有把归属的机型对调。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 依次选中机型 iPhone 17 Pro Max、颜色深蓝色、容量 512GB (key: c05_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0833)

预设状态：在 1440×900 视口打开首页，滚动到选购区。

操作：依次选中机型 iPhone 17 Pro Max、颜色深蓝色、容量 512GB，然后读出页面显示的价格。

期望结果：价格是 11999 元，写成 ¥11,999、￥11,999、11,999 元或 11999 元都算通过，不能停留在其他容量或其他机型的价格上。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 把颜色改选为星宇橙色 (key: c06_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0833)

预设状态：在 1440×900 视口打开首页，滚动到选购区，先选中颜色银色，记下此时选购区展示的商品主图画面。

操作：把颜色改选为星宇橙色。

期望结果：选购区展示的商品主图换成了橙色机身的那张图，与选银色时展示的图片明显不是同一张。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 把机型改选为 iPhone 17 Pro (key: c07_cross_region_linkage, primary: interaction_function, secondary: cross_region_linkage, weight: 0.0833)

预设状态：在 1440×900 视口打开首页，滚动到选购区，先选中机型 iPhone 17 Pro Max，再选中容量 2TB。

操作：把机型改选为 iPhone 17 Pro，然后查看容量选项。

期望结果：2TB 不再处于可以选中的状态，从容量列表里消失、置灰或以其他方式明确标为不可选都算通过。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 把机型改选为 iPhone 17 Pro (key: c08_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0833)

预设状态：在 1440×900 视口打开首页，滚动到选购区，先选中机型 iPhone 17 Pro Max，再选中容量 2TB。

操作：把机型改选为 iPhone 17 Pro，然后同时读出当前选中的容量和页面显示的价格。

期望结果：价格重新算过并与「iPhone 17 Pro + 当前选中容量」这组配置对得上：256GB 对 8999 元、512GB 对 10999 元、1TB 对 12999 元，不再显示 17999 元。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 点击影片的播放控件 (key: c09_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0833)

预设状态：在 1440×900 视口打开首页，滚动到产品影片所在的位置。

操作：点击影片的播放控件，等待约 2 秒后观察影片。

期望结果：影片开始播放，播放进度从 0 往前走、画面在动，不是停在静止的封面帧上。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看页面主体区域的背景色和正文文字颜色 (key: c10_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0833)

预设状态：在 1440×900 视口打开首页。

操作：查看页面主体区域的背景色和正文文字颜色。

期望结果：页面主体背景是深色（接近黑色或深灰），正文文字是浅色，深底浅字的方向明确，不是深底深字或浅底浅字。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 对比 512GB 与 256GB 两个容量选项的外观 (key: c11_component_style, primary: visual_layout, secondary: component_style, weight: 0.0833)

预设状态：在 1440×900 视口打开首页，滚动到选购区，把容量选中为 512GB。

操作：对比 512GB 与 256GB 两个容量选项的外观。

期望结果：选中的 512GB 与未选中的 256GB 在外观上有明显差别，边框、底色、文字颜色或勾选标记等任意一种处理方式都算通过，一眼能看出当前选的是哪一个。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 从页面顶部滚动到底部 (key: c12_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0837)

预设状态：把视口调成 375×812 后打开首页。（视口 375×812）

操作：从页面顶部滚动到底部，途中在选购区点一次未选中的容量选项。

期望结果：页面没有横向滚动，没有元素宽度超出视口被截断；选购区的机型、颜色、容量三组选项都完整可见，能点中并看到选中效果发生变化。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_034_iphone17pro_product_page

## Skills

## Env

## Warmup
