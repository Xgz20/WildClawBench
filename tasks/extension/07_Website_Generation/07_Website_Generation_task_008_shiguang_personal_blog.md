---
id: 07_Website_Generation_task_008_shiguang_personal_blog
name: 拾光札记博客
category: 07_Website_Generation
sub_scene: 个人表达与生涯
task_type: 个人博客
timeout_seconds: 900
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
---

# 拾光札记博客

## Prompt

请帮我做一个名为“拾光札记”的中文个人博客。我想用它记录生活、阅读、城市和工作中的见闻，访客可以浏览文章，我也能直接写文章、修改和删除已有内容，不需要登录。

顶部显示品牌名“拾光札记”，放“文章”“关于作者”两个导航和一个“写一篇”按钮。“文章”跳到文章区域，“关于作者”跳到页面靠下的作者介绍。首页开头用“把日子写成自己的风景”作为主标题，配一句“记录阅读、散步与工作里那些值得留下的片段。”

文章区域先放搜索、分类和热门标签，再展示文章列表。初始准备几篇生活、阅读和城市主题的示例文章，让页面打开后就有内容。每张文章卡片显示标题、摘要、分类、发布日期、阅读时长和标签，点击卡片或“阅读全文”进入文章详情。搜索要能匹配标题、摘要和标签，分类包括“生活、阅读、城市、工作”，热门标签里放“生活方式”“读书”“城市”“散步”。搜索、分类和标签可以组合筛选；没有匹配内容时给出清楚的提示，并提供清除筛选的入口。

文章详情显示标题、分类、发布日期、阅读时长、标签和排版后的完整正文，并提供返回文章列表、编辑文章和删除文章的入口。删除前先让人确认，避免误操作。

点击“写一篇”打开文章编辑窗口，表单包含标题、分类、摘要、标签、发布日期和正文。正文编辑器参考常见的在线文档，工具栏支持正文和标题样式，以及加粗、下划线、引用和无序列表；在段落开头输入 `# `、`> ` 或 `- ` 时，也能快捷切换成对应格式。标题和正文没有填写时，给出明确提示。

文章列表后面单独做一段“关于作者”，放一段简短介绍：“一个记录日常、阅读和城市漫游的个人角落。”，再在页面底部放版权信息。

整体想要安静、清爽、有纸张阅读感。标题和正文要有舒服的阅读层级，文章卡片、筛选区域、作者介绍和编辑窗口之间也要区分清楚。编辑工具栏放在正文上方，正文区域留出充足的写作空间；窄屏上也要方便阅读和写作。

## Expected Behavior

Agent 应从空目录生成可运行的前端网站，按 Prompt 完成页面内容、交互和视觉要求；项目应能在本地安装、构建并启动，且不依赖外部网络资源。

## Grading Criteria

本题使用 LLM Judge 评分。评分点统一放在 `## LLM Judge Rubric` 中；每个 Criterion 仅有 `Score 1.0`（符合预设状态、操作和期望结果）与 `Score 0.0`（不符合其中任一项）两档。

## Automated Checks

无。本题不使用规则评分函数。

## LLM Judge Rubric

说明：每个评分点都按“预设状态 → 操作 → 期望结果”统一描述；Judge 只根据实际页面和操作结果判断是否符合预期。

### Criterion 1: 页面显示品牌名“拾光札记”、导航“文章”“关于作者”和“ (key: criterion_01_basic_content, primary: content_structure, secondary: basic_content, weight: 0.1)

预设状态：首次打开页面。

操作：检查首页顶部和开头区域。

期望结果：页面显示品牌名“拾光札记”、导航“文章”“关于作者”和“写一篇”入口，并显示主标题“把日子写成自己的风景”和说明文字“记录阅读、散步与工作里那些值得留下的片段。”。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 2: 首页已有至少三篇示例文章，内容覆盖生活、阅读和城市主题； (key: criterion_02_lists_and_tables, primary: content_structure, secondary: lists_and_tables, weight: 0.1)

预设状态：首次打开首页，尚未新增或删除文章。

操作：检查初始文章列表。

期望结果：首页已有至少三篇示例文章，内容覆盖生活、阅读和城市主题；每张文章卡片都能看到标题、摘要、分类、发布日期、阅读时长、标签以及进入全文的入口。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 3: 文章列表下方有独立的“关于作者”区域，并显示文字“一个记 (key: criterion_03_detail_display, primary: content_structure, secondary: detail_display, weight: 0.1)

预设状态：首页已显示文章列表。

操作：检查文章列表后的作者区域和页脚。

期望结果：文章列表下方有独立的“关于作者”区域，并显示文字“一个记录日常、阅读和城市漫游的个人角落。”；页面底部有版权信息。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 4: 列表只保留标题、摘要或标签中包含该关键词的文章，不匹配的 (key: criterion_04_search, primary: interaction_and_function, secondary: search, weight: 0.1)

预设状态：首页有多篇标题、摘要或标签不同的文章。

操作：选择一篇文章独有的关键词，在搜索框中输入该关键词。

期望结果：列表只保留标题、摘要或标签中包含该关键词的文章，不匹配的文章不再显示。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 5: 选择分类后只显示该分类的文章，切回全部分类后恢复完整文章 (key: criterion_05_filtering_and_sorting, primary: interaction_and_function, secondary: filtering_and_sorting, weight: 0.1)

预设状态：首页至少有两个不同分类的文章。

操作：选择其中一个有文章的分类，再切回全部分类。

期望结果：选择分类后只显示该分类的文章，切回全部分类后恢复完整文章列表。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 6: 列表只显示同时符合搜索词和所选分类的文章，不会忽略其中任 (key: criterion_06_filtering_and_sorting, primary: interaction_and_function, secondary: filtering_and_sorting, weight: 0.1)

预设状态：页面已有两篇含有相同关键词但分类不同的文章。

操作：搜索这个共同关键词，同时选择其中一个分类。

期望结果：列表只显示同时符合搜索词和所选分类的文章，不会忽略其中任意一个条件。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 7: 无匹配内容时出现清楚的空状态和清除入口；清除后搜索与分类 (key: criterion_07_operation_feedback, primary: interaction_and_function, secondary: operation_feedback, weight: 0.1)

预设状态：停留在首页文章列表。

操作：搜索一个所有文章都不包含的词，再点击清除筛选的入口。

期望结果：无匹配内容时出现清楚的空状态和清除入口；清除后搜索与分类条件被重置，文章列表恢复。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 8: 页面进入对应文章详情，显示返回文章列表的入口、标题、分类 (key: criterion_08_page_navigation, primary: interaction_and_function, secondary: page_navigation, weight: 0.1)

预设状态：首页显示至少一张文章卡片。

操作：点击文章卡片或它的阅读全文入口。

期望结果：页面进入对应文章详情，显示返回文章列表的入口、标题、分类、发布日期、阅读时长、标签和排版后的完整正文，并提供编辑文章和删除文章的入口。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 9: 打开文章编辑窗口，包含标题、分类、摘要、标签、发布日期和 (key: criterion_09_content_creation_and_editing, primary: interaction_and_function, secondary: content_creation_and_editing, weight: 0.1)

预设状态：停留在首页。

操作：点击“写一篇”。

期望结果：打开文章编辑窗口，包含标题、分类、摘要、标签、发布日期和正文；正文可以直接编辑并显示排版效果，上方有正文或标题、加粗、下划线、引用和无序列表工具。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 10: 选中的文字立即在同一个编辑区呈现粗体或下划线效果，正文中 (key: criterion_10_content_creation_and_editing, primary: interaction_and_function, secondary: content_creation_and_editing, weight: 0.1)

预设状态：正文编辑区已有一段普通文字，并选中了其中一部分。

操作：分别对选中文字使用加粗和下划线工具。

期望结果：选中的文字立即在同一个编辑区呈现粗体或下划线效果，正文中不出现星号、下划线等格式标记。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 11: 当前段落能在同一个编辑区切换为标题、引用块或无序列表，之 (key: criterion_11_content_creation_and_editing, primary: interaction_and_function, secondary: content_creation_and_editing, weight: 0.1)

预设状态：光标位于正文编辑区中的普通段落。

操作：依次尝试标题、引用和无序列表工具。

期望结果：当前段落能在同一个编辑区切换为标题、引用块或无序列表，之后输入的文字沿用当前段落格式，正文中不显示 Markdown 标记。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 12: 输入空格后，当前段落分别转换为标题、引用块或无序列表，快 (key: criterion_12_content_creation_and_editing, primary: interaction_and_function, secondary: content_creation_and_editing, weight: 0.1)

预设状态：光标位于正文编辑区的空段落开头。

操作：分别输入 `# `、`> ` 和 `- `。

期望结果：输入空格后，当前段落分别转换为标题、引用块或无序列表，快捷标记随即消失，之后输入的文字直接使用对应格式。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 13: 编辑窗口保持打开，标题和正文附近分别出现明确的必填提示， (key: criterion_13_form_filling_and_validation, primary: interaction_and_function, secondary: form_filling_and_validation, weight: 0.1)

预设状态：文章编辑窗口已打开，标题和正文都为空。

操作：直接保存文章。

期望结果：编辑窗口保持打开，标题和正文附近分别出现明确的必填提示，文章列表中没有新增空文章。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 14: 新文章出现在首页列表中；打开详情后，标题、分类、日期、标 (key: criterion_14_content_creation_and_editing, primary: interaction_and_function, secondary: content_creation_and_editing, weight: 0.1)

预设状态：文章编辑窗口已打开。

操作：填写一篇文章，并在正文中加入标题、粗体、下划线、引用或列表等富文本格式后保存，再打开这篇文章。

期望结果：新文章出现在首页列表中；打开详情后，标题、分类、日期、标签和正文内容正确，正文保留编辑时使用的富文本排版。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 15: 编辑窗口预填原文章的内容和富文本排版；保存后仍是同一篇文 (key: criterion_15_content_creation_and_editing, primary: interaction_and_function, secondary: content_creation_and_editing, weight: 0.1)

预设状态：已经打开一篇带有富文本排版的文章详情。

操作：点击编辑文章，修改文章信息和正文格式后保存。

期望结果：编辑窗口预填原文章的内容和富文本排版；保存后仍是同一篇文章，详情和首页卡片都显示修改后的内容，没有产生重复文章。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 16: 删除确认层关闭，当前文章没有被删除，仍可在详情和首页列表 (key: criterion_16_modal_and_overlay, primary: interaction_and_function, secondary: modal_and_overlay, weight: 0.1)

预设状态：已经打开一篇文章详情。

操作：点击删除文章，在确认层中选择取消。

期望结果：删除确认层关闭，当前文章没有被删除，仍可在详情和首页列表中找到。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 17: 文章被移出列表，页面返回文章列表；再次搜索或浏览时不再出 (key: criterion_17_content_creation_and_editing, primary: interaction_and_function, secondary: content_creation_and_editing, weight: 0.1)

预设状态：已经打开一篇文章详情。

操作：点击删除文章并确认删除。

期望结果：文章被移出列表，页面返回文章列表；再次搜索或浏览时不再出现这篇文章。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 18: 文章仍然存在，详情和编辑窗口都保留保存过的文字、字段信息 (key: criterion_18_state_persistence, primary: interaction_and_function, secondary: state_persistence, weight: 0.1)

预设状态：已经新建或修改一篇带有富文本排版的文章。

操作：刷新页面，再重新打开这篇文章及其编辑窗口。

期望结果：文章仍然存在，详情和编辑窗口都保留保存过的文字、字段信息以及标题、粗体、下划线、引用或列表等排版。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 19: 点击标签后只显示带有该标签的相关文章，并提供清除当前标签 (key: criterion_19_filtering_and_sorting, primary: interaction_and_function, secondary: filtering_and_sorting, weight: 0.1)

预设状态：文章筛选区域显示热门标签，并且列表中有使用这些标签的文章。

操作：点击一个热门标签，再清除标签筛选。

期望结果：点击标签后只显示带有该标签的相关文章，并提供清除当前标签筛选的入口；清除后恢复完整列表。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 20: 首页按开场、文章筛选、文章列表、关于作者的顺序组织，各区 (key: criterion_20_page_layout, primary: visual_and_layout, secondary: page_layout, weight: 0.1)

预设状态：在 1440×900 桌面视口打开首页和文章编辑窗口。

操作：观察首页和编辑区域的布局。

期望结果：首页按开场、文章筛选、文章列表、关于作者的顺序组织，各区域边界和层级清楚；编辑工具栏位于正文上方，正文区域有足够的写作空间，主要操作容易找到。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 21: 页面呈现安静、清爽的纸张阅读感，标题与正文有明显的文字层 (key: criterion_21_visual_style, primary: visual_and_layout, secondary: visual_style, weight: 0.1)

预设状态：首页、文章详情或编辑窗口已打开。

操作：观察整体视觉和富文本样式。

期望结果：页面呈现安静、清爽的纸张阅读感，标题与正文有明显的文字层级，文章卡片和编辑窗口的边界、间距清楚；标题、粗体、下划线、引用和列表等正文格式容易区分。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 22: 导航、文章卡片、关于作者、详情正文、编辑工具栏和主要操作 (key: criterion_22_responsive_layout, primary: visual_and_layout, secondary: responsive_layout, weight: 0.1)

预设状态：在较窄的移动视口打开首页、文章详情和编辑窗口。

操作：观察并尝试使用主要内容和操作。

期望结果：导航、文章卡片、关于作者、详情正文、编辑工具栏和主要操作在窄屏上仍然清楚可用。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

### Criterion 23: 点击“文章”会定位到文章筛选与列表区域；点击“关于作者” (key: criterion_23_page_navigation, primary: interaction_and_function, secondary: page_navigation, weight: 0.1)

预设状态：停留在首页顶部。

操作：分别点击顶部的“文章”和“关于作者”导航。

期望结果：点击“文章”会定位到文章筛选与列表区域；点击“关于作者”会定位到文章列表之后的独立作者介绍区域，两个导航有明确且不同的落点。

Score 1.0: 预设状态、操作和期望结果均满足，页面行为与题目要求一致。

Score 0.0: 预设状态、操作或期望结果任一不满足。

## Workspace Path

```
workspace/extension/07_Website_Generation/task_008_shiguang_personal_blog
```

附件映射：`workspace/extension/07_Website_Generation/task_008_shiguang_personal_blog/exec/` 的内容在执行时对应 `/tmp_workspace/`；`workspace/extension/07_Website_Generation/task_008_shiguang_personal_blog/eval/` 对应预留的 `/tmp_workspace_eval/`。

## Skills

```
```

## Env

```
```

## Warmup

```bash
```
