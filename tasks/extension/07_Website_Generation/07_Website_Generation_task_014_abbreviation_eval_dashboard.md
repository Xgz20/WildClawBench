---
id: 07_Website_Generation_task_014_abbreviation_eval_dashboard
name: 缩写识别评测结果看板
category: 07_Website_Generation
sub_category: 数据分析与决策
task_type: 论文评测结果看板
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 缩写识别评测结果看板

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我想把一篇论文里的评测结果做成一个中文的结果看板。这篇论文研究的是斯洛文尼亚传记词典里的缩写问题——文本里缩写太多，会让 NLP 工具分词出错、识别不出人名地名，论文提出了自动识别缩写并把它还原成完整词的方法，还做了好几组对比实验。论文原文和逐页图片都放在 `/tmp_workspace/assets` 目录中，请直接使用，页面上的数据要和论文一致。

页面是给想快速判断"这套方法到底有没有用"的人看的。所以除了交代清楚问题背景和用的是什么数据，重点是把论文里那几张实验表格搬上网页，让人能直接比出来：几种识别方法各自的准确率和召回率差多少、把缩写还原之后命名实体识别的效果又提升了多少。表格要能按某一列排序，方便一眼找出表现最好的方法。命名实体识别的结果论文里是分实体类别给的，可以做成能切换查看的形式，不必一次全铺开。

另外也请方便别人引用这篇论文，并能打开论文原文。整页板块不少，请让人能在几个部分之间快速跳转。整体做成清爽的数据看板风格，数字要醒目、好读。手机上也要能正常浏览。

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

### Criterion 1: 查看首屏 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：首次打开页面

操作：查看首屏

期望结果：可见论文标题 Dealing with Abbreviations in the Slovenian Biographical Lexicon，作者一栏恰为 Angel Daza、Antske Fokkens、Tomaž Erjavec 三人，没有混入论文之外的名字；并有一句中文说明这项工作在解决什么问题。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看问题背景说明 (key: c02_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：页面已打开

操作：查看问题背景说明

期望结果：说明缩写会造成分词错误和未登录词问题，并点出这在斯洛文尼亚语这类资源较少的语言上更严重；不是泛泛一句“缩写不好处理”。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看数据来源说明 (key: c03_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载数据集区

操作：查看数据来源说明

期望结果：写明评测集来自斯洛文尼亚传记词典，词典共收录 5,047 篇传记，本文从中随机抽取 51 篇构建评测集；这两个数字与论文一致。词典的卷数与出版年份可写可不写。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 查看训练／开发／测试集的切分统计 (key: c04_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0555)

预设状态：页面已加载数据集区

操作：查看训练／开发／测试集的切分统计

期望结果：以表格或等价方式给出三个划分的句子数、缩写总数、唯一缩写数和未见缩写数：训练 458／1385／399／0，开发 66／236／130／33，测试 131／420／181／70，合计 655 句、2041 个缩写、710 个唯一缩写。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看缩写对命名实体识别的影响 (key: c05_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载缩写影响区

操作：查看缩写对命名实体识别的影响

期望结果：能对照看出缩写对命名实体识别的影响：原始带缩写的文本与缩写全部正确展开后，宏平均 F1 存在 30 分以上的差距。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 查看四种基线方法的识别效果 (key: c06_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0555)

预设状态：页面已加载方法对比区

操作：查看四种基线方法的识别效果

期望结果：四行数值与论文一致：GigaFida 词典 89.36／20.00／32.68，Hunspell 词典 80.81／71.19／75.70，语料二元组 95.85／76.90／85.34，二元组+词典 73.27／95.95／83.09；顺序可以不同，但数值不能改。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 查看论文所提分类器的结果 (key: c07_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载方法对比区

操作：查看论文所提分类器的结果

期望结果：给出 SloBERTa 分类器在测试集上的 93.94／98.10／95.97，并能看出它比最好的基线（语料二元组 85.34）高约 10 分。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看缩写还原之后的识别效果 (key: c08_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载还原效果区

操作：查看缩写还原之后的识别效果

期望结果：说明测试集 420 个缩写中有 154 个被自动还原，宏平均 F1 从原始的 27.16 提升到 49.64（约 22 分），并点明 59.31 是用人工正确展开时的上限。三个数字都要出现且不能改。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 查看作者对这套方法的自我评价 (key: c09_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：完整浏览页面

操作：查看作者对这套方法的自我评价

期望结果：能看出作者认为当前的缩写还原方法仍然比较简单、后续打算继续改进；不是只讲方法的好处。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式） (key: c10_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0555)

预设状态：页面已打开

操作：点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式）

期望结果：页面滚动或切换到对应区域，该区域标题和主要内容进入可见范围，导航不会跳到空白处。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 对方法对比表格按某一列排序（点击表头或页面提供的其他排序方式） (key: c11_search_filtering, primary: interaction_function, secondary: search_filtering, weight: 0.0555)

预设状态：方法对比表格已显示四种基线方法

操作：对方法对比表格按某一列排序（点击表头或页面提供的其他排序方式）

期望结果：排序后行顺序按该列单调重排，该列的最高值与最低值分别位于表格两端；再操作一次可得到相反顺序。以操作前的状态为基准，两次操作后的顺序互为逆序即可，不限定排序哪一列、也不限定首次操作得到升序还是降序。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 对照原始文本与缩写已展开两种状态下的识别效果 (key: c12_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0555)

预设状态：缩写影响区已显示一种文本状态的识别结果

操作：对照原始文本与缩写已展开两种状态下的识别效果

期望结果：能获得两种状态下各实体类别的数值，且确实不同——例如人名 PER 的 F1 在原始文本下是 33.85、缩写已展开后是 70.59。两状态并排展示、分表罗列或切换查看均可；若采用切换，切换后数值要真的更换。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 查看某一个实体类别（例如地名 LOC）的三项指标 (key: c13_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0555)

预设状态：还原效果区已显示各实体类别的识别结果

操作：查看某一个实体类别（例如地名 LOC）的三项指标

期望结果：能读到该类别的精确率、召回率和 F1 三个数值。若采用选中式展示，换选另一个当前未选中的类别时数值随之更换、不停留在上一个；若一次性铺开全部类别，各类别三项指标齐全即可。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 查看引用信息 (key: c14_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0555)

预设状态：页面已滚动到引用区域

操作：查看引用信息

期望结果：引用文本完整可见且便于取用。若页面提供复制按钮，点击后要给出明确的复制成功反馈；若采用可选中的代码块或提供下载，同样成立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 点击查看论文原文的入口 (key: c15_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0555)

预设状态：页面已打开

操作：点击查看论文原文的入口

期望结果：入口指向随题提供的 `/tmp_workspace/assets/paper.pdf` 或等价的本地论文副本，请求该路径能取到这份 PDF。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 查看首屏、数据集区和方法对比区 (key: c16_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0555)

预设状态：在 1440×900 桌面视口打开页面

操作：查看首屏、数据集区和方法对比区

期望结果：导航、关键指标和各张表格层级清楚，表格列对齐一致、数值单元格不折行，相邻卡片之间没有重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 观察整体页面 (key: c17_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0555)

预设状态：在 1440×900 桌面视口打开页面

操作：观察整体页面

期望结果：整体呈现清爽的数据看板气质：关键数字明显大于正文（约 2 倍以上），表格与卡片有清晰边界，强调色数量克制；本文方法在视觉上与基线方法可区分（背景、边框、文字色或独立卡片等任一手段均可）。不像堆满装饰的营销落地页。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 18: 滚动浏览，并对表格排序、切换实体类别 (key: c18_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0565)

预设状态：在 375×812 手机视口打开页面（视口 375×812）

操作：滚动浏览，并对表格排序、切换实体类别

期望结果：主内容区块不再左右并排（统计卡这类小卡片允许两列）；较宽的表格在自己的容器内横向滚动查看，表头和数值不被截断，排序与切换仍然可用。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_014_abbreviation_eval_dashboard

## Skills

## Env

## Warmup
