---
id: 07_Website_Generation_task_012_interactive3d_paper_site
name: Interactive3D论文探索站
category: 07_Website_Generation
sub_category: 内容与知识生产
task_type: 交互式学术项目主页
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# Interactive3D论文探索站

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我想给一篇 CVPR 2024 的论文 Interactive3D 做一个中文的项目主页，让读者不用读完整篇论文，也能看懂这项研究在做什么、方法是怎样的、效果如何。

论文原文和配套素材都放在 `/tmp_workspace/assets` 目录中，请直接使用，页面上的内容要和论文一致。

页面整体应该像一个正式发布的研究项目官网，而不是把论文正文照搬过来。论文中的插图和那段演示视频都要用上，实验部分也请把与其他方法比较的数据一并呈现。内容较多的部分可以做成切换查看，不必一次全部铺开；整页内容不短，请让读者能在几个部分之间快速跳转。文中有几个专业名词，最好能让读者点开看到解释。另外也请方便读者引用这篇论文，并能打开论文原文。

视觉上专业、现代一些，给图片和视频留出足够空间，避免大段文字堆叠。手机上也要能正常浏览。

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

### Criterion 1: 查看首屏标题区 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.05)

预设状态：首次打开页面

操作：查看首屏标题区

期望结果：清楚显示 Interactive3D 论文标题、CVPR 2024、至少一个相关机构，以及一句概括这项研究在做什么的中文说明；作者一栏完整列出 Shaocong Dong、Lihe Ding、Zhanpeng Huang、Zibin Wang、Tianfan Xue、Dan Xu 六人，没有混入论文之外的名字。标题和作者是页面上的可见文字，不是只存在于论文截图里。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 阅读摘要和方法导语 (key: c02_detail_display, primary: content_structure, secondary: detail_display, weight: 0.05)

预设状态：页面已打开

操作：阅读摘要和方法导语

期望结果：页面用中文说明传统 3D 生成控制不够精细这一问题，并提到 Gaussian Splatting 与 InstantNGP 的组合，内容不是泛泛的“AI 生成”介绍。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看两阶段流程 (key: c03_information_organization, primary: content_structure, secondary: information_organization, weight: 0.05)

预设状态：滚动到方法区

操作：查看两阶段流程

期望结果：能同时辨认 Gaussian Splatting 和 InstantNGP / Interactive Hash Refinement 两个阶段，并能看到从交互生成到局部细化的流程关系；页面可以用编号、标签或其他等价方式表达阶段顺序。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 浏览交互操作的清单区 (key: c04_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.05)

预设状态：方法区已加载

操作：浏览交互操作的清单区

期望结果：覆盖论文第一阶段的四类交互——添加与删除部件、几何变换、形变与刚性拖拽、语义编辑，并且能看到第二阶段的 Interactive Hash Refinement；每项都有论文语境下的中文说明。允许把形变拖拽和刚性拖拽拆成两条分别说明。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看定量对比部分 (key: c05_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.05)

预设状态：页面已加载结果浏览区

操作：查看定量对比部分

期望结果：页面用表格或等价方式呈现论文的定量对比，指标写明是 CLIP R-Precision：Interactive3D 一行是 0.94 和 50min，并且至少还有一个被比较的方法数值也正确（DreamFusion 0.67／1.1h，或 ProlificDreamer 0.83／3.4h）；不是只写一句“效果更好”，也不是把数字改成别的值。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式） (key: c06_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.05)

预设状态：页面已打开

操作：点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式）

期望结果：页面滚动或切换到对应内容区，目标区域标题和主要内容进入可见范围，导航不会跳到空白页。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 查看第二阶段的说明（若页面把两个阶段做成可切换的 (key: c07_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.05)

预设状态：停留在两阶段方法区，当前显示 Gaussian Splatting

操作：查看第二阶段的说明（若页面把两个阶段做成可切换的，先切换过去）

期望结果：能读到第二阶段的四点内容：表示转换、选择需要细化的局部区域、哈希细化、表面或纹理增强。若采用切换形式，切过去后不残留第一阶段的高斯球操作说明；若两阶段并排展示，两段内容同时完整可见且能分辨各属哪个阶段。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看语义编辑和几何变换这两项操作的说明 (key: c08_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.05)

预设状态：交互操作实验室已显示默认操作

操作：查看语义编辑和几何变换这两项操作的说明

期望结果：两项都有各自的文字说明且内容不同：语义编辑涉及对局部施加语义改变，几何变换涉及改变结构。若采用选中式卡片，当前选中项要能分辨；若并排铺开，两项说明同时可见即可。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 查看形变拖拽这一项 (key: c09_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.05)

预设状态：已进入交互操作展示区

操作：查看形变拖拽这一项

期望结果：该项显示形变拖拽的说明及其自然语言 prompt，并能看到随题提供的本地演示视频（video 的来源指向本地文件）。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 让演示视频开始播放 (key: c10_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.05)

预设状态：形变拖拽详情中已出现视频播放器

操作：让演示视频开始播放

期望结果：视频进入播放状态，或 3 秒内播放进度发生增长；自动播放的实现同样成立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 浏览结果展示区 (key: c11_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.05)

预设状态：结果浏览区已显示一个结果主题

操作：浏览结果展示区

期望结果：结果区至少呈现两组不同主题的内容，每组都有自己的图片或预览、标题和解释文字，彼此不是同一段重复文案。若做成可切换的形式，切换后三者一同更换，不残留上一组内容。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 查看术语解释（若需要点开或展开 (key: c12_detail_display, primary: content_structure, secondary: detail_display, weight: 0.05)

预设状态：术语解释区已显示 Gaussian Splatting、InstantNGP 或 SDS

操作：查看术语解释（若需要点开或展开，按页面提供的方式操作）

期望结果：能获得术语的中文解释，且各术语解释互不相同、与术语对应；其中 SDS 的解释要与论文中的用法一致（一种用于优化 3D 生成的损失），不编造论文里没有的含义。内联展开、弹层或悬浮提示等形式均可。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 查看引用信息 (key: c13_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.05)

预设状态：页面已滚动到 BibTeX 区域

操作：查看引用信息

期望结果：BibTeX 全文可见且便于取用。若页面提供复制按钮，点击后要给出明确的复制成功反馈；若采用可选中的代码块或提供 .bib 下载，同样成立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 查看首屏、方法区和交互操作展示区 (key: c14_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.05)

预设状态：在 1440×900 桌面视口打开页面

操作：查看首屏、方法区和交互操作展示区

期望结果：导航、首屏信息、两阶段流程和媒体内容层级清楚；论文图片和视频有充足展示宽度，相邻文本块与卡片的包围盒不重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 观察整体页面 (key: c15_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.05)

预设状态：在 1440×900 桌面视口打开页面

操作：观察整体页面

期望结果：整体是一套统一、克制的视觉方案：主色与强调色成体系不杂乱，正文与背景对比度足够阅读，图片和视频有充足展示宽度。视觉上像正式发布的研究项目主页，而不是后台管理界面或堆满装饰的营销落地页。深色或浅色都可以，不限定具体配色。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 滚动并查看方法阶段、操作项和结果内容 (key: c16_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.05)

预设状态：在 375×812 手机视口打开页面并进入方法或演示区（视口 375×812）

操作：滚动并查看方法阶段、操作项和结果内容

期望结果：主内容区块不再左右并排；导航、卡片、图片/视频、按钮和长文本都没有被截断，各处切换与展开仍然可用，视频控件仍可操作。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 检查核心信息的承载方式 (key: c17_information_organization, primary: content_structure, secondary: information_organization, weight: 0.05)

预设状态：完整浏览页面主要内容区

操作：检查核心信息的承载方式

期望结果：论文标题、作者、动机、方法、实验结果、引用等核心信息以页面上可选中的文字承载，不是只靠 PDF 截图或图片里的文字来呈现。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 18: 点击查看论文原文的入口 (key: c18_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.05)

预设状态：页面已打开且本地素材可访问

操作：点击查看论文原文的入口

期望结果：入口指向随题提供的 `/tmp_workspace/assets/paper.pdf` 或等价的本地论文副本，请求该路径能取到这份 PDF。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 19: 查看刚性拖拽这一项的说明 (key: c19_detail_display, primary: content_structure, secondary: detail_display, weight: 0.05)

预设状态：交互操作区已打开

操作：查看刚性拖拽这一项的说明

期望结果：说明里给出论文中真实存在的具体实例（具体物体 + 具体动作），例如把霸王龙的头从朝前拖到朝右；不能是凭空编造、论文里查不到的例子。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 20: 查看关于第二阶段为什么要换表示的说明 (key: c20_detail_display, primary: content_structure, secondary: detail_display, weight: 0.05)

预设状态：已进入方法区，并查看到关于第二阶段的说明（如需点击切换则先切换）

操作：查看关于第二阶段为什么要换表示的说明

期望结果：页面说清楚换表示的原因：高斯球便于直接交互编辑，但难以重建高质量几何，所以要转到 InstantNGP 继续细化并提取表面；不是只说“第二阶段用 InstantNGP”而不给原因。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_012_interactive3d_paper_site

## Skills

## Env

## Warmup
