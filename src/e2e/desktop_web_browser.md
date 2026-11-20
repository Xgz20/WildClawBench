# AStudio 原生浏览器取证适配

本指引随受管评分工作区分发。先读取固定版本 score-web-e2e 的评分契约及浏览器交互规则。

1. 读取实际公开的 AStudio 原生浏览器工具能力。使用原生浏览器访问当前评分工作区的回环 URL。控件操作以浏览器可见状态为依据。按检查点执行实际动作，并记录操作前后状态、理由和证据引用。
2. 发布客户端用 `astron_browser_tab` 的 `open` 和 `resize` 打开候选页并设置尺寸。使用回执里实际观测到的视口，再获取新的页面观察并执行交互。
3. 截图前用 `astron_browser_tab` 的 `list` 确认候选页的会话标签页 ID 与回环 URL。用 `astron_browser_inspect` 的 `screenshot` 保存视口 PNG，传入该 `tabId` 和形如 `private-scoring/browser-captures/native-home.png` 的唯一 `path`。客户端回执含绝对路径、MIME 与字节数。按下方命令读取并回传该文件。

   ```bash
   node desktop-scoring-tooling/desktop_web_screenshot.mjs native-home.png
   ```

   提供 `astron_browser_save_screenshot` 的测试客户端可使用该工具，并把回执中的 `filename` 和 `sha256` 一并传给脚本。用脚本返回的绝对 `path` 调用 `image_understanding`，参数为 `image` 和对应检查点的 `question`。记录文字观察，使用 `evidence` 字段引用截图，使用 `viewport` 记录实际像素尺寸。保留原生截图和接收回执。原生保存或独立读图失败时记为评测异常。完成后停止接收器和站点，清理运行时副本。
4. 按冻结任务的指标 Profile 完成评分。保留 score_input.json 和 task_score.json，由执行器再次核验并构建回传包。
