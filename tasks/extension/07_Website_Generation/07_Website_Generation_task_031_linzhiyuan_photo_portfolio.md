---
id: 07_Website_Generation_task_031_linzhiyuan_photo_portfolio
name: 林知远摄影作品集
category: 07_Website_Generation
sub_category: 个人表达与生涯
task_type: 个人作品集／摄影图集
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 林知远摄影作品集

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

题目提供的输入素材已经放在 /tmp_workspace/assets 目录中，请直接使用这些文件，不要用自行编造的数据替代。

我想给自己做一个摄影作品集的网页。整体想要手帐的感觉，翻起来像在读一本书，不同的主题就是书里的不同章节。

照片和配套的文字都放在 `/tmp_workspace/assets` 目录中，请直接使用。照片按主题分在各自的文件夹里，哪个文件夹对应哪一章、每章开头那段话，还有每张照片的标题、拍摄时间、拍摄地点和说明，都记在同一个目录的表格里。

开头要写上我的名字林知远，并像书的目录一样把几章列出来，点一下能直接翻到那一章。照片点开以后可以放大看，同时看到它的标题、拍摄时间、地点和那段说明；放大之后接着看同一章的下一张，不用退回去重新点，看完关掉就接着刚才的地方往下读，不要跳到别的页面去。最后附上我的联系方式，邮箱 linzhiyuan.photo@foxmail.com，微信号 linzy_photo。

纸一样的底色、手写感的标题、像贴上去的照片，这些都用上，读起来更像一本册子，而不是一个普通网站。手机上也要能正常翻。

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

### Criterion 1: 查看页面开头部分 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0833)

预设状态：打开作品集首页

操作：查看页面开头部分

期望结果：开头能读到作者名字“林知远”，并有明确文字表明这是一份摄影作品集，例如标题、副标题或简介中出现“摄影”“作品集”“照片”一类说明，具体措辞不限。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 通读整份作品集 (key: c02_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0833)

预设状态：打开作品集首页

操作：通读整份作品集，查看章节是怎么划分的；若做成一章一屏或分页翻阅的形式，依次进入每一章

期望结果：作品集按“山野”“海边”“街巷”“日常”四章组织，四个章节名都能读到；每章开头都有一段引言文字，内容与素材 /tmp_workspace/assets/chapters.csv 中该章的“章节小引”一致，没有把章节名或引言写成素材以外的内容。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 查看这一章下面展示的照片 (key: c03_lists_tables, primary: content_structure, secondary: lists_tables, weight: 0.0833)

预设状态：打开作品集，定位到“海边”这一章，可以用开头的目录直接跳过去

操作：查看这一章下面展示的照片

期望结果：“海边”章展示 5 张照片，不多不少。按画面内容可以辨认出有人影的沙滩海岸、岸边成堆的礁石、向远处延伸的长堤、夜色中的海面、海边带屋顶的凉亭这五种画面，顺序不限；这里判断的是画面本身，不要求页面把这些描述文字写出来。没有混入山野、街巷或日常章的照片，也没有把同一张重复展示。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 点击目录中的“街巷” (key: c04_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0833)

预设状态：打开作品集首页，页面开头列出了各章的目录

操作：点击目录中的“街巷”

期望结果：页面翻到“街巷”这一章，该章标题完整可见、没有被顶部固定的元素压住或遮挡，随后可见的照片属于“街巷”章。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 点击这张照片 (key: c05_popup_overlay, primary: interaction_function, secondary: popup_overlay, weight: 0.0833)

预设状态：打开作品集首页，页面上有一张照片可见

操作：点击这张照片，查看放大后的呈现，再用页面提供的方式关闭它

期望结果：点击后照片在当前页面上放大呈现，浏览器没有跳转到别的地址、作品集正文仍在其下层；放大后的照片比它在正文里的显示尺寸更大，放大视图上有可见的关闭入口。关闭之后放大视图消失，作品集页面重新完整可见。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 点开这张照片 (key: c06_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0833)

预设状态：定位到“街巷”章，找到那张夜色中带一道闪电的照片（素材中的 /tmp_workspace/assets/photos/street/street-05.jpg，标题“夜里的一道闪电”）；若正文里没有显示标题，可逐张点开确认

操作：点开这张照片，查看放大视图里的文字

期望结果：放大视图同时显示这张照片的拍摄时间 2023-08-02、拍摄地点“西班牙 瓦伦西亚”，以及说明“在阳台上等了一个多小时，最后只拍到这一张带闪电的。”，三项内容与素材一致，没有张冠李戴或自行编写。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 用放大视图里继续往下看的方式 (key: c07_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0833)

预设状态：定位到“日常”章，可以用开头的目录直接跳过去；打开该章靠前的一张照片（不要选排在最后的那张）的放大视图，记下当前显示的标题、拍摄时间、拍摄地点和说明

操作：用放大视图里继续往下看的方式，切换到该章的另一张照片

期望结果：放大视图换成“日常”章的另一张照片，标题、拍摄时间、拍摄地点和说明四项同时更新为新照片对应的那一组，不残留上一张的任何一项。该章五张照片的标题、拍摄时间、拍摄地点分别是：读到一半的书／2024-04-02／家中书桌，三颗树莓／2023-06-18／家中阳台，散掉的灯／2023-12-24／杭州 武林路，橘子的胡须／2024-05-07／家中沙发，捡回来的松果／2023-11-12／家中窗台；说明文字以 /tmp_workspace/assets/photos.csv 中该张照片的“说明”列为准。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 关闭这个放大视图 (key: c08_popup_overlay, primary: interaction_function, secondary: popup_overlay, weight: 0.0833)

预设状态：定位到“日常”章，用开头的目录跳过去或滚动过去均可，此时页面已经不在开头；再打开该章一张照片的放大视图

操作：关闭这个放大视图，观察关闭后页面停在哪里

期望结果：关闭后页面仍停留在打开放大视图之前的阅读位置，“日常”章的照片仍在视野内，没有被重置回页面开头。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 查看结尾处的联系方式 (key: c09_detail_display, primary: content_structure, secondary: detail_display, weight: 0.0833)

预设状态：打开作品集并翻到结尾

操作：查看结尾处的联系方式

期望结果：结尾展示邮箱 linzhiyuan.photo@foxmail.com 和微信号 linzy_photo，两项都完整可见、没有被截断或写错。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 观察整体配色、标题的处理方式和照片的呈现方式 (key: c10_visual_style, primary: visual_layout, secondary: visual_style, weight: 0.0833)

预设状态：在 1440×900 桌面视口打开页面

操作：观察整体配色、标题的处理方式和照片的呈现方式

期望结果：底色、标题、照片三处都做了手帐化的处理：底色接近纸张，米色、牛皮、浅灰一类都算，不是纯白或纯黑；标题用了手写体或书籍标题一类的处理，与正文明显区分；照片有贴在纸上的处理，白边、胶带、轻微倾斜、投影、压边等任意一种都算。具体用哪种手法不限。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 从头到尾浏览一遍 (key: c11_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0833)

预设状态：在 1440×900 桌面视口打开页面

操作：从头到尾浏览一遍；若做成分页翻阅的形式，依次进入每一章

期望结果：阅读顺序是开头、四章正文、结尾联系方式；每章自成一段，与相邻章之间有明显的分隔或过渡；同一章的照片成组排布，照片与文字互不重叠，也不被相邻内容压住。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 浏览全部内容 (key: c12_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0837)

预设状态：浏览器视口已调整为 375×812 并打开页面（视口 375×812）

操作：浏览全部内容，并点开一张照片查看放大视图

期望结果：页面没有横向滚动，没有任何元素宽度超出视口。章节标题、引言、照片和结尾的联系方式都完整可读，没有被截断或互相重叠；放大视图在窄屏下也能正常打开，照片和文字都在屏幕范围内。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_031_linzhiyuan_photo_portfolio

## Skills

## Env

## Warmup
