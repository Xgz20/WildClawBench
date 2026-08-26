---
id: 07_Website_Generation_task_024_kyrgyzstan_wage_gap_brief
name: 吉尔吉斯斯坦性别工资差距研究简报
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 研究成果简报页
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 吉尔吉斯斯坦性别工资差距研究简报

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我手上有一份关于吉尔吉斯斯坦性别工资差距的研究报告演示稿，放在 `/tmp_workspace/assets` 目录里。想把它做成一个网页版的研究简报，让没时间读完整份报告的人也能弄清楚这项研究用了什么数据、什么方法，最后得出了什么结论。

内容都以这份原件为准，数字和表格照原样呈现，不要改写，也不要补充原件里没有的东西。

研究里的几张统计表都比较大，可以做成切换查看，不必一次全部铺开。最后那组分解结果是全文的落点，请给它配一张图，比只列数字更容易看出两个年份的差别。文中有几个计量方法的专有名词，请给出解释，让没有统计背景的人也能看懂。文末的参考文献条目不少，请让人能按关键词筛选，快速找到某一条。

整页内容不短，请让人能在几个部分之间快速跳转。

视觉上希望干净克制，像一份正式的研究简报，段落层次清楚，不要大段文字堆在一起。手机上也要能正常看。

这份演示稿以 CC BY 4.0 许可发布，作者是 Irina Kovaleva，请在页面上标注出处和许可。

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

### Criterion 1: 查看首屏 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0666)

预设状态：首次打开页面

操作：查看首屏

期望结果：可见研究标题（吉尔吉斯斯坦的性别工资差距与收入不平等，或与之对应的英文原题 Gender Wage Gap and Income Inequality in Kyrgyzstan），作者写明 Irina Kovaleva 且没有混入原件之外的人名，并有一句话说明这项研究考察的是 2016 至 2019 年吉尔吉斯斯坦的性别工资差距。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看研究背景 (key: c02_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已打开背景说明部分

操作：查看研究背景

期望结果：写明国家统计委员会的口径下 2018 年女性收入比男性低 28.4%，以及政府在 2018—2019 年对教师、医疗和社会服务人员实施加薪改革后，到 2019 年底差距收窄到 23%，收窄幅度 5.4 个百分点。三个数字都要与原件一致，不能只给其中一个。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看研究使用的调查数据说明 (key: c03_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已打开数据来源部分

操作：查看研究使用的调查数据说明

期望结果：说明数据来自“Life in Kyrgyzstan”（LiK）追踪调查，采集期为 2010 至 2019 年，采用分层两阶段随机抽样，样本为 3000 户家庭、8100 多名个人，覆盖全国各州以及比什凯克和奥什两座主要城市。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 查看研究使用了哪些分析方法 (key: c04_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0666)

预设状态：页面已打开方法部分

操作：查看研究使用了哪些分析方法

期望结果：三种方法都列出且名称正确：普通最小二乘（OLS）、Heckman（1979）样本选择校正、Oaxaca-Blinder（1973）分解；并说明经验框架建立在 Mincer（1974）的收入方程之上。不得出现原件没有使用的方法。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看 Oaxaca-Blinder 分解这个名词的解释（若解释需要点开才显示 (key: c05_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已打开方法部分

操作：查看 Oaxaca-Blinder 分解这个名词的解释（若解释需要点开才显示，先打开它；若已经展开或本来就直接写在正文里，直接阅读即可）

期望结果：Oaxaca-Blinder 分解有一段与该名词对应的解释，说明它把两组之间的差距拆成可由可观测特征差异解释的部分和归因于系数差异的部分；解释内容与名词匹配，没有张冠李戴。行内直接展示、折叠展开或点开浮层都可以。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 逐行核对该表 2016 与 2019 两列的数值 (key: c06_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0666)

预设状态：页面已打开统计结果部分，当前显示的是 Oaxaca-Blinder 分解结果那张表（若页面把几张表做成可切换的，先切换过去）

操作：逐行核对该表 2016 与 2019 两列的数值

期望结果：观测数为 2,925（2016）与 2,545（2019）；Difference 为 .1276371 与 .1375113；Explained 为 -.0417533 与 -.0470802；Unexplained 为 .1693904 与 .1845915。四行数值与原件一致，两个年份分列可辨。原件采用省略整数位零的写法，页面补成 0.1276371 这类等价形式同样算通过，但不接受四舍五入到更少位数。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 查看研究结论 (key: c07_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已打开结论部分

操作：查看研究结论

期望结果：写明 2016 年男性平均比女性多挣 12.8%、2019 年为 13.8%，即总体差距在扩大；并指出无法由可观测特征解释的部分明显上升，可能意味着歧视或其他未观测因素的作用变大。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看分解结果配的图形 (key: c08_data_visualization, primary: content_structure, secondary: data_visualization, weight: 0.0666)

预设状态：页面已打开分解结果部分

操作：查看分解结果配的图形

期望结果：分解结果以图形方式呈现（柱状、条形、点线等均可），2016 与 2019 两个年份可对照，可解释部分与不可解释部分能分辨；图形的长度、高度或位置与数值方向一致——不可解释部分 2019 高于 2016，可解释部分两年都在零以下。仅有一段文字或一张纯数字表格不算。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 查看出处与许可说明 (key: c09_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已加载完成

操作：查看出处与许可说明

期望结果：页面上能读到作者 Irina Kovaleva 与 CC BY 4.0 许可声明，二者都出现且指向同一份原始演示稿。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看 OLS 回归结果那张表（若页面把几张表做成可切换的 (key: c10_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0666)

预设状态：统计结果部分已显示其中一张统计表

操作：查看 OLS 回归结果那张表（若页面把几张表做成可切换的，先切换过去）

期望结果：能读到该表的分样本量：2016 年男性 974、女性 870，2019 年男性 879、女性 636。若采用切换形式，切过去后不残留上一张表的内容；若几张表并排或依次铺开，各表同时可见且能分辨哪张是哪张。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 在参考文献的关键词输入框中输入 Heckman (key: c11_search_filtering, primary: interaction_function, secondary: search_filtering, weight: 0.0666)

预设状态：页面已滚动到参考文献部分，能看到完整的文献列表（约 20 条；若默认折叠，先展开）

操作：在参考文献的关键词输入框中输入 Heckman

期望结果：列表只保留标题或作者含 Heckman 的那一条（Heckman, J. J. (1979). Sample selection bias as a specification error），其余不匹配的文献不再显示；清空输入框后完整列表恢复。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 通过页面内的章节导航跳转到结论部分 (key: c12_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0666)

预设状态：页面停留在顶部

操作：通过页面内的章节导航跳转到结论部分

期望结果：页面滚动到结论部分，且该部分的标题实际停留在可视区域内、没有被顶部导航条压住或遮挡，能直接读到结论正文的开头。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 从上到下滚动浏览全页 (key: c13_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0666)

预设状态：在 1440×900 桌面视口打开页面

操作：从上到下滚动浏览全页

期望结果：内容按研究简报的顺序分区呈现，背景、数据、方法、统计结果、结论、参考文献各成一块且次序合理；区块之间没有重叠或互相遮挡，统计表未被容器截断。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 查看整体配色与文字层级 (key: c14_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0666)

预设状态：在 1440×900 桌面视口打开页面

操作：查看整体配色与文字层级

期望结果：正文与背景是深浅分明的搭配（深字浅底或浅字深底），长段落读起来不吃力；章节标题与正文在字号或字重上至少有一项明显不同，不是全篇一个样式铺平；强调色只出现在标题、关键数值、选中态这类局部元素上，没有整屏铺满的高饱和色块。具体用什么色系不限。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 滚动浏览全页 (key: c15_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0676)

预设状态：在 375×812 手机视口打开页面（视口 375×812）

操作：滚动浏览全页，并查看其中一张统计表

期望结果：页面没有横向溢出，主内容区块不再左右并排；较宽的统计表在自己的容器内横向滚动查看而不被截断，章节导航与参考文献筛选仍然可用。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_024_kyrgyzstan_wage_gap_brief

## Skills

## Env

## Warmup
