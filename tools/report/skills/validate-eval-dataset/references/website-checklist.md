# Web 站点评测静态校验清单

任务 frontmatter 的 `tags` 包含 `web-site-gen` 时自动应用以下规则。

1. frontmatter 的 `sub_category` 必须使用网站生成场景登记的二级场景，不能继续使用旧的统一值“自然语言页面构建”。
2. 任务 ID 必须能推导出 `task_<序号>_<slug>`，并存在 `eval/checks/website/tasks/task_<序号>_<slug>.py`。
3. 检查器必须能被 Python AST 解析；校验过程禁止导入或执行检查器。
4. 检查器必须静态声明字符串序列 `RUNTIME_KEYS` 和 `VISUAL_KEYS`。前者精确覆盖 Rubric 中所有非 `visual_layout` key，后者精确覆盖所有 `visual_layout` key，均不得重复。
5. 检查器必须声明 `async run(page, screenshot_dir)`；存在视觉 key 时必须声明 `async capture_visual(page, screenshot_dir)`。
6. 每个 Rubric Criterion 必须有连续编号、合法且唯一的 key、必填 primary/secondary、正权重，以及 `Score 1.0` 和 `Score 0.0`。primary 只允许 `content_structure`、`interaction_function`、`visual_layout`，所有权重总和允许千分之一以内的十进制舍入误差。
7. Prompt 必须说明项目创建在 `/tmp_workspace` 下；启动网站遇到端口冲突时，应自行选择其他可用端口。具体 npm 安装、构建和启动协议属于评测框架的统一运行约定，不重复写入单题 Prompt。
8. Workspace 必须为 `workspace/extension/07_Website_Generation/task_<序号>_<slug>` 且包含 `exec/`。这是当前 `src/utils/website_checks.py` 实际复制评测素材的固定契约。
9. 检查器字符串常量引用 `/tmp_workspace_eval` 时，对应 Workspace 的 `eval/` 必须包含 `.gitkeep` 以外的评测素材。

确定性缺失或不匹配均为 `FAIL`，对应问题码为：

- `WEBSITE_CHECKER_MISSING`
- `WEBSITE_CHECKER_SYNTAX_INVALID`
- `WEBSITE_CHECKER_ENTRYPOINT_MISSING`
- `WEBSITE_RUNTIME_KEYS_MISMATCH`
- `WEBSITE_VISUAL_KEYS_MISMATCH`
- `WEBSITE_RUBRIC_DIMENSION_INVALID`
- `WEBSITE_RUBRIC_FORMAT_INVALID`
- `WEBSITE_RUBRIC_WEIGHT_INVALID`
- `WEBSITE_SUB_CATEGORY_INVALID`
- `WEBSITE_STARTUP_CONTRACT_MISSING`
- `WEBSITE_WORKSPACE_LAYOUT_INVALID`
- `WEBSITE_EVAL_FIXTURE_MISSING`

本 Skill 不在宿主机启动 npm、站点、Chromium 或 Playwright。定位器稳定性、真实交互、截图质量和浏览器依赖只能通过评测容器中的运行时测试确认，静态 `PASS` 不表示 Playwright 端到端已经执行成功。
