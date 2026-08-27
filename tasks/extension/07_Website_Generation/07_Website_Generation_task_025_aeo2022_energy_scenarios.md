---
id: 07_Website_Generation_task_025_aeo2022_energy_scenarios
name: AEO2022 能源展望情景对比
category: 07_Website_Generation
sub_category: 数据分析与决策
task_type: 能源展望情景对比页
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# AEO2022 能源展望情景对比

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

美国能源信息署每年发布一份长期能源展望，我把 2022 年那次发布会的演示稿放在 `/tmp_workspace/assets` 目录里了。这份材料的重点不是某一个数字，而是它同时给出了好几套假设不同的情景，同一件事在不同假设下走向差别很大。想做一个网页，让人能把这些情景摆在一起看明白。

内容以原件为准，情景名称、假设参数和结论都照原件写，不要自己编造数字。

页面上要能选择某一个情景，选中之后它对应的假设条件和图上的位置得一起跟着变，这样才能看出各个情景差在哪里。核心的几条判断也请放在显眼的位置，各个能源领域的主要结论也整理进去。除了已经完成的这些情景，材料里还提到了几个后续要发布的专题情景，也一并列出来。

情景数量不少，请让人能按名字筛选，快速找到某一个。整页内容不短，也请让人能在几个部分之间快速跳转。

视觉上希望像一份专业的能源报告，数据部分清楚易读，不要花哨。手机上也要能正常看。

材料来自美国能源信息署，属于公有领域，页面上把来源注明一下。

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

### Criterion 1: 查看首屏 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0588)

预设状态：首次打开页面

操作：查看首屏

期望结果：可见展望名称 Annual Energy Outlook 2022（或 AEO2022，可另附中文译名），说明这份展望考察的时间范围是 2020 至 2050 年，并写明发布日期为 2022 年 3 月 3 日。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看这份展望给出的核心判断 (key: c02_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0588)

预设状态：页面已打开核心判断部分

操作：查看这份展望给出的核心判断

期望结果：三条核心判断都在且含义与原件一致：一、到 2050 年石油和天然气仍是美国消费量最大的能源，但可再生能源增长最快；二、风能和太阳能的激励政策加上技术成本下降，使其在发电上与天然气形成有力竞争，同时煤电和核电在美国电力结构中的份额下降；三、美国原油产量创历史新高，天然气产量则越来越受出口驱动。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 清点这份展望的核心情景 (key: c03_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0588)

预设状态：页面已打开情景总览部分

操作：清点这份展望的核心情景

期望结果：九个核心情景全部列出且名称与原件一致：参考情景（Reference），高/低经济增长（High/Low Economic Growth），高/低油价（High/Low Oil Price），高/低油气供应（High/Low Oil and Gas Supply），高/低可再生能源成本（High/Low Renewables Cost）。不得多出原件里没有的情景。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 查看经济增长与油价的假设取值 (key: c04_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0588)

预设状态：页面已打开假设条件部分

操作：查看经济增长与油价的假设取值

期望结果：实际 GDP 年均复合增长率写明参考情景 2.2%、高经济增长 2.7%、低经济增长 1.8%；2050 年布伦特原油价格（2021 年不变美元）写明参考情景每桶 90 美元、高油价每桶 170 美元、低油价每桶 45 美元。六个数值都要与原件一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看法规基准与可再生能源成本情景的假设说明 (key: c05_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0588)

预设状态：页面已打开假设条件部分

操作：查看法规基准与可再生能源成本情景的假设说明

期望结果：写明这份展望采用截至 2021 年 11 月的现行法律法规作为基准，并纳入了两党基础设施法（Bipartisan Infrastructure Law）的相关条款；低可再生能源成本情景的设定是到 2050 年可再生能源的隔夜资本成本比参考情景低 40%，高可再生能源成本情景则是可再生能源技术成本不再下降。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 清点后续将要发布的专题情景 (key: c06_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0588)

预设状态：页面已打开后续专题情景部分

操作：清点后续将要发布的专题情景

期望结果：六个后续专题情景都在：替代政策假设下的碳费（carbon fee）、信贷退坡（sunset credits）、信贷延长（extended credits）、不新建管道（no new pipelines），以及替代技术与宏观经济假设下的替代天气假设（alternative weather assumptions）和电池储能应用场景（use cases for battery storage）。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 查看关于美国电力消费增速的判断（页面把它放在概览、核心判断区还是电力领域的结论里… (key: c07_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0588)

预设状态：页面已加载完成

操作：查看关于美国电力消费增速的判断（页面把它放在概览、核心判断区还是电力领域的结论里都可以，若需要切换请先切过去）

期望结果：写明在参考情景下，美国电力消费的年均增速在大部分预测期内保持在 1% 以下。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看关于天然气与液化天然气贸易量的判断（页面把它放在概览、核心判断区还是天然气领… (key: c08_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0588)

预设状态：页面已加载完成

操作：查看关于天然气与液化天然气贸易量的判断（页面把它放在概览、核心判断区还是天然气领域的结论里都可以，若需要切换请先切过去）

期望结果：写明在参考情景下，天然气与液化天然气（LNG）贸易量达到 8 万亿立方英尺。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 查看情景之间的参数对照图形 (key: c09_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.0588)

预设状态：页面已打开情景对比部分

操作：查看情景之间的参数对照图形

期望结果：各情景的关键假设以图形方式对照呈现（柱状、条形、点线等均可），不同情景之间可以直观比出高低；图形的长度、高度或位置与数值大小一致——例如在油价这一项上，高油价情景明显高于参考情景，参考情景又明显高于低油价情景。仅有一张纯数字表格不算。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看资料来源说明 (key: c10_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0588)

预设状态：页面已加载完成

操作：查看资料来源说明

期望结果：页面上能读到内容来自美国能源信息署（EIA / U.S. Energy Information Administration），并说明该材料属于公有领域或为美国政府出版物。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 把选中的情景切换为高油价（High Oil Price） (key: c11_cross_region_linkage, primary: interaction_function, secondary: cross_region_linkage, weight: 0.0588)

预设状态：情景对比部分已加载，当前选中的是高油价以外的任意一个情景（页面打开时默认选中哪个都可以）

操作：把选中的情景切换为高油价（High Oil Price）

期望结果：假设参数区与对比图形同时跟着更新到同一个情景：参数区显示高油价情景的假设（2050 年布伦特原油每桶 170 美元），图形中对应高油价的那一项被突出显示或成为当前项，且两处指向的是同一个情景，不存在参数区已切换而图形仍停留在上一个情景的情况。突出显示采用高亮、变色、加粗或指示标记均可。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 在情景的关键词输入框中输入 Renewables (key: c12_search_filtering, primary: interaction_function, secondary: search_filtering, weight: 0.0588)

预设状态：情景列表完整显示全部九个核心情景

操作：在情景的关键词输入框中输入 Renewables

期望结果：列表只保留名称含 Renewables 的两个情景（High Renewables Cost 与 Low Renewables Cost），其余情景不再显示；清空输入框后九个情景的完整列表恢复。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 查看天然气领域的结论（若页面把各领域做成可切换的 (key: c13_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0588)

预设状态：页面已打开分领域结论部分，当前显示其中一个领域

操作：查看天然气领域的结论（若页面把各领域做成可切换的，先切换过去）

期望结果：能读到天然气领域的结论：天然气消费增长主要来自工业用途和出口。若采用切换形式，切过去后不残留上一个领域的结论；若各领域并排或依次铺开，各段同时可见且能分辨归属。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 通过页面内的导航跳转到后续专题情景部分 (key: c14_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0588)

预设状态：页面停留在顶部

操作：通过页面内的导航跳转到后续专题情景部分

期望结果：页面滚动到该部分，且该部分的标题实际停留在可视区域内、没有被顶部导航条压住或遮挡，能直接读到其中至少一个专题情景的名称。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 从上到下滚动浏览全页 (key: c15_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0588)

预设状态：在 1440×900 桌面视口打开页面

操作：从上到下滚动浏览全页

期望结果：内容分区呈现，核心判断、情景总览、假设参数、情景对比、后续专题各成一块且次序合理；区块之间没有重叠或互相遮挡，对比图形和情景列表都完整可见、未被容器截断。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 查看整体配色与文字层级 (key: c16_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0588)

预设状态：在 1440×900 桌面视口打开页面

操作：查看整体配色与文字层级

期望结果：正文与背景是深浅分明的搭配（深字浅底或浅字深底），数字在各自底色上清楚可读；标题与正文在字号或字重上至少有一项明显不同；强调色只出现在标题、关键数值、选中态这类局部元素上，没有整屏铺满的高饱和色块。具体用什么色系不限。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 滚动浏览全页 (key: c17_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0592)

预设状态：在 375×812 手机视口打开页面（视口 375×812）

操作：滚动浏览全页，并切换一次选中的情景

期望结果：页面没有横向溢出，主内容区块不再左右并排；对比图形与情景列表在自己的容器内完整查看或横向滚动而不被截断，情景选择与筛选仍然可用。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_025_aeo2022_energy_scenarios

## Skills

## Env

## Warmup
