# WildClawBench 评测集校验 Skill 设计

## 目标

为产品团队新增的 WildClawBench 评测集提供两类可复用校验能力：

1. 新增或修改任务后，静态检查任务格式、评分契约和全部预置条件是否能被框架实际使用；
2. 多模型或多 Harness 评测完成后，使用原始结果反向检查题目是否过难、过易、缺少梯度或不能区分模型差异。

两类结论统一使用 `PASS`、`REVIEW`、`FAIL`：

- `PASS`：当前输入和证据下未发现明确问题；
- `REVIEW`：统计启发式或样本不足需要人工复核，不默认阻断发布；
- `FAIL`：输入无效、任务契约破坏、结果覆盖缺失等确定性问题。

## 现状与证据

- 任务解析由 `src/utils/task_parser.py::parse_task_md()` 完成，框架实际消费 `Workspace Path`、`Skills`、`Env`、`Warmup`、`Automated Checks` 和 `LLM Judge Rubric` 等章节。
- 任务执行会把 Skill 复制到 Harness 容器，并在容器内逐行执行 Warmup；宿主机静态检查不能把 Warmup 当作安全的本地命令直接运行。
- 多轮有效 run 已有 `src/utils/run_selection.py::select_effective_run_dirs()`，显式 `run_metadata.json.supersedes_run` 的旧 run 不应再次计入统计。
- 仓库已有 `validate-eval-results`（结果完整性/可比性）和 `low-score-analysis`（逐用例失分根因）Skill；新能力不替代这两个 Skill。
- 真实样本 `/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/custom/round1/astroncode` 采用 `<model>/<harness>/<category>/<task>/<run>` 布局，共 5 个模型、1 个 Harness、300 个 `score.json`，适合验证多模型区分度，但不足以推断 Harness 敏感性。

## 设计决策

### 两个 Skill，而不是一个大 Skill

| Skill | 输入 | 主要职责 | 结论性质 |
|---|---|---|---|
| `validate-eval-dataset` | 仓库内任务目录、文件或 ID | 静态契约、资源和预置条件校验 | 确定性错误可 `FAIL` |
| `audit-eval-dataset-quality` | 任务选择 + 一个或多个外部结果根目录 | 结果覆盖、难度梯度、区分度、稳定性和 Harness 敏感性 | 统计异常为 `REVIEW` |

两个 Skill 共享解析、选择、路径发现、run 归一化和报告协议；静态规则与质量统计判据分别维护，避免规则变化污染统计结论。当前目标是 WildClawBench 仓库内团队共享，不承诺两个 Skill 脱离仓库独立安装。

### 仓库内团队分发

规范实现位于 `tools/report/skills/`，共享库位于 `tools/report/lib/eval_dataset/`。提交两个发现入口：

```text
.agents/skills/validate-eval-dataset
  -> ../../tools/report/skills/validate-eval-dataset
.agents/skills/audit-eval-dataset-quality
  -> ../../tools/report/skills/audit-eval-dataset-quality
.claude/skills/validate-eval-dataset
  -> ../../tools/report/skills/validate-eval-dataset
.claude/skills/audit-eval-dataset-quality
  -> ../../tools/report/skills/audit-eval-dataset-quality
```

`.gitignore` 只放行这四个团队入口，继续忽略两个目录下的个人设置、计划和 worktree。入口脚本使用 `Path(__file__).resolve()` 定位仓库，保证通过软链接调用时共享库仍能导入。该方案适用于当前 macOS/Linux 协作模式；若未来要求原生 Windows 且禁用 symlink，需要另行设计复制式入口或插件发行包。

## 输入契约

### 任务选择

两个 Skill 统一支持重复指定：

```text
--task-dir <目录>
--task-path <Markdown 文件>
--task-id <精确 task ID>
--task-id @<文本清单>
```

路径可为绝对路径或相对仓库根目录的路径。选择结果去重；同一 ID 匹配多个文件时报告歧义并停止，避免把官方任务和扩展任务静默合并。

`validate-eval-dataset` 未提供选择器时默认扫描 `<repo>/tasks`，因此同时覆盖官方任务和 `tasks/extension`。显式指向 `tasks/extension` 时启用扩展集额外规则。

`audit-eval-dataset-quality` 使用同一任务选择结果，并重复接受：

```text
--result-root <绝对或相对路径>
```

结果根目录可以在仓库外、解压到任意名称，也可以传入 round、model、Harness 或 unit 的上层目录。脚本递归发现已知结果布局，不要求用户移动或重命名结果包。

### Warmup smoke

- 默认只做静态检查：Shell 语法、危险命令模式、workspace 引用和脚本/文件路径可解析性；不在宿主机执行命令。
- 显式 `--smoke` 才在一次性容器中执行 Warmup，并记录退出码、超时和缺失依赖；禁止直接复用产品评测容器或修改宿主机。
- smoke 模式缺少可用 Docker/Harness 镜像时输出可诊断的 `SMOKE_UNAVAILABLE`，不把未执行误报为 Warmup 通过。

## 静态校验范围

### 通用任务契约

- frontmatter 存在、YAML 无重复键且字段类型合法；`id`、`category`、`difficulty`、`modality`、`timeout_seconds`、`grading_type` 和 `grading_weights` 满足框架约定；
- 父目录 category 与声明一致，task ID 与文件名一致且不冲突；
- 必需章节存在，空章节只允许框架明确允许的章节；
- `Automated Checks` 能静态解析出 `grade()` 和稳定评分 key，不执行作者提供的评分代码；
- `LLM Judge Rubric` 的 key、weight、criterion 数量和档位可被现有 parser 解析，混合评分权重归一；
- automated/rubric 评分 key 与能力映射的关系可追溯。

### 预置条件和资源

- `Workspace Path` 解析到仓库内或显式允许的目录，目录存在且不越界；
- 任务引用的 `exec/`、`gt/`、输入附件、参考答案、脚本和配置文件确实存在；
- `Skills` 章节非空时，逐个解析 Skill 相对路径，检查 `<skills_path>/<skill>/SKILL.md` 存在、可读且 frontmatter 合法；
- `Env` 章节只检查变量名格式、重复声明和当前执行环境是否存在；不读取、打印或写入变量值，缺失必需变量形成明确问题；
- `Warmup` 中引用的本地文件、命令脚本和 workspace 路径可解析；静态危险模式只告警或失败，不执行命令；
- 扩展任务额外校验 `tasks/extension/task_sources.yaml`、workspace 入库约定、编号保留记录和 checkpoint 能力映射。

## 结果合理性审计

### 结果归一化

1. 发现 model、Harness、category、task ID 和 run；
2. 读取 `score.json`、`execution_status.json`、`usage.json`、`anomalies.json`；
3. 复用 `select_effective_run_dirs()` 排除被替代 run；
4. 先区分缺失/无效结果、执行/基础设施异常和可用于能力比较的有效分数；
5. 以 `model@harness` 作为原始统计 unit，再分别计算模型差异和 Harness 差异。

新 Skill 只做质量审计，不替代 `validate-eval-results` 的完整结果门禁；若已有 validity JSON，审计应消费并保留其结论和证据。

### 统计检查

- 任务覆盖：选择范围与每个 model@Harness 的实际任务集合对齐；缺失或无法对齐是 `FAIL`；
- 过易/过难：按任务和难度计算均值、满分率、零分率，并标记大量集中在天花板或地板的任务；
- 模型区分度：在至少两个模型且有共同有效任务时，计算任务级分差、跨题分差分布、排序一致性和可区分任务比例；
- Harness 敏感性：至少两个 Harness 且控制模型/任务集合后才计算；只有一个 Harness 时输出 `REVIEW`（样本不足），不伪造结论；
- 稳定性：有多 run 时计算任务均值、标准差和有效 run 数；单 run 只作为横截面证据；
- 难度梯度：按 `difficulty` 分组检查总体方向，但难度等级不是等距变量；倒挂只触发 `REVIEW`，必须披露样本量、题目构成和标签风险；
- 交叉污染：发现共同环境/评分异常时，先归因有效性或基础设施，不把它解释为模型能力。

阈值采用可配置默认值，并在报告中记录阈值来源、样本量和缺失维度；默认统计异常不改变进程成功码。

## 输出契约

默认不修改任务目录和外部结果目录，输出到：

```text
<repo>/report-workspace/eval-dataset/static/
<repo>/report-workspace/eval-dataset/quality/
```

每次运行生成带时间和范围 hash 的子目录：

```text
<timestamp>_<scope-hash>/report.json
<timestamp>_<scope-hash>/report.md
```

两个报告共享如下 JSON 外层结构：

```json
{
  "schema_version": 1,
  "status": "PASS",
  "scope": {},
  "summary": {},
  "issues": []
}
```

问题对象至少包含 `severity`、`code`、`task_id`（如适用）、`location`、`message` 和 `evidence`。Env 只记录变量名和 `present/missing`，绝不输出值。外部路径只记录规范化路径和必要的相对标识，避免把密钥、完整 transcript 或大附件复制进报告。

默认退出码：`PASS`/`REVIEW` 为 0，确定性 `FAIL` 为 1，参数或输入结构无法解析为 2；`--fail-on review` 可供 CI 或发布门禁选择把 `REVIEW` 升级为失败。

## 测试与验收

### 静态 Skill

- 使用临时任务目录覆盖缺失 frontmatter、重复 YAML key、评分 key 漂移、缺失 workspace 文件、缺失 Skill、缺失 Env 和非法 Warmup；
- 使用现有 `tasks/extension` 验证默认 `<repo>/tasks` 扫描和扩展规则；
- 验证空的 `Skills`、`Env`、`Warmup` 章节不会被误判为配置；
- 验证 `--smoke` 在一次性容器中可记录成功、失败、超时和不可用；
- 验证通过 `.agents/skills` 和 `.claude/skills` 软链接调用时路径解析不依赖当前工作目录。

### 质量 Skill

- 使用真实 custom round1 结果验证 5 模型、1 Harness、300 个 score 的发现和归一化；
- 构造缺失任务、重复 run、`supersedes_run`、score 缺失、执行失败和共同环境异常样本；
- 构造单模型、单 Harness、多模型、多 Harness 及多 run 样本，验证 `REVIEW` 边界和不伪造结论；
- 验证任务均值、满分/零分率、分差、标准差、难度倒挂和样本量披露；
- 验证外部绝对结果路径无需复制到仓库，报告默认仍写入仓库 `report-workspace/eval-dataset/quality`。

### 发布验收

- Git clone 后两个客户端无需手工创建软链接即可发现 Skill；
- `.agents/skills`、`.claude/skills` 只提交四个团队入口，个人设置和 worktree 仍被忽略；
- `git diff --check`、Skill frontmatter 校验、共享库单测、两个入口脚本测试全部通过；
- 报告中不出现 Env 实际值、API key、Bearer token 或完整敏感日志。

## 非目标

- 不修改 WildClawBench 的任务执行器、评分算法或已有结果文件；
- 不把质量审计的启发式 `REVIEW` 解释成模型能力定论；
- 不在宿主机自动执行任务作者提供的 Warmup 或评分代码；
- 不要求外部评测结果目录固定在仓库或固定命名；
- 不把两个 Skill 作为第三个编排 Skill 或独立插件发行包实现。
