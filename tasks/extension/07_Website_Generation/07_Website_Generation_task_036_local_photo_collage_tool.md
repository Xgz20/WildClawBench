---
id: 07_Website_Generation_task_036_local_photo_collage_tool
name: 本地照片拼图工具
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 本地照片拼图工具
timeout_seconds: 900
modality: pure-text
difficulty: L1
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 本地照片拼图工具

## Prompt

请在 /tmp_workspace 下从空目录创建一个可运行的中文本地照片拼图工具网页项目。项目根目录需要提供 package.json，并支持 npm install、npm run build，以及 npm run start -- --host 127.0.0.1 --port 4173 启动网站。页面运行时不要依赖外部图片、字体、接口或其他网络资源；不要接入真实支付或发送真实请求。

我想做一个本地的拼图工具，照片从我电脑里选，一次最多能拼十张。拼法要能支持四种：让它自己排、全部横着排成一行、全部竖着排成一列、我自己拖拽。每张照片还要能单独放大缩小和转方向。拼完之后图片可以导出。

## Expected Behavior

Agent 应从空目录生成可运行的前端网站，按 Prompt 完成页面内容、交互和视觉要求；项目应能在本地 npm install、npm run build 并通过 npm run start 启动，且不依赖外部网络资源。

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

### Criterion 1: 通览整页，找出从本机选照片的入口、显示拼图效果的区域、四种拼法的入口，以及导出的… (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0909)

预设状态：页面在 1440×900 视口首次打开，还没有选入任何照片

操作：通览整页，找出从本机选照片的入口、显示拼图效果的区域、四种拼法的入口，以及导出的入口

期望结果：四样都能找到：一个能从本机选照片的入口；一处显示拼图效果的区域（此时还没有照片，为空或显示空状态文字都算具备）；四种拼法都能选到，分别对应自动排布、横排一行、竖排一列、自己拖拽摆放（做成四个按钮、标签、单选项，或者一个下拉里的四个选项，都算）；一个导出的入口。拼法的名称写法不限，但能看出四种是不同的排法，不是同一种的重复。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 用页面上选照片的入口 (key: c02_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0909)

预设状态：页面已打开，还没有选入任何照片

操作：用页面上选照片的入口，把下面三张选入页面（若页面只能逐张选择，就分次选入）： /tmp_workspace_eval/coast-01.jpg、/tmp_workspace_eval/daily-01.jpg、/tmp_workspace_eval/mountain-02.jpg 三张，然后查看页面（若这三张默认没有全部进入拼图，就用页面提供的入口把它们都加进拼图）

期望结果：三张照片都进了工具，每一张都能被认出是哪一张（显示缩略图或显示文件名，任一即可）；三张都出现在拼图效果里，画面正常显示出照片本身的内容（黄昏的海滩、摊开在桌上的旧书、雾中的林荫路），没有裂图、灰块或三张长得一模一样的占位图。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 把下面十一张选入页面（若页面只能逐张选择 (key: c03_rule_settlement, primary: interaction_function, secondary: rule_settlement, weight: 0.0909)

预设状态：页面已打开，还没有选入任何照片

操作：把下面十一张选入页面（若页面只能逐张选择，就分次选入）： /tmp_workspace_eval/coast-01.jpg、/tmp_workspace_eval/coast-02.jpg、/tmp_workspace_eval/coast-04.jpg、/tmp_workspace_eval/coast-05.jpg、/tmp_workspace_eval/daily-01.jpg、/tmp_workspace_eval/daily-02.jpg、/tmp_workspace_eval/daily-03.jpg、/tmp_workspace_eval/daily-05.jpg、/tmp_workspace_eval/mountain-02.jpg、/tmp_workspace_eval/mountain-03.jpg、/tmp_workspace_eval/street-05.jpg 共十一张，然后尽量把它们全部拼进去（若选入后默认没有全部进入拼图，就用页面提供的入口一张一张加，直到某一张加不进去为止）

期望结果：拼图里的照片最多十张，第十一张没有被拼进去。若页面把十一张全都收进了页面（清单、缩略图列表之类的地方能看到十一张），那么第十一张要么显示为未加入拼图的状态，要么伴随一句到达上限的提示，不能让人以为它已经拼上了；若页面在选入这一步就只收下十张，清单里只有十张即算通过。无论哪种，拼图里绝不能出现第十一张照片。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 先选横着排成一行的那种拼法 (key: c04_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0909)

预设状态：已选入 /tmp_workspace_eval/coast-01.jpg、/tmp_workspace_eval/daily-01.jpg、/tmp_workspace_eval/mountain-02.jpg 三张并让它们都进入拼图

操作：先选横着排成一行的那种拼法，查看拼图效果；再切到竖着排成一列的那种，再查看一次

期望结果：横排时三张照片同处一行、没有换行，水平方向从左到右依次排开，互不重叠；竖排时三张同处一列，垂直方向从上到下依次排开，互不重叠。两种拼法下三张照片都在拼图里，没有因为换拼法丢掉或多出照片。三张的高度是否一致、宽度是否一致都不作要求。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 选择让工具自动排布的那种拼法 (key: c05_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0909)

预设状态：已选入 /tmp_workspace_eval/coast-01.jpg、/tmp_workspace_eval/coast-02.jpg、/tmp_workspace_eval/daily-01.jpg、/tmp_workspace_eval/daily-02.jpg、/tmp_workspace_eval/mountain-02.jpg 五张并让它们都进入拼图

操作：选择让工具自动排布的那种拼法，查看拼图效果

期望结果：五张照片都出现在拼图里，各自的画面能辨认出来，互相不重叠；拼图不需要横向拉动就能看全，也没有照片溢出到拼图区域外面。为了排整齐而把照片裁掉一部分是允许的，具体排成几行几列不限。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 先记下拼图里这两张现在的大小 (key: c06_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0909)

预设状态：已选入 /tmp_workspace_eval/coast-01.jpg（黄昏的海滩）和 /tmp_workspace_eval/daily-01.jpg（摊开在桌上的旧书）两张并让它们都进入拼图，拼法选横着排成一行的那种

操作：先记下拼图里这两张现在的大小，然后针对 coast-01.jpg 用页面提供的任一方式把它放大（缩放按钮、输入框、滑块，或者直接拖它的角柄都可以；页面若用百分比就调到 150% 上下，用倍数就调到 1.5 倍上下，只要比原来明显大即可）。如果页面需要先选中某张照片再调整，就先点选 coast-01.jpg

期望结果：拼图里的 coast-01.jpg 明显比调整前大——它在拼图里占的地方变大，或者它在自己那一格里的画面被明显放大，任一种都算；同时 daily-01.jpg 的大小没有跟着变。若页面写出了这张的倍数或百分比，该数值与画面上实际的变化一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 针对 coast-01.jpg 用页面提供的任一方式把它转 90 度（旋转按钮、… (key: c07_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0909)

预设状态：已选入 /tmp_workspace_eval/coast-01.jpg（黄昏的海滩）和 /tmp_workspace_eval/daily-01.jpg（摊开在桌上的旧书）两张并让它们都进入拼图，拼法选横着排成一行的那种

操作：针对 coast-01.jpg 用页面提供的任一方式把它转 90 度（旋转按钮、输入框、滑块，或者直接拖它的旋转手柄都可以）。如果页面需要先选中某张照片再调整，就先点选 coast-01.jpg

期望结果：拼图里 coast-01.jpg 的方向明显变了，原本横着的画面变成竖着（或反过来），daily-01.jpg 的方向没有跟着变。若页面写出了这张的角度，该数值与画面上实际转过的方向一致，不出现写着 90 度但画面没转的情况。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 先记下拼图里这两张各自的位置 (key: c08_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0909)

预设状态：已选入 /tmp_workspace_eval/coast-01.jpg（黄昏的海滩）和 /tmp_workspace_eval/daily-01.jpg（摊开在桌上的旧书）两张并让它们都进入拼图，拼法选自己拖拽摆放的那一种

操作：先记下拼图里这两张各自的位置，然后用鼠标按住其中一张（记清楚拖的是哪一张：画面是黄昏海滩的那张，还是摊开旧书的那张），把它明显往右或往下拖一段再松开。若照片本身拖不动、而页面把拖动做在某个手柄或边框上，就拖那个手柄

期望结果：松手之后，被拖的那张停在新位置，能看出它相对于拼图区域移动了一段距离，并且位置保持住、没有弹回原处；另一张的位置没有跟着动。两张因此叠在一起也算正常，不作为不通过的理由。这一条要求照片确实能用鼠标拖着挪；如果只能靠方向按钮或坐标输入框改位置、鼠标怎么拖都不动，不算通过。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 点击导出的入口 (key: c09_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0909)

预设状态：已选入 /tmp_workspace_eval/coast-01.jpg 和 /tmp_workspace_eval/daily-01.jpg 两张并让它们都进入拼图，拼图效果已经显示出来

操作：点击导出的入口

期望结果：这次点击确实导出了一张图片，而不是一个没有接上功能的按钮：浏览器收到一次图片文件下载，或者页面上出现可点的下载链接、生成好的成品图、“已导出”这类明确提示，任意一种都算。同时拼图里的照片没有因为这次导出被清空。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 查看页面上各个功能区域（选照片的入口和照片清单、拼图效果、调整控件、导出入口）之… (key: c10_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0909)

预设状态：页面在 1440×900 视口打开，已选入 /tmp_workspace_eval/coast-01.jpg、/tmp_workspace_eval/daily-01.jpg、/tmp_workspace_eval/mountain-02.jpg 三张并让它们都进入拼图

操作：查看页面上各个功能区域（选照片的入口和照片清单、拼图效果、调整控件、导出入口）之间的位置关系

期望结果：页面上存在的各区域互不重叠遮挡，没有内容被裁切或被固定的页头页脚压住；拼图效果不需要横向拉动就能看全。区域怎么摆（左右分栏、上下分区或其他排布）不限；若某类区域不以独立分区的形式存在（例如控件直接浮在选中的照片旁边），只判存在的那些。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 选入 /tmp_workspace_eval/coast-01.jpg 和 /tmp_workspace_eval/daily-01.jpg 两张并让它们都进入拼图 (key: c11_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.091)

预设状态：浏览器视口已调整为 375×812 并打开页面（视口 375×812）

操作：选入 /tmp_workspace_eval/coast-01.jpg 和 /tmp_workspace_eval/daily-01.jpg 两张并让它们都进入拼图，检查整页是否出现横向滚动，再看一遍拼图效果和调整控件

期望结果：页面没有横向滚动，没有元素把视口撑破；照片、拼图效果和调整控件都能看到、能点到，文字没有被裁掉也没有互相重叠；两张照片在窄屏下仍然完整显示在拼图区域里，没有被挤出边界。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_036_local_photo_collage_tool

## Skills

## Env

## Warmup
