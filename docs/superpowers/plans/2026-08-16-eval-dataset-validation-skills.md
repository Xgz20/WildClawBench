# WildClawBench 评测集校验 Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 WildClawBench 仓库内提供两个可由 Codex 和 Claude Code 自动发现的 Skill，分别完成任务集静态契约校验和基于外部评测结果的题目质量审计。

**Architecture:** 两个 Skill 保持独立入口和判据，共享 `tools/report/lib/eval_dataset/` 中的选择器、任务/结果解析、run 归一化、问题对象和报告输出。Skill 实现位于 `tools/report/skills/`，`.agents/skills` 与 `.claude/skills` 提交相对软链接；静态 Skill 默认扫描 `tasks/`，质量 Skill 接受仓库外任意结果根目录。

**Tech Stack:** Python 3、PyYAML、标准库 `argparse`/`ast`/`statistics`/`subprocess`/`pathlib`、现有 `src.utils.task_parser`、`src.utils.run_selection`、`src.utils.anomalies`、pytest、Agent Skills `SKILL.md` + `agents/openai.yaml`。

---

## 文件结构与职责

### 共享基础库

- Create: `tools/report/lib/eval_dataset/__init__.py` — 导出共享公共接口和 schema 版本。
- Create: `tools/report/lib/eval_dataset/contracts.py` — `Issue`、`Report`、`Status`、退出码、JSON 序列化和 secret-safe evidence。
- Create: `tools/report/lib/eval_dataset/selectors.py` — `--task-dir`、`--task-path`、`--task-id`、`@file` 解析、去重、精确 ID 歧义检测。
- Create: `tools/report/lib/eval_dataset/task_files.py` — Markdown/frontmatter/章节解析、任务相对路径、Skill/Env/Warmup 引用提取。
- Create: `tools/report/lib/eval_dataset/result_files.py` — 结果根目录发现、model/Harness/category/task/run 归一化、JSON 读取和 `select_effective_run_dirs()` 适配。
- Create: `tools/report/lib/eval_dataset/reporting.py` — 默认输出路径、scope hash、JSON/Markdown 输出和退出码。
- Create: `tools/report/lib/eval_dataset/security.py` — Env/Token 脱敏、路径越界和 Warmup 危险命令检查。
- Test: `tools/report/tests/test_eval_dataset_common.py`。

### 静态校验 Skill

- Create via `init_skill.py`: `tools/report/skills/validate-eval-dataset/SKILL.md`。
- Create: `tools/report/skills/validate-eval-dataset/agents/openai.yaml`。
- Create: `tools/report/skills/validate-eval-dataset/references/checklist.md`。
- Create: `tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py`。
- Create: `tools/report/tests/test_validate_eval_dataset.py`。

### 质量审计 Skill

- Create via `init_skill.py`: `tools/report/skills/audit-eval-dataset-quality/SKILL.md`。
- Create: `tools/report/skills/audit-eval-dataset-quality/agents/openai.yaml`。
- Create: `tools/report/skills/audit-eval-dataset-quality/references/quality-methods.md`。
- Create: `tools/report/skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py`。
- Create: `tools/report/tests/test_audit_eval_dataset_quality.py`。

### 团队发现入口

- Modify: `.gitignore` — 只放行四个 Skill 软链接和其父目录，不放行个人配置、计划、worktree。
- Create symlink: `.agents/skills/validate-eval-dataset` -> `../../tools/report/skills/validate-eval-dataset`。
- Create symlink: `.agents/skills/audit-eval-dataset-quality` -> `../../tools/report/skills/audit-eval-dataset-quality`。
- Create symlink: `.claude/skills/validate-eval-dataset` -> `../../tools/report/skills/validate-eval-dataset`。
- Create symlink: `.claude/skills/audit-eval-dataset-quality` -> `../../tools/report/skills/audit-eval-dataset-quality`。

### 生成产物

- Modify: `.gitignore` — 忽略 `report-workspace/eval-dataset/`。
- Runtime output: `report-workspace/eval-dataset/static/<timestamp>_<scope-hash>/report.{json,md}`。
- Runtime output: `report-workspace/eval-dataset/quality/<timestamp>_<scope-hash>/report.{json,md}`。

## 实施任务

### Task 1: 锁定共享契约、选择器和报告 schema

**Files:**
- Create: `tools/report/lib/eval_dataset/{__init__,contracts,selectors,task_files,result_files,reporting,security}.py`
- Test: `tools/report/tests/test_eval_dataset_common.py`

- [ ] **Step 1: Write the failing tests for selection and status.**

  在 `test_eval_dataset_common.py` 中创建临时 `tasks/01_Productivity_Flow/a.md`、`tasks/extension/01_Productivity_Flow/b.md` 和 `ids.txt`，断言：默认根目录只在调用方传入的 repo 下扫描；重复 `--task-path` 去重；`--task-id @ids.txt` 按行展开；同 ID 两个文件时返回 `TASK_ID_AMBIGUOUS`；`PASS`/`REVIEW` 的默认退出码为 0、`FAIL` 为 1、参数错误为 2；Env 值在 evidence 中只出现变量名和 `present/missing`。

- [ ] **Step 2: Run the focused test to verify the expected import failure.**

  Run:

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_common.py -q
  ```

  Expected: FAIL because `tools.report.lib.eval_dataset` and its public functions do not exist yet。

- [ ] **Step 3: Implement the minimal shared interfaces.**

  `selectors.py` 使用 `Path.resolve()`，默认根目录由脚本显式传入；解析 `@file` 时忽略空行和 `#` 注释但保留路径中的空格；ID 采用精确匹配，0 个匹配返回 `TASK_ID_NOT_FOUND`，多个匹配返回 `TASK_ID_AMBIGUOUS`。`contracts.py` 定义：

  ```python
  @dataclass(frozen=True)
  class Issue:
      severity: str
      code: str
      message: str
      task_id: str = ""
      location: str = ""
      evidence: dict[str, object] = field(default_factory=dict)

  @dataclass
  class Report:
      schema_version: int
      status: str
      scope: dict[str, object]
      summary: dict[str, object]
      issues: list[Issue]
  ```

  `reporting.py` 计算范围 hash 时只使用规范化选择结果、结果根目录和规则版本，不读 transcript 内容；默认根目录固定为当前仓库的 `report-workspace/eval-dataset/{static,quality}`。

- [ ] **Step 4: Run the focused tests and inspect serialized output.**

  Run:

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_common.py -q
  python3 -m json.tool <(python3 -c 'from tools.report.lib.eval_dataset.contracts import Issue; import json; print(json.dumps(Issue("error", "X", "secret", evidence={"API_KEY": "missing"}).__dict__))')
  ```

  Expected: all focused tests pass; serialized issue contains no secret value。

- [ ] **Step 5: Commit the shared contract.**

  ```bash
  git add tools/report/lib/eval_dataset tools/report/tests/test_eval_dataset_common.py
  git commit -m "feat(eval-dataset): 增加评测集校验共享契约"
  ```

### Task 2: 实现任务 Markdown、评分和预置资源静态校验

**Files:**
- Create: `tools/report/skills/validate-eval-dataset/SKILL.md`
- Create: `tools/report/skills/validate-eval-dataset/agents/openai.yaml`
- Create: `tools/report/skills/validate-eval-dataset/references/checklist.md`
- Create: `tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py`
- Test: `tools/report/tests/test_validate_eval_dataset.py`

- [ ] **Step 1: Initialize the Skill directory.**

  Run the repository-independent initializer with deterministic metadata:

  ```bash
  python3 /Users/gzx/.codex/skills/.system/skill-creator/scripts/init_skill.py \
    validate-eval-dataset \
    --path /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench/tools/report/skills \
    --resources scripts,references \
    --interface display_name='Validate Eval Dataset' \
    --interface short_description='检查 WildClawBench 任务格式与运行前置条件' \
    --interface default_prompt='校验 tasks/extension 或指定任务的框架契约、workspace、Skill、Env 和 Warmup。'
  ```

  删除 initializer 生成的占位内容后再写入真实 Skill，不创建 README 或安装指南。

- [ ] **Step 2: Write failing tests for representative task fixtures.**

  测试 fixture 至少覆盖：缺 frontmatter、重复 YAML key、category 不一致、`Automated Checks` 无 `grade()`、rubric 重复 key、缺 `workspace/extension/01_Productivity_Flow/exec/answer.py` 文件、`Skills` 为 `agent-browser` 但 `skills/agent-browser/SKILL.md` 缺失、Env 名称非法、Warmup 为空以及 Warmup 引用不存在的脚本。断言每项返回稳定 code 和 `FAIL`，而不是执行作者代码。

- [ ] **Step 3: Run the static validator tests to verify RED.**

  ```bash
  python3 -m pytest tools/report/tests/test_validate_eval_dataset.py -q
  ```

  Expected: FAIL because `validate_eval_dataset.py` has no validator entry point。

- [ ] **Step 4: Implement static validation in deterministic layers.**

  `validate_eval_dataset.py` 做以下顺序：解析选择器；读取 frontmatter/sections；运行通用 schema 规则；用 `ast.parse()` 提取 `grade()` 和评分 key；调用现有 `src.utils.task_parser.parse_rubric_criteria()` 但不执行任务代码；解析 `Workspace Path` 和 `skills_path`；检查 `skills/<name>/SKILL.md`；检查 workspace 目录下由任务定义明确引用的 `exec`/`gt`/附件/脚本；仅对当前进程 `os.environ` 做变量存在性检查并用 `security.py` 脱敏；静态检查 Warmup 的 shell 语法和危险模式；对 `tasks/extension` 读取 `task_sources.yaml` 与能力映射。

  CLI 默认使用 `Path(__file__).resolve().parents[5] / "tasks"` 作为任务根，支持重复 `--task-dir`、`--task-path`、`--task-id`、`--output-dir`、`--smoke` 和 `--fail-on review`。脚本只在 `--smoke` 时调用独立 smoke helper。

- [ ] **Step 5: Run fixture tests and the real default scan.**

  ```bash
  python3 -m pytest tools/report/tests/test_validate_eval_dataset.py -q
  python3 tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py \
    --output-dir /tmp/wcb-static-validation-check
  ```

  Expected: fixture tests pass; real scan produces `report.json` and `report.md` under the explicit temporary directory, and any existing task issues are listed as evidence rather than hidden。

- [ ] **Step 6: Write the Skill instructions and checklist.**

  `SKILL.md` 只写触发条件、默认命令、选择器、PASS/REVIEW/FAIL、预置条件处理和报告路径；把详细规则放入 `references/checklist.md`。明确禁止执行评分代码、宿主机 Warmup、输出 Env 值和把缺失 Skill 静默跳过。

- [ ] **Step 7: Validate the Skill folder.**

  ```bash
  python3 /Users/gzx/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
    tools/report/skills/validate-eval-dataset
  ```

  Expected: frontmatter and naming validation pass。

- [ ] **Step 8: Commit the static Skill.**

  ```bash
  git add tools/report/skills/validate-eval-dataset tools/report/tests/test_validate_eval_dataset.py
  git commit -m "feat(eval-dataset): 增加评测集静态校验 Skill"
  ```

### Task 3: 增加 Warmup smoke 的一次性容器验证

**Files:**
- Create: `tools/report/lib/eval_dataset/smoke.py`
- Modify: `tools/report/skills/validate-eval-dataset/scripts/validate_eval_dataset.py`
- Modify: `tools/report/skills/validate-eval-dataset/references/checklist.md`
- Test: `tools/report/tests/test_eval_dataset_smoke.py`

- [ ] **Step 1: Write failing smoke tests.**

  使用临时 fake Docker executable 验证：空 Warmup 不启动容器；成功命令返回 `smoke_passed`；非零退出返回 `WARMUP_SMOKE_FAILED`；缺 Docker 或镜像返回 `SMOKE_UNAVAILABLE`；命令字符串不写入宿主机；默认模式不调用 subprocess。

- [ ] **Step 2: Run the smoke tests to verify RED.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_smoke.py -q
  ```

  Expected: FAIL because the smoke helper is absent。

- [ ] **Step 3: Implement the bounded smoke helper.**

  `smoke.py` 只接受解析后的 Warmup 命令、明确的容器镜像和临时 workspace；使用 `subprocess.run(command, timeout=timeout_seconds, check=False, capture_output=True, text=True)`，容器使用 `--rm`，不挂载仓库写目录，不注入未脱敏 Env 值；为每条命令返回退出码、截断 stderr 和状态。静态 Skill 没有 `--smoke` 时不得触发该模块。

- [ ] **Step 4: Run smoke tests and a no-Docker default-mode regression.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_smoke.py tools/report/tests/test_validate_eval_dataset.py -q
  ```

  Expected: all tests pass and default validation remains host-execution-free。

- [ ] **Step 5: Commit smoke support.**

  ```bash
  git add tools/report/lib/eval_dataset/smoke.py \
    tools/report/skills/validate-eval-dataset \
    tools/report/tests/test_eval_dataset_smoke.py
  git commit -m "feat(eval-dataset): 增加 Warmup 安全 smoke 校验"
  ```

### Task 4: 实现外部结果发现、有效 run 归一化和统计指标

**Files:**
- Modify: `tools/report/lib/eval_dataset/result_files.py`
- Create: `tools/report/lib/eval_dataset/metrics.py`
- Test: `tools/report/tests/test_eval_dataset_results.py`
- Test: `tools/report/tests/test_eval_dataset_metrics.py`

- [ ] **Step 1: Write failing result-discovery tests.**

  在 `test_eval_dataset_results.py` 构造 `/tmp/wcb-eval-results-fixture/round/model-a/harness-a/01_Productivity_Flow/task-a/run-1/`、第二个 model、第二个 Harness、缺 score、`run_metadata.json.supersedes_run` 和外部绝对路径。断言发现结果、读取 `score.json`/`execution_status.json`/`usage.json`、排除 superseded run、保留 0 分有效 run，并区分缺失结果与执行异常。

- [ ] **Step 2: Run result tests to verify RED.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_results.py -q
  ```

  Expected: FAIL because external result normalization is not implemented。

- [ ] **Step 3: Implement result discovery by composing existing utilities.**

  `result_files.py` 不复制 `select_effective_run_dirs()`；直接导入 `src.utils.run_selection`，并对 round/model/unit 起点递归发现结果。只读取 JSON object，记录 `result_path`、model、Harness、category、task ID、run 名和 validity evidence；绝不把 transcript 全量载入报告。

- [ ] **Step 4: Write failing metric tests.**

  在 `test_eval_dataset_metrics.py` 构造 2 模型 × 2 Harness × 3 任务 × 2 runs，断言任务均值、满分率、零分率、跨模型分差、标准差、难度分组、单 Harness 的样本不足状态、多 Harness 的 Harness 分差和缺失/无效结果不被当作能力分数。

- [ ] **Step 5: Run metric tests to verify RED.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_metrics.py -q
  ```

  Expected: FAIL because `metrics.py` has no aggregation functions。

- [ ] **Step 6: Implement deterministic metrics.**

  `metrics.py` 提供 `aggregate_task_scores()`、`compare_models()`、`compare_harnesses()`、`difficulty_summary()`、`stability_summary()`；任务均值等权，run 先按有效选择规则归一化；单模型/单 Harness 返回样本不足 evidence；统计阈值集中为不可变默认配置并支持 CLI 覆盖；任何启发式异常创建 `REVIEW` issue，不改变默认成功码。

- [ ] **Step 7: Run all result and metric tests.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_results.py \
    tools/report/tests/test_eval_dataset_metrics.py -q
  ```

  Expected: all tests pass with exact floating-point assertions使用 `pytest.approx`。

- [ ] **Step 8: Commit result and metric foundations.**

  ```bash
  git add tools/report/lib/eval_dataset/result_files.py \
    tools/report/lib/eval_dataset/metrics.py \
    tools/report/tests/test_eval_dataset_results.py \
    tools/report/tests/test_eval_dataset_metrics.py
  git commit -m "feat(eval-dataset): 增加评测结果归一化与区分度统计"
  ```

### Task 5: 实现质量审计 Skill 和报告

**Files:**
- Create via `init_skill.py`: `tools/report/skills/audit-eval-dataset-quality/SKILL.md`
- Create: `tools/report/skills/audit-eval-dataset-quality/agents/openai.yaml`
- Create: `tools/report/skills/audit-eval-dataset-quality/references/quality-methods.md`
- Create: `tools/report/skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py`
- Test: `tools/report/tests/test_audit_eval_dataset_quality.py`

- [ ] **Step 1: Initialize the quality Skill with repository-local metadata.**

  ```bash
  python3 /Users/gzx/.codex/skills/.system/skill-creator/scripts/init_skill.py \
    audit-eval-dataset-quality \
    --path /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/WildClawBench/tools/report/skills \
    --resources scripts,references \
    --interface display_name='Audit Eval Dataset Quality' \
    --interface short_description='用多模型多 Harness 结果反向检查评测集质量' \
    --interface default_prompt='使用指定评测结果目录审计题目难度梯度、模型区分度、稳定性和 Harness 敏感性。'
  ```

- [ ] **Step 2: Write failing quality-report tests.**

  使用 Task 4 的 fixture 断言：外部结果根目录被接受；报告 `scope` 包含结果根目录和选中任务；5 模型/1 Harness 场景输出模型统计并生成 Harness `REVIEW`；缺失 task 是 `FAIL`；过易/过难、难度倒挂、单 run 样本不足是 `REVIEW`；JSON/Markdown 只引用证据摘要，不带 `OPENROUTER_API_KEY`、Bearer token 或 transcript 全文。

- [ ] **Step 3: Run quality tests to verify RED.**

  ```bash
  python3 -m pytest tools/report/tests/test_audit_eval_dataset_quality.py -q
  ```

  Expected: FAIL because the quality Skill entry point is absent。

- [ ] **Step 4: Implement the quality CLI and renderer.**

  CLI 参数为 `--result-root`（可重复）、共享任务选择器参数、`--validity` 可选、`--output-dir`、`--fail-on review` 和可配置统计阈值。入口先运行 result discovery，再加载 validity JSON（若提供），计算 metrics，合并 issues，使用 `reporting.py` 写入 `report-workspace/eval-dataset/quality/<timestamp>_<scope-hash>/report.{json,md}`。结果只有一个 Harness 时明确输出“无法评估 Harness 敏感性”，不得把模型差异写成 Harness 结论。

- [ ] **Step 5: Write quality instructions and methods reference.**

  `SKILL.md` 说明外部路径、默认任务根、命令示例、单模型/单 Harness 样本限制、validity JSON 边界和报告位置；`quality-methods.md` 固化均值、满分/零分率、分差、标准差、难度梯度和 REVIEW 解释，不写未经真实数据验证的阈值结论。

- [ ] **Step 6: Run folder validation and focused tests.**

  ```bash
  python3 /Users/gzx/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
    tools/report/skills/audit-eval-dataset-quality
  python3 -m pytest tools/report/tests/test_audit_eval_dataset_quality.py -q
  ```

  Expected: Skill metadata validation and focused quality tests pass。

- [ ] **Step 7: Commit the quality Skill.**

  ```bash
  git add tools/report/skills/audit-eval-dataset-quality \
    tools/report/tests/test_audit_eval_dataset_quality.py
  git commit -m "feat(eval-dataset): 增加评测集质量审计 Skill"
  ```

### Task 6: 固化团队 Skill 发现入口与生成目录忽略规则

**Files:**
- Modify: `.gitignore`
- Create symlink: `.agents/skills/validate-eval-dataset`
- Create symlink: `.agents/skills/audit-eval-dataset-quality`
- Create symlink: `.claude/skills/validate-eval-dataset`
- Create symlink: `.claude/skills/audit-eval-dataset-quality`

- [ ] **Step 1: Write the discovery regression test.**

  在 `tools/report/tests/test_eval_dataset_distribution.py` 中使用 `Path.is_symlink()`/`os.readlink()` 断言四个路径的目标分别为 `../../tools/report/skills/...`，并使用 `git check-ignore` 断言它们不再被忽略；个人 `.agents/deepseek-harness-poc`、`.agents/hermesagent-production-readiness`、`.claude/plans` 和 `.claude/settings.local.json` 仍被忽略。

- [ ] **Step 2: Run the distribution test to verify RED.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_distribution.py -q
  ```

  Expected: FAIL because the new symlinks and allowlist do not exist。

- [ ] **Step 3: Update ignore rules and create tracked links.**

  将 `.gitignore` 中整目录忽略改为只忽略个人内容并逐项放行四个链接和 `report-workspace/eval-dataset/`；创建四个相对链接：

  ```bash
  mkdir -p .agents/skills .claude/skills
  ln -s ../../tools/report/skills/validate-eval-dataset .agents/skills/validate-eval-dataset
  ln -s ../../tools/report/skills/audit-eval-dataset-quality .agents/skills/audit-eval-dataset-quality
  ln -s ../../tools/report/skills/validate-eval-dataset .claude/skills/validate-eval-dataset
  ln -s ../../tools/report/skills/audit-eval-dataset-quality .claude/skills/audit-eval-dataset-quality
  ```

  只用 `git add -f` 放行这四个链接，不添加当前个人目录。

- [ ] **Step 4: Run discovery and path-resolution tests.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_distribution.py -q
  git diff --check
  ```

  Expected: filesystem link and ignore tests pass; from repository root 和 `/tmp` 分别执行两个入口时都能定位共享库。

- [ ] **Step 5: Commit team distribution.**

  ```bash
  git add .gitignore tools/report/tests/test_eval_dataset_distribution.py
  git add -f .agents/skills/validate-eval-dataset \
    .agents/skills/audit-eval-dataset-quality \
    .claude/skills/validate-eval-dataset \
    .claude/skills/audit-eval-dataset-quality
  git commit -m "chore(skills): 固化评测集校验团队入口"
  ```

### Task 7: 使用真实任务和外部 round1 结果完成回归验收

**Files:**
- Modify: `tools/report/skills/validate-eval-dataset/references/checklist.md` — only when real-input findings require clarifying a rule or evidence boundary.
- Modify: `tools/report/skills/audit-eval-dataset-quality/references/quality-methods.md` — only when real-input findings require clarifying a metric or sample limitation.
- Test: `tools/report/tests/test_eval_dataset_real_inputs.py`

- [ ] **Step 1: Add a read-only real-input regression test.**

  测试只读取当前仓库任务和 `/Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/custom/round1/astroncode`，断言发现 5 个 model@Harness、300 个 score 文件、1 个 Harness 样本不足 issue；不把真实报告写入 Git 工作区，使用 `TemporaryDirectory` 作为 output。

- [ ] **Step 2: Run the real-input regression.**

  ```bash
  python3 -m pytest tools/report/tests/test_eval_dataset_real_inputs.py -q
  ```

  Expected: PASS；如果外部目录缺失，测试明确标记为 skipped 并在结果中写出原因，不伪造通过。

- [ ] **Step 3: Run the user-facing commands.**

  ```bash
  python3 .agents/skills/validate-eval-dataset/scripts/validate_eval_dataset.py \
    --output-dir /tmp/wcb-final-static-validation

  python3 .agents/skills/audit-eval-dataset-quality/scripts/audit_eval_dataset_quality.py \
    --result-root /Users/gzx/Project/GitHub/xgz/ai/evaluate/WildClawBench/eval_out/custom/round1/astroncode \
    --output-dir /tmp/wcb-final-quality-audit
  ```

  Expected: 两个命令均生成 JSON/Markdown；质量审计明确报告单 Harness 限制；静态校验不执行作者 Warmup 或评分代码。

- [ ] **Step 4: Run the focused full verification set.**

  ```bash
  python3 -m pytest \
    tools/report/tests/test_eval_dataset_common.py \
    tools/report/tests/test_eval_dataset_smoke.py \
    tools/report/tests/test_validate_eval_dataset.py \
    tools/report/tests/test_eval_dataset_results.py \
    tools/report/tests/test_eval_dataset_metrics.py \
    tools/report/tests/test_audit_eval_dataset_quality.py \
    tools/report/tests/test_eval_dataset_distribution.py \
    tools/report/tests/test_eval_dataset_real_inputs.py -q
  python3 -m pytest tests/test_task_rubric_parser.py tests/test_task_warmups.py tests/test_validate_eval_results.py -q
  git diff --check
  ```

  Expected: all focused tests pass; unrelated pre-existing failures must单独记录，不修改无关文件。

- [ ] **Step 5: Review secret safety and Git scope.**

  ```bash
  rg -n "sk-[A-Za-z0-9_-]{8,}|Bearer [A-Za-z0-9._~+/-]{8,}|OPENROUTER_API_KEY=.*[^$]" \
    /tmp/wcb-final-static-validation /tmp/wcb-final-quality-audit || true
  git status --short
  git diff --stat e6ce056..HEAD
  ```

  Expected: reports contain no secret values；工作树只含本计划范围内的实现、测试、Skill、软链接和忽略规则变更。

- [ ] **Step 6: Commit the real-input regression and final docs updates.**

  ```bash
  git add tools/report/tests/test_eval_dataset_real_inputs.py \
    tools/report/skills/validate-eval-dataset/references/checklist.md \
    tools/report/skills/audit-eval-dataset-quality/references/quality-methods.md
  git commit -m "test(eval-dataset): 完成评测集校验真实结果回归"
  ```

## Plan self-review

- 设计文档的两 Skill 拆分、共享库、默认 `tasks/`、预置条件、Warmup smoke、外部结果路径、三态结论、团队软链接和输出目录均有对应任务。
- 结果质量 Skill 明确复用 `src.utils.run_selection`，不复制既有有效 run 规则，也不替代 `validate-eval-results`。
- 计划没有执行作者评分代码或宿主机 Warmup 的步骤；真实结果回归只读外部目录并把输出写入 `/tmp`。
- 共享接口在 Task 1 定义后，Task 2–7 均使用同一命名；入口脚本路径和默认 output path 固定。
- 统计启发式只生成 `REVIEW`，缺失/不可解析输入才生成 `FAIL`，与批准的设计一致。
