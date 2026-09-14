# 通用场景 v2 契约

## 任务与目录

- task ID：`<Category>_task_<NNN>_<slug>`；`NNN` 为分类内三位编号，已存在、已登记或 invalid 保留编号都不可复用。
- 任务文件：`tasks/extension/<Category>/<task_id>.md`。
- Workspace：`workspace/extension/<Category>/task_<NNN>_<slug>/{exec,gt}`。
- `exec/` 是 Agent 可见输入，运行时复制到 `/tmp_workspace/`；`gt/` 仅在评分阶段复制到 `/tmp_workspace/gt/`。
- 即使没有输入或真值，也保留目录并提交 `.gitkeep`。Prompt 中的交付物统一写到 `/tmp_workspace/results/`。

## Frontmatter 与章节

必需 frontmatter：`id`、`name`、`category`、`timeout_seconds`、`modality`、`attachment_size_limit_mb`、`difficulty`、`grading_type`、`tags`。`hybrid` 还必须有和为 1 的 `grading_weights`。

必需章节按以下顺序生成：

1. `Prompt`
2. `Expected Behavior`
3. `Grading Criteria`
4. `Automated Checks`
5. `LLM Judge Rubric`
6. `Workspace Path`
7. `Skills`
8. `Env`
9. `Warmup`
10. `Additional Notes`

无内容的可选执行章节保留标题并让正文完全为空；不要写 `N/A`、`无`、说明文字、注释或空代码块。

## 评分选择

- `automated`：交付物和正确性可由确定性代码充分判断。提供 `grade()`，Rubric 为空。
- `llm_judge`：核心质量只能由语义判断。Automated Checks 为空，提供结构化 Rubric。
- `hybrid`：确定性正确性与主观质量都重要。两部分都提供，并显式给出 `grading_weights`。

Automated Checks 约束：

- `def grade(**kwargs) -> dict`，通过 `Path(kwargs.get("workspace_path") or "/tmp_workspace")` 定位工作区。
- 不调用 LLM 或外部服务；每个 checkpoint 独立返回 `0~1`，并显式返回 `overall_score`。
- 只读取 Agent 交付、输入和 `gt/`；不得修改结果。评分失败时返回零分字典，不让异常逃逸。
- 对合理的等价表示做必要归一化，避免把实现风格当成业务正确性。

通用 Rubric 约束：

- 标题固定为 `### Criterion N: 名称 (key: stable_key, weight: 0.X)`，不要添加专项 `primary/secondary`。
- key 唯一，权重之和为 1；每项至少包含明确可判的 `1.0` 和 `0.0`，建议使用 `1.0/0.75/0.5/0.25/0.0`。
- 不用“基本正确”“质量较好”等无法复核的循环描述。

能力映射使用评分结果中的真实 key：

- `automated` 单独评分沿用 legacy 执行路径，映射未加前缀的自动评分 key。
- `llm_judge` 映射 `llm_judge.<key>`。
- `hybrid` 映射 `automated.<key>` 和 `llm_judge.<key>`。
- `overall_score` 不与组成项重复映射；仅真正的单分制任务才单独映射它。

## 前置条件

- `Skills` 只声明仓库中真实存在且可读的 `skills/<name>/SKILL.md`。
- `Env` 只写合法变量名，不写值；生成时当前环境必须已注入。
- `Warmup` 只写必要、可静态检查、可直接成功的命令。没有 Warmup 就让章节为空。
- Prompt 引用的 `/tmp_workspace/<input>` 必须来自 spec 的 `workspace.exec`；评分真值来自 `workspace.gt`，不得在 Prompt 暴露。
- 每个附件默认不超过 5 MiB，确有必要可提高到 20 MiB，不能超过仓库约定上限。

## 首版禁止项

- `07_Website_Generation`、`web-site-gen`、Playwright checker。
- `ppt` tag、PPT/图片专项 `primary/secondary` 指标或 evidence pipeline。
- 把公开网页来源误当作运行时依赖。只有任务执行时必须访问的稳定信源才进入 `runtime_sources`。
