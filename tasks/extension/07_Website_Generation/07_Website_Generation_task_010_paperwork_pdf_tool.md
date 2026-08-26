---
id: 07_Website_Generation_task_010_paperwork_pdf_tool
name: 文页工坊PDF工具
category: 07_Website_Generation
sub_category: 自然语言页面构建
task_type: 本地文档处理工具
timeout_seconds: 1200
modality: pure-text
difficulty: L2
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---

# 文页工坊PDF工具

## Prompt

请在 `/tmp_workspace` 下创建项目。如果启动网站时遇到端口冲突，请自行选择其他可用端口。

我想做一个叫“文页工坊”的中文本地文档处理网页，帮助办公用户把图片整理成 PDF，也能处理已有 PDF。打开页面即可使用，不需要登录，文件只在浏览器本地处理，不上传服务器。

页面顶部显示品牌名“文页工坊”、说明“把文件整理成一份好用的 PDF”。首页用清楚的功能卡片展示：图片转 PDF、图片合并 PDF、PDF 合并、PDF 拆分、PDF 转图片、PDF 签名。用户先选择一个功能，再进入该功能自己的文件选择和参数页面；整个页面始终只处理当前这一项操作，不做任务队列，也不要求多任务并发。

每个功能都遵循“选择功能 → 选择文件 → 设置参数 → 开始处理 → 查看结果 → 下载文件”的单流程。选择功能后显示对应的文件格式提示和“选择文件”入口；选中文件后显示文件名、格式、大小，并允许在开始前移除或重新选择。图片合并和 PDF 合并支持一次选择多个文件并调整顺序，但它们仍作为一次操作完成。空选择、重复文件、不支持的格式和非法页码范围都要给出明确的中文提示，不能开始错误处理。

支持以下功能：图片转成 PDF；多张图片合并成一个 PDF；多个 PDF 合并成一个 PDF；PDF 按每页或指定页码范围拆分；PDF 转成 PNG 或 JPG 图片；给 PDF 添加文字签名。签名工具提供文字、颜色和大小设置，并在处理前的预览区域展示签名效果，可调整位置或删除后重新添加。

开始处理后，在当前流程中显示处理中和进度，完成后展示真实结果摘要、页数或图片数量、文件名编辑框和下载按钮，不能只展示静态占位内容。提供“重新开始”或“返回功能选择”入口，让用户完成一次下载后可以开始下一次单独操作。

视觉上做成清爽、可信的本地工具：浅灰白背景，深色文字，蓝色作为主要操作和处理中状态，绿色表示完成，橙色表示提醒，红色表示失败。桌面端让功能选择、文件操作、参数和结果区域层级清楚；窄屏时自动变成单栏，文件名、状态和主要按钮仍然容易阅读和点击。

## Expected Behavior

Agent 应按 Prompt 完成页面内容、交互和视觉要求。

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

### Criterion 1: 查看页面顶部和功能区域 (key: c01_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0588)

预设状态：首次打开页面

操作：查看页面顶部和功能区域

期望结果：显示“文页工坊”“把文件整理成一份好用的 PDF”，并能找到六个功能入口和开始使用的引导。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 2: 浏览全部功能卡片 (key: c02_information_organization, primary: content_structure, secondary: information_organization, weight: 0.0588)

预设状态：页面已打开

操作：浏览全部功能卡片

期望结果：图片转 PDF、图片合并 PDF、PDF 合并、PDF 拆分、PDF 转图片、PDF 签名均有独立入口和用途说明。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 3: 依次选择图片转 PDF、PDF 拆分和 PDF 签名 (key: c03_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0588)

预设状态：页面已打开

操作：依次选择图片转 PDF、PDF 拆分和 PDF 签名

期望结果：每次只展示当前功能的文件格式提示、参数和主按钮，切换后不保留上一个功能的不相关控件。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 4: 选择 /tmp_workspace_eval/sample-image-a.png (key: c04_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0588)

预设状态：已选择图片转 PDF

操作：选择 /tmp_workspace_eval/sample-image-a.png

期望结果：进入当前单流程的文件步骤，显示 sample-image-a.png、PNG 格式和文件大小，并可移除或重新选择文件；页面没有任务队列。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 5: 先不选择任何文件就尝试点击开始处理 (key: c05_form_validation, primary: interaction_function, secondary: form_validation, weight: 0.0588)

预设状态：已选择图片转 PDF 功能

操作：先不选择任何文件就尝试点击开始处理，然后选择 /tmp_workspace_eval/sample-note.txt

期望结果：不选文件时无法开始处理（开始入口不可用或给出明确提示都算）；选择 TXT 后显示格式不支持的中文提示，该文件不能进入处理步骤。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 6: 选择 /tmp_workspace_eval/sample-image-a.png (key: c06_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0588)

预设状态：已选择图片转 PDF功能

操作：选择 /tmp_workspace_eval/sample-image-a.png，点击开始处理并等待完成

期望结果：当前流程显示处理中和进度，完成后展示实际生成的 PDF 结果摘要和可下载文件，不能只展示静态占位内容。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 7: 一次选择 /tmp_workspace_eval/sample-image-a.png 和 /tmp_workspace_eval/sample-image-b.png (key: c07_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0588)

预设状态：已选择图片合并 PDF功能

操作：一次选择 /tmp_workspace_eval/sample-image-a.png 和 /tmp_workspace_eval/sample-image-b.png，调整顺序后开始处理

期望结果：两个文件可以调整顺序；处理完成后结果显示总页数为 2，且预览第一页对应排序后的第一张图片。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 8: 一次选择 /tmp_workspace_eval/sample-2-pages.pdf 和 /tmp_workspace_eval/sample-4-pages.pdf (key: c08_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0588)

预设状态：已选择 PDF 合并功能

操作：一次选择 /tmp_workspace_eval/sample-2-pages.pdf 和 /tmp_workspace_eval/sample-4-pages.pdf，调整文件顺序并开始处理

期望结果：文件顺序可调整，合并作为一次单独操作完成，结果显示合并后的总页数为 6 页和可编辑的输出名称。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 9: 分别输入空范围、反向范围和超出页数的范围 (key: c09_form_validation, primary: interaction_function, secondary: form_validation, weight: 0.0588)

预设状态：已选择 PDF 拆分功能并载入 /tmp_workspace_eval/sample-4-pages.pdf

操作：分别输入空范围、反向范围和超出页数的范围

期望结果：每种非法页码范围都显示清楚的中文提示，不能开始拆分。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 10: 在“每页一个文件”和页码范围 2-3 之间切换并处理 (key: c10_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0588)

预设状态：已选择 PDF 拆分功能并载入 /tmp_workspace_eval/sample-4-pages.pdf

操作：在“每页一个文件”和页码范围 2-3 之间切换并处理

期望结果：选“每页一个文件”得到 4 个结果；选页码范围 2-3 得到只包含原文件第 2、3 页内容的结果（打成一个文件或两个文件均可），结果与所选拆分方式一致。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 11: 在 PNG 和 JPG 之间切换后开始处理 (key: c11_content_switching, primary: interaction_function, secondary: content_switching, weight: 0.0588)

预设状态：已选择 PDF 转图片功能并载入 /tmp_workspace_eval/sample-2-pages.pdf

操作：在 PNG 和 JPG 之间切换后开始处理

期望结果：目标格式随选择变化，结果扩展名与目标格式一致，结果数量为 2 张。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 12: 输入文字签名 (key: c12_content_editing, primary: interaction_function, secondary: content_editing, weight: 0.0588)

预设状态：已选择 PDF 签名功能并载入 /tmp_workspace_eval/sample-2-pages.pdf

操作：输入文字签名，调整颜色和大小，移动签名并删除后重新添加

期望结果：预览中能看到文字签名，颜色、大小和位置随操作更新，删除后签名消失且可以再次添加。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 13: 不填写签名内容就点击开始或应用签名 (key: c13_form_validation, primary: interaction_function, secondary: form_validation, weight: 0.0588)

预设状态：已选择 PDF 签名功能并载入 /tmp_workspace_eval/sample-2-pages.pdf

操作：不填写签名内容就点击开始或应用签名

期望结果：显示签名不能为空的中文提示，不生成空签名结果。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 14: 修改输出名称并点击下载 (key: c14_file_upload_and_download, primary: interaction_function, secondary: file_upload_and_download, weight: 0.0588)

预设状态：已选择图片转 PDF 功能，载入 /tmp_workspace_eval/sample-image-a.png 并完成一次处理，当前流程已完成并显示结果

操作：修改输出名称并点击下载

期望结果：结果卡片中的名称同步更新，点击下载有明确反馈，下载文件名使用修改后的名称。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 15: 点击重新开始或返回功能选择 (key: c15_page_navigation, primary: interaction_function, secondary: page_navigation, weight: 0.0588)

预设状态：已选择图片转 PDF 功能，载入 /tmp_workspace_eval/sample-image-a.png 并完成一次处理，当前流程已完成

操作：点击重新开始或返回功能选择

期望结果：当前结果被安全收尾，页面回到功能选择或空的文件步骤，不残留上一次操作的处理中状态，也不出现并发任务列表。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 16: 查看功能选择、文件步骤、参数和结果区域 (key: c16_page_layout, primary: visual_layout, secondary: page_layout, weight: 0.0588)

预设状态：页面在 1440×900 视口打开，已选择图片转 PDF 功能并载入 /tmp_workspace_eval/sample-image-a.png，进入处理步骤

操作：查看功能选择、文件步骤、参数和结果区域

期望结果：桌面端流程层级清楚，当前步骤和主操作明显，文件名、状态和按钮无需横向滚动即可阅读。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

### Criterion 17: 查看功能选择、文件信息和参数控件 (key: c17_responsive_layout, primary: visual_layout, secondary: responsive_layout, weight: 0.0592)

预设状态：页面在 375×812 视口打开，已选择图片转 PDF 功能并载入 /tmp_workspace_eval/sample-image-a.png，进入文件步骤（视口 375×812）

操作：查看功能选择、文件信息和参数控件

期望结果：页面变为单栏且无横向滚动，文件名、状态和主要按钮仍可读可点击，参数控件不会被截断。

Score 1.0: 符合预设状态、操作要求，且结果与期望结果一致。

Score 0.0: 不符合预设状态、操作要求或期望结果。

## Workspace Path

workspace/extension/07_Website_Generation/task_010_paperwork_pdf_tool

## Skills

## Env

## Warmup
