---
id: 07_Website_Generation_task_016_commentator_tool_page
name: COMMENTATOR标注工具介绍页
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 开发者工具产品介绍页
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# COMMENTATOR标注工具介绍页

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我们做了一个叫 COMMENTATOR 的文本标注工具，专门用来标注那种一句话里中英夹杂的混合语言文本。想给它做一个中文的产品介绍页。工具怎么设计的、和别的工具比下来如何，都写在一篇论文里，论文原文和逐页图片都放在 `/tmp_workspace/assets` 目录中，请直接使用，页面上的内容要和论文一致。

页面要能让人快速判断这个工具值不值得用：支持哪些标注任务、标注员和管理员各自能做什么、跟市面上已有的工具比起来快多少。速度那部分论文里有实测数据，做成对比图表会比只写一句"更快"有说服力；两类标注任务的耗时可以分开看。

工具目前还有几个没做到的地方，论文里如实列了出来，也请照实放上去，别只讲优点。另外请方便别人引用这篇论文，并能打开论文原文。

整页内容不少，请让人能在几个板块之间快速跳转。风格做成偏产品的介绍页，清爽利落，重点信息一眼能抓到。手机上也要能正常浏览。

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

### Criterion 1: 查看工具的基本信息 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0666)

预设状态：首次打开页面

操作：查看工具的基本信息

期望结果：页面上可见工具名 COMMENTATOR 和一句中文说明它是做什么的；论文的五位作者 Rajvee Sheth、Shubh Nisar、Heenaben Prajapati、Himanshu Beniwal、Mayank Singh 在页面某处完整列出（首屏或引用区皆可），没有混入论文之外的名字。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看工具支持的标注任务 (key: c02_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0666)

预设状态：页面已加载功能区

操作：查看工具支持的标注任务

期望结果：列出当前版本支持的三项任务：词级语言识别（LID）、词级词性标注（POS）、句级主体语言识别（MLI），每项都有中文说明；不能把论文说明将来才要支持的任务（如命名实体识别、拼写纠正、机器翻译）写成已支持。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看标注员一侧的功能 (key: c03_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已加载角色说明区

操作：查看标注员一侧的功能

期望结果：说明标注员面板由三个页面组成：任务选择的落地页、各任务的标注页、以及可回看并修改历史标注的历史与编辑页。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 查看管理员一侧的功能 (key: c04_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已加载角色说明区

操作：查看管理员一侧的功能

期望结果：说明管理员可以做三件事：用 CSV 上传待标注句子；分析标注质量，用 Cohen's Kappa 衡量标注者间一致性、用代码混合指数 CMI 衡量文本的混合程度；把标注结果导出成 CSV，并支持按一致性和 CMI 做条件筛选。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看 CMI 指标的取值范围 (key: c05_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已加载指标说明

操作：查看 CMI 指标的取值范围

期望结果：若页面提到代码混合指数 CMI，其取值范围须写对：0 到 100，0 表示单语、100 表示高度混合；不能把范围或含义写错。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 查看六个工具的标注耗时 (key: c06_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0666)

预设状态：页面已加载耗时对比区

操作：查看六个工具的标注耗时

期望结果：以表格或图表给出六个工具在 LID 与 POS 两项任务上的平均标注耗时（秒），数值与论文一致：YEDDA 757.00 / 1370.66，MarkUp 1192.33 / 1579.00，INCEpTION 1040.66 / 1714.66，UBIAI 690.66 / 748.33，GATE 1118.33 / 1579.00，COMMENTATOR 138.33 / 337.66。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 查看提速幅度的结论 (key: c07_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0666)

预设状态：页面已加载耗时对比区

操作：查看提速幅度的结论

期望结果：点明与最接近的对手 UBIAI 相比，COMMENTATOR 在 LID 上快约 5 倍、在 POS 上快约 2 倍；两个倍数和被比较的工具名都不能写错。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看工具当前的不足 (key: c08_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0666)

预设状态：页面已加载局限区

操作：查看工具当前的不足

期望结果：完整列出论文自陈的三条局限：目前还不是网页版、正在开发中；界面上还不支持直接接入预训练模型做预测；标注后分析还比较基础，未来才会加入 Fleiss' Kappa、Krippendorff's Alpha 和组内相关系数等指标。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式） (key: c09_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0666)

预设状态：页面已打开

操作：点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式）

期望结果：页面滚动或切换到对应区域，该区域标题和主要内容进入可见范围，导航不会跳到空白处。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看标注员与管理员各自能做什么 (key: c10_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0666)

预设状态：角色说明区已显示一类角色

操作：查看标注员与管理员各自能做什么

期望结果：两类角色的功能都能读到，且两侧内容确实不同。并排展示或切换查看均可。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 查看引用信息 (key: c11_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0666)

预设状态：页面已滚动到引用区域

操作：查看引用信息

期望结果：引用文本完整可见且便于取用。若页面提供复制按钮，点击后要给出明确的复制成功反馈；若采用可选中的代码块或提供下载，同样成立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 点击查看论文原文的入口 (key: c12_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0666)

预设状态：页面已打开

操作：点击查看论文原文的入口

期望结果：入口指向随题提供的 `/tmp_workspace/assets/paper.pdf` 或等价的本地论文副本，请求该路径能取到这份 PDF。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 查看首屏、功能区和耗时对比区 (key: c13_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0666)

预设状态：在 1440×900 桌面视口打开页面

操作：查看首屏、功能区和耗时对比区

期望结果：导航、首屏卖点、任务卡片和对比图表层级清楚：正文列居中且有足够宽度，对比图表有充足展示宽度，相邻文本块与卡片的包围盒不重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 观察整体页面 (key: c14_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0666)

预设状态：在 1440×900 桌面视口打开页面

操作：观察整体页面

期望结果：整体呈现开发者工具产品页的气质：强调色数量克制、分区之间有可见分隔、卡片边界清晰；COMMENTATOR 在耗时对比中被明显突出（配色、字重、位置或独立标注等任一方式均可）。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 滚动浏览，并切换标注任务、切换耗时任务、展开一条局限 (key: c15_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0676)

预设状态：在 375×812 手机视口打开页面（视口 375×812）

操作：滚动浏览，并切换标注任务、切换耗时任务、展开一条局限

期望结果：主内容区块不再左右并排（统计卡这类小卡片允许两列）；较宽的表格或图表在自己的容器内横向滚动查看而不被截断，各处切换与展开仍然可用。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_016_commentator_tool_page

## Skills

## Env

## Warmup
