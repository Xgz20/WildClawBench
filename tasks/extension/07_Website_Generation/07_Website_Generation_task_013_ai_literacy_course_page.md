---
id: 07_Website_Generation_task_013_ai_literacy_course_page
name: AI素养课程介绍页
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 课程介绍页
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# AI素养课程介绍页

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我想给一门叫《The Essentials of AI for Life and Society》的 AI 素养课做一个中文介绍页面。这门课怎么设计的、开完之后学员反馈如何，都写在一篇论文里，论文原文和逐页图片都放在 `/tmp_workspace/assets` 目录中，请直接使用，页面上的内容要和论文一致。

页面主要给两类人看：想报名的人，以及想照着开一门类似课程的老师。所以既要讲清楚这门课是什么、面向谁、怎么上、有什么要求，也要把开课之后的真实情况放出来——报名的人有多少、都是些什么人、学员怎么评价、AI 素养到底有没有提升、哪些地方没做好、后来又是怎么改的。

十四讲的课表要能看到每一讲讲什么、由谁来讲。学习效果那部分论文里有具体数字，做成图表比堆文字好读。内容比较多的地方可以做成切换查看，不必一次全部铺开；整页内容不短，请让人能在几个部分之间快速跳转。另外也请方便别人引用这篇论文，并能打开论文原文。

风格清爽、正式一些，像一个正经的课程主页。手机上也要能正常浏览。

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

### Criterion 1: 查看课程的基本信息 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：首次打开页面

操作：查看课程的基本信息

期望结果：页面显著位置可见课程英文全名 The Essentials of AI for Life and Society、开课单位 The University of Texas at Austin，以及这门课的基本形态：1 学分、14 周、线上、2023 年秋季首次开课；同时有一句中文说明这门课要做什么。这些是页面上的可见文字，不是只存在于论文截图里。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 查看课程面向人群与前置要求的说明 (key: c02_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：页面已打开

操作：查看课程面向人群与前置要求的说明

期望结果：写明这门课面向全校范围的非技术背景人群（学生、教职工乃至校外人员均可参加），且不需要任何技术或数学基础；不是笼统一句“适合所有人”。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 浏览十四讲课表 (key: c03_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0555)

预设状态：页面已加载课表区

操作：浏览十四讲课表

期望结果：完整列出 14 讲，每一讲都能看到讲授主题和主讲人；首讲是 AI100 研究报告导论，末讲是 Current and Future Directions，编号连续无重复。允许分组或折叠，只要 14 讲都能在页面内到达。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 核对几位主讲人与讲题的对应关系 (key: c04_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：课表区已可见

操作：核对几位主讲人与讲题的对应关系

期望结果：主讲人与主题对应正确：Computer Vision 是 Kristen Grauman，AI and Mis/disinformation 是 Matt Lease，AI Alignment and Existential Threats 是 Scott Aaronson，Intelligent Robotics 是 Luis Sentis；不能张冠李戴。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 查看报名与参与人数 (key: c05_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载参与情况区

操作：查看报名与参与人数

期望结果：给出总报名 788 人，并拆分为 132 名修学分的本科生、631 名校内旁听者、25 名校外参与者；同时说明校内旁听者覆盖了 UT Austin 全部 17 个学院。数字与论文一致，不能改成别的值。若页面采用论文另一处“131 名学生与 584 名旁听者”的说法，也算与论文一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 查看考核方式 (key: c06_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载课程要求区

操作：查看考核方式

期望结果：写明成绩由三部分构成：出勤 30%、随堂测验正确率 40%、每周反思完成情况 30%；三项占比与论文一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 查看课程评价分数 (key: c07_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0555)

预设状态：页面已加载学习效果区

操作：查看课程评价分数

期望结果：给出课程评价 4.23、授课教师 4.33，并与同学期自然科学学院全部课程的平均分 4.00 和 4.20 形成对照；不是只写一句“评价不错”。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 查看 AI 素养自评 10 道题的结果 (key: c08_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0555)

预设状态：页面已加载学习效果区

操作：查看 AI 素养自评 10 道题的结果

期望结果：呈现 10 道自评题各自的提升幅度，且能看出 10 项全部为正；第 3 题提升最大（+1.37），第 4 题提升最小（+0.97），并注明结果具有统计显著性（p<0.01）。题干为中文意译即可，不要求逐字一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式） (key: c09_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0555)

预设状态：页面已打开

操作：点击页面提供的区块跳转入口（顶部导航、侧边目录或等价形式）

期望结果：页面滚动或切换到对应区域，该区域的标题和主要内容进入可见范围，导航不会跳到空白处。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看某一讲的主讲人（若页面把课表做成点开看详情的形式 (key: c10_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0555)

预设状态：课表区已显示十四讲列表

操作：查看某一讲的主讲人（若页面把课表做成点开看详情的形式，先点开那一讲）

期望结果：能看到该讲对应的主讲人。若采用点开查看的形式，换一讲后详情随之更换、不停留在上一讲；若讲者信息直接内联在课表每一行里，同样成立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 查看自评图表中某一项（例如第 7 项）的完整题干 (key: c11_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0555)

预设状态：学习效果区已显示自评结果

操作：查看自评图表中某一项（例如第 7 项）的完整题干

期望结果：能读到该题的完整表述和它的提升幅度（第 7 题为 +1.19）。题干直接标在图表上，或点选后在详情里显示，两种形式都成立；若采用点选形式，换一项后内容随之更换。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 查看学员反馈里获得认可的部分和需要改进的部分 (key: c12_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0555)

预设状态：页面已加载反馈区

操作：查看学员反馈里获得认可的部分和需要改进的部分

期望结果：两类反馈都能读到且内容不同：获得认可的一侧包含讲者多样性与真实案例（22% 的开放式回答提到讲者阵容多样、37% 提到课程讲座本身）；需要改进的一侧包含阅读材料偏难（19% 集中在阅读材料的难度和长度）以及课堂互动不足。并排展示或切换查看均可。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 查看引用信息 (key: c13_operation_feedback, primary: interaction_function, secondary: operation_feedback, weight: 0.0555)

预设状态：页面已滚动到引用区域

操作：查看引用信息

期望结果：引用文本完整可见且便于取用。若页面提供复制按钮，点击后要给出明确的复制成功反馈；若采用可选中的代码块或提供下载，同样成立。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 点击查看论文原文的入口 (key: c14_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0555)

预设状态：页面已打开

操作：点击查看论文原文的入口

期望结果：入口指向随题提供的 `/tmp_workspace/assets/paper.pdf` 或等价的本地论文副本，请求该路径能取到这份 PDF。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 查看课程后续改版的说明 (key: c15_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0555)

预设状态：完整浏览页面

操作：查看课程后续改版的说明

期望结果：说明这门课已在 2024 年秋季升级为 3 学分版本，且能看出两点关键调整：新版只面向修学分的学生（不再招旁听），以及阅读材料被替换成更易读的博客与新闻报道。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 查看首屏、课表区和学习效果区 (key: c16_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0555)

预设状态：在 1440×900 桌面视口打开页面

操作：查看首屏、课表区和学习效果区

期望结果：导航、首屏信息、课表和图表层级清楚，长列表和图表有充足展示宽度，相邻文本块与卡片的包围盒不重叠。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 观察整体页面 (key: c17_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0555)

预设状态：在 1440×900 桌面视口打开页面

操作：观察整体页面

期望结果：整体呈现清爽、正式的课程主页气质：配色克制、字号层级分明、留白充足，视觉上不像后台管理系统，也不像堆满装饰的营销落地页。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 18: 滚动浏览，并查看课表中的一讲、查看自评图表 (key: c18_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0565)

预设状态：在 375×812 手机视口打开页面（视口 375×812）

操作：滚动浏览，并查看课表中的一讲、查看自评图表

期望结果：主内容区块不再左右并排；导航、课表、图表、按钮和长文本都没有被截断，各处查看与切换仍然可用。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_013_ai_literacy_course_page

## Skills

## Env

## Warmup
