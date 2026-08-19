# 静态校验清单

1. frontmatter 必须存在、是 YAML mapping、没有重复 key；`id`、`category`、`difficulty`、`modality`、`timeout_seconds` 和 `grading_type` 类型可被框架消费。
2. 声明的 category 要与任务父目录一致；ID 不得在选择范围内多义，文件名通常应包含声明 ID。
3. `Prompt`、`Workspace Path` 和与评分类型对应的 `Automated Checks`/`LLM Judge Rubric` 章节必须可解析。`grade()` 只用 Python AST 检查，禁止导入或执行任务作者代码。
4. Workspace 为相对路径时从仓库根解析并检查越界/存在性；`/tmp_workspace` 是评测容器的虚拟根，静态模式记录为 `REVIEW`，不要求宿主机创建。任务明确引用的 `exec/`、`gt/`、附件或脚本仍需存在。
5. Skills 中每个名称必须对应 `<repo>/skills/<name>/SKILL.md`（或任务 `Skills Path`/绝对 `skills_path` 下的同名目录），缺失或不可读是 `FAIL`。
6. Env 每行只解析变量名，检查 POSIX 名称、重复声明和当前进程存在性；报告永远只包含 `present/missing`。
7. Warmup 章节必须存在；不需要预热时保留标题并置空正文，表示合法 no-op，不产生问题。只有非空 Warmup 才检查 shell 语法、引用文件和危险模式；不可解析脚本和宿主机删除/提权/网络/daemon 命令须显式报告。`--smoke` 的运行边界见脚本与 `smoke.py`。
8. `tasks/extension/task_sources.yaml` 存在时校验 YAML 可读和 `tasks` 映射；缺失或任务 ID 无法追溯为 `FAIL`。
9. `tags` 包含 `web-site-gen` 时自动启用 Web 专项静态协议；检查 Playwright 模块、Rubric 与 key 对齐、npm 启动约定和 workspace/eval 素材，详细规则见 [website-checklist.md](website-checklist.md)。

报告解读：`summary.action_summary.tasks_to_fix` 是确定性问题清单，应修复后重跑；`tasks_for_review` 是需要人工确认的边界问题；`tasks_pass` 只表示当前规则下未发现问题，不等于质量已被统计证明。
