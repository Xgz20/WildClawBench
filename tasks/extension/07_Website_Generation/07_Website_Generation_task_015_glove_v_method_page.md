---
id: 07_Website_Generation_task_015_glove_v_method_page
name: GloVe-V方法讲解页
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 论文方法讲解页
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# GloVe-V方法讲解页

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我想把一篇论文的方法部分做成一个中文讲解页面。论文提出的方法叫 GloVe-V，用来给词向量算出统计方差——以前大家用词向量只有一个点估计，没办法判断由它得出的结论到底稳不稳。论文原文和逐页图片都放在 `/tmp_workspace/assets` 目录中，请直接使用，页面上的内容要和论文一致。

页面是给想搞懂这套方法怎么一步步推出来的人看的。论文里的推导分了好几步，公式也不少，希望能顺着推导讲清楚，每一步都配上对应的公式和一句人话解释，而不是把公式堆成一整片。论文里的符号用得比较讲究，最好单独整理一张符号说明，让人看推导时随时能查。

方法能用在什么情况、不能用在什么情况，论文里交代得很清楚，也请如实列出来，别只讲好的一面。实验用的语料和主要参数也交代一下，方便别人对照。另外请方便别人引用这篇论文，并能打开论文原文。

推导内容不短，请让人能在几个部分之间快速跳转。页面要安静、好读，公式不要糊成一团。手机上也要能正常浏览。

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

### Criterion 1: 查看首屏与引用区 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：首次打开页面

操作：查看首屏与引用区

期望结果：在首屏或引用区可见论文标题 Statistical Uncertainty in Word Embeddings: GloVe-V，四位作者 Andrea Vallebueno、Cassandra Handan-Nader、Christopher D. Manning、Daniel E. Ho 姓名完整且没有混入论文之外的名字，机构写明 Stanford University，并有一句中文说明这套方法在解决什么问题。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看问题背景说明 (key: c02_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：页面已打开

操作：查看问题背景说明

期望结果：说明现有做法只用词向量的点估计、无法评估结论受数据稀疏影响的程度；并指出已有的自助法（bootstrap）与置换检验在大规模数据上计算不可行，且它们处理的是文档或词表选择带来的不确定性。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看符号约定 (key: c03_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0555)

预设状态：页面已加载符号说明区

操作：查看符号约定

期望结果：给出论文的书写约定：大写粗体表示矩阵、小写粗体表示向量、常规非粗体表示标量、花体表示集合；并至少解释 D（词向量维度）、V（词表大小）、K（与某个词共现次数非零的列下标集合）三个符号的含义。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 浏览整条推导路线 (key: c04_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：页面已加载推导区

操作：浏览整条推导路线

期望结果：推导按顺序分步呈现，从 GloVe 的代价函数出发，依次经过矩阵形式的低秩逼近、固定最优上下文向量后的加权最小二乘解、多元正态概率模型，最后到方差与协方差的估计；步骤顺序与论文一致，不是把公式无序堆在一起。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看方法的核心洞察 (key: c05_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：推导区已展开

操作：查看方法的核心洞察

期望结果：说清关键前提：把上下文向量和常数项固定在最优值后，GloVe 词向量正好是共现矩阵各行经加权对数变换后的多元正态模型的最优参数；并点明这里假设各行在给定最优参数时相互独立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 查看代价函数中权重函数的定义 (key: c06_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：推导区已展开

操作：查看代价函数中权重函数的定义

期望结果：写出论文采用的权重函数：当 x 小于 100 时取 (x/100) 的 3/4 次方，否则取 1；阈值与指数都不能写错。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 查看协方差可计算的前提 (key: c07_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载估计方法说明

操作：查看协方差可计算的前提

期望结果：说明协方差估计只对共现的唯一上下文词数量 |K| 大于词向量维度 D 的词才成立；并提到当二者接近时求逆会出现数值问题，论文改用 Moore-Penrose 伪逆来处理。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看方法的适用边界 (key: c08_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0555)

预设状态：页面已加载局限区

操作：查看方法的适用边界

期望结果：完整列出论文自陈的四条局限：只能为上下文词数超过向量维度的词计算方差；使用者需要拿到共现矩阵才能自行计算；方法只适用于 GloVe 这一个模型；所刻画的不确定性仅来自共现矩阵的稀疏性，语料选择、超参数以及上下文向量本身的不确定性都被当作固定值。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 查看维度对覆盖率影响的例子 (key: c09_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载局限区

操作：查看维度对覆盖率影响的例子

期望结果：给出论文举的对照：在规模较小的纽约时报标注语料上，用 50 维向量可以为 96% 的词计算方差，而用 300 维时这一比例降到 36%；两个百分比和两个维度都不能写错。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看实验用的语料与参数 (key: c10_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载实验设置说明

操作：查看实验用的语料与参数

期望结果：写明实验使用 20 世纪的美国历史英语语料库（COHA，1900–1999），词向量为 300 维，上下文窗口为对称的 8 个词。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式） (key: c11_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0555)

预设状态：页面已打开

操作：点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式）

期望结果：页面滚动或切换到对应区域，该区域标题和主要内容进入可见范围，导航不会跳到空白处。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 查看推导中另一步（例如多元正态模型那一步）的公式与解释 (key: c12_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：推导区已显示某一步

操作：查看推导中另一步（例如多元正态模型那一步）的公式与解释

期望结果：该步的公式与文字解释都能读到，且与代价函数那一步的公式确实不同。各步并列铺开或点击切换均可；若采用切换，切换后公式与解释一同更换，不残留上一步内容。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 查看某个符号（例如 K）的含义 (key: c13_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：符号说明区已显示若干符号

操作：查看某个符号（例如 K）的含义

期望结果：能获得该符号的中文解释，且各符号解释互不相同、与符号对应，不是统一的空泛提示。直接标注在符号表里、内联展开或点开弹层均可。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 查看引用信息 (key: c14_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0555)

预设状态：页面已滚动到引用区域

操作：查看引用信息

期望结果：引用文本完整可见且便于取用。若页面提供复制按钮，点击后要给出明确的复制成功反馈；若采用可选中的代码块或提供下载，同样成立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 点击查看论文原文的入口 (key: c15_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0555)

预设状态：页面已打开

操作：点击查看论文原文的入口

期望结果：入口指向随题提供的 `/tmp_workspace/assets/paper.pdf` 或等价的本地论文副本，请求该路径能取到这份 PDF。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 查看首屏、符号说明区和推导区 (key: c16_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0555)

预设状态：在 1440×900 桌面视口打开页面

操作：查看首屏、符号说明区和推导区

期望结果：公式与解释文字层级分明；公式完整显示不被裁切，下标与上标清楚可辨，相邻文本块与卡片的包围盒不重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 观察整体页面 (key: c17_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0555)

预设状态：在 1440×900 桌面视口打开页面

操作：观察整体页面

期望结果：整体是一份安静的技术讲解稿：页面主色不超过两三种、无大面积高饱和装饰，正文行距不小于常规阅读行距，公式区域与正文有可见的背景或边框区分。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 18: 滚动浏览，并切换推导步骤、点开一个符号 (key: c18_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0565)

预设状态：在 375×812 手机视口打开页面（视口 375×812）

操作：滚动浏览，并切换推导步骤、点开一个符号

期望结果：主内容区块不再左右并排（符号卡片这类小卡片允许两列）；较宽的公式在自己的容器内横向滚动查看而不被截断，切换与点开仍然可用。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_015_glove_v_method_page

## Skills

## Env

## Warmup
