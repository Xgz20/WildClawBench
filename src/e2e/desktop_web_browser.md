# AStudio 原生浏览器取证适配

本指引随受管评分工作区分发。先读取固定版本 score-web-e2e 的评分契约及浏览器交互规则。

1. 读取实际公开的 AStudio 原生浏览器工具能力。使用原生浏览器访问当前评分工作区的回环 URL。控件操作以浏览器可见状态为依据。按检查点执行实际动作，并记录操作前后状态、理由和证据引用。
2. 用 `astron_browser_set_viewport` 设置桌面或窄屏尺寸，再获取新的页面快照并执行交互。按实际工具能力处理日期、对话框、拖拽和下载。
3. 每张视觉证据先调用 `astron_browser_save_screenshot`，传入本次状态的短标签。使用回执中的 `filename` 和 `sha256` 运行以下命令。用脚本返回的绝对 `path` 调用 `image_understanding`（参数 `image` 和针对检查点的 `question`）。工具可通过工具搜索发现。记录文字观察，评分引用使用脚本返回的 `evidence` 字段，美观度视口使用原生回执的尺寸。

   ```bash
   node desktop-scoring-tooling/desktop_web_screenshot.mjs <filename> <sha256>
   ```

   保留原生截图和接收回执。原生保存或独立读图不成功时，将对应评测记为异常。完成后确认接收器和站点均停止，移除运行时副本。
4. 按冻结任务的指标 Profile 完成评分。保留 score_input.json 和 task_score.json，由执行器再次核验并构建回传包。
