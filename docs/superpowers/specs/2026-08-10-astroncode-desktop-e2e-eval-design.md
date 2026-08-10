# AstronCode 桌面端端到端评测设计

日期：2026-08-10
状态：待评审

## 背景与目标

WildClawBench 当前通过 AstronCode CLI 在 Docker 容器内自动化评测。本设计新增一条链路，
用**同一批评测用例**在 AstronCode 桌面客户端上做端到端评测，目的是验证
**AstronCode CLI 与 AstronCode 桌面端在多模型上的评测结论是否一致**。

两者内核同为 CLI，桌面端额外叠加 Skill 与插件，属于同一产品的两种形态对比。

### 成功标准

1. 端到端结果与 CLI 结果落在同构目录，可被 `tools/report` 当作两个并列的
   `(模型, harness)` 分析单元直接对比。
2. 评分口径与 CLI 侧**同源同码**，分差可归因为产品形态差异而非评分器差异。
3. 用例工作空间不含 Ground Truth。
4. 仓库侧路径全部相对化，换机器只需调整入口参数即可运行。

## 关键约束（基于实测）

| 约束 | 实测结论 | 设计含意 |
|---|---|---|
| GT 隔离 | `workspace/<cat>/<task>/` 已是 `exec/` + `gt/` 分离（60 个 exec、26 个 gt）；CLI 侧仅挂载 `exec/`，评分前才单独 `docker cp` 送入 `gt/`（`eval/run_batch.py:130`） | 直接沿用该约定，prepare 只拷 `exec/` |
| 用例路径 | 164/184 个用例的 `grade()` 硬编码 `/tmp_workspace` 字面量，仅 28 个读 `workspace_path` 参数；172 个用例的 Prompt 也写 `/tmp_workspace/...` | 容器内路径必须固定为 `/tmp_workspace`，用例一律不改 |
| 评分载体 | `src/utils/grading.py` 全程依赖 `docker cp` + `docker exec` | 端到端复用 Docker 评分，不新写本地评分器 |
| 模块可复用性 | `task_parser`、`grading`、`docker_utils` 均可独立 import，无循环依赖，顶层副作用仅 `load_dotenv()`；`run_grading()` 与 `start_container()` 签名为纯参数式 | 可 import 复用，无需改现有文件 |
| 桌面端环境 | 本机未安装 AstronCode 桌面端，`~/.acode` 不存在；轨迹目录待实测确认 | 轨迹根设默认值 `~/.acode/sessions` 并支持覆盖 |
| grade 契约 | `grade(transcript=..., workspace_path="/tmp_workspace")` 只吃这两个输入 | 复用切面即此契约：换执行载体，不改契约 |

## 已确认的设计决策

1. **实现形态**：仓库内新增 `eval_e2e/` 目录，import 复用 `src/utils/` 现有模块，**不修改任何现有文件**。
   拒绝复制 `grading.py`（800+ 行、含 v2 混合评分与 judge shim，复制必然漂移，漂移即摧毁归因能力）；
   拒绝改造 `run_batch.py`（900+ 行同步闭环，与端到端的三段异步流程互相牵制，且现有链路是已验证产线）。
2. **执行方式**：本期只做人工执行 + 采集，不做 Computer Use 自动化。
3. **评分载体**：复用 Docker，走现有 `run_grading()`。
4. **轨迹定位**：按时间窗 + `session_meta.payload.cwd` 自动匹配。
5. **产物边界**：项目目录即工作区，评分时挂载为容器 `/tmp_workspace`。
6. **输出结构**：完全对齐现有报告链路目录结构。
7. **路径对齐**：容器内固定 `/tmp_workspace`，仓库侧全相对路径。
8. **Prompt 差异**：项目目录尾部命名对齐（`<task_id>/tmp_workspace/`）+ 完整披露改写记录。
9. **用量指标**：解析轨迹产出 `usage.json`，以工具调用数为主口径。
10. **用例范围**：由外部 task-list 文件提供，框架不内置清单。

## 架构

端到端与 CLI 评测的差异只在"谁触发 Agent"。因此拆成三个独立阶段，
各自一个脚本，通过磁盘上的 `manifest.json` 串联，人工执行插在中间：

```
① prepare  →  [人工在桌面端执行]  →  ② collect  →  ③ grade  →  tools/report
```

| 阶段 | 脚本 | 输入 | 输出 |
|---|---|---|---|
| ① 准备 | `prepare_workspaces.py` | task-list 文件 | 项目目录、`manifest.json`、人工执行清单 |
| ② 采集 | `collect_runs.py` | `manifest.json`、轨迹根 | 结果目录骨架（`chat.jsonl`/`usage.json`/`task_output/`） |
| ③ 评分 | `grade_runs.py` | 结果目录骨架 | `score.json` |

### 目录形态

```
eval_e2e/
  prepare_workspaces.py   # ① 准备项目目录 + manifest + 人工清单
  collect_runs.py         # ② 匹配轨迹 + 落同构结果目录
  grade_runs.py           # ③ 挂载评分（复用 run_grading）
  e2e_manifest.py         # manifest 读写与相对路径解析（三脚本共享）
  README.md
tests/test_e2e_*.py       # 单测跟随现有 tests/ 约定
```

`src/utils/` 保持只读复用。若实现中发现某处必须改现有文件才能复用，
先与用户确认再动。

## 阶段设计

### ① prepare — 准备工作空间与人工执行清单

对 task-list 中每个用例：

1. `parse_task_md()` 解析 `prompt`、`workspace_path`、`automated_checks` 等字段。
2. 把 `workspace/<...>/<task>/exec/` 内容拷到 `<e2e-root>/<model>/<task_id>/tmp_workspace/`，
   **`gt/` 不拷**。项目目录尾部命名为 `tmp_workspace` 以对齐 CLI 侧路径结构。
3. 生成两份 Prompt：
   - `prompt_original.txt`：原文，供报告披露与审计
   - `prompt_desktop.txt`：把 `/tmp_workspace` 前缀替换为项目目录绝对路径，供人工粘贴
4. 写入 `manifest.json` 与人工执行清单。

`manifest.json` 中仓库内路径一律存相对路径；项目目录因需交付桌面端而存绝对路径，
但由 `--e2e-root` 在运行时重新解析，换机器只需换该参数。

```json
{
  "e2e_root": "eval_out_e2e",
  "created_at": "2026-08-10T12:00:00+08:00",
  "runs": [{
    "task_id": "02_Code_Intelligence_task_001_temperature_cli_fix",
    "category": "02_Code_Intelligence",
    "task_file": "tasks/extension/02_Code_Intelligence/..._cli_fix.md",
    "workspace_src": "workspace/extension/02_Code_Intelligence/task_001_temperature_cli_fix",
    "project_dir": "eval_out_e2e/<model>/<task_id>/tmp_workspace",
    "model": "xopglm52",
    "reasoning_effort": "medium",
    "prompt_rewritten": true,
    "prompt_rewrite_map": {"/tmp_workspace": "<abs project_dir>"},
    "status": "pending"
  }]
}
```

人工执行清单 `执行清单.md` 每个用例一段，含：序号、项目目录路径（可直接复制到桌面端
"打开项目"）、要选的模型与推理强度、可直接粘贴的 Prompt、执行完的打勾记录位。

### ② collect — 采集轨迹与产物

对 manifest 每个 run：

1. **定位轨迹**：扫描 `--trace-root`（默认 `~/.acode/sessions`，可覆盖）下所有 `*.jsonl`，
   读首行 `session_meta`，取 `payload.cwd` 与项目目录匹配、且 `timestamp` 落在执行时间窗内的文件。
   命中多个取最新并告警；零命中记 `trace_missing` 并继续处理其余用例。
2. **落结果目录**：写成与 CLI 侧同构的
   `<out>/round-1/<model>/astroncode-desktop/<category>/<task_id>/<run-slug>/`，内含：
   - `chat.jsonl`：轨迹原文
   - `usage.json`：解析出的 token 用量与工具调用数
   - `task_output/`：项目目录快照
   - `manifest_entry.json`：含 Prompt 改写记录
   - `execution_status.json`：采集状态与失败原因
3. **用量口径**：以工具调用数为主口径，token 从轨迹 usage 字段累加。
   沿用 CLI 侧既有结论——`request_count` 存在低估，不作主口径。

harness 名定为 `astroncode-desktop`，与 CLI 侧 `astroncode` 并列，
使 `tools/report` 可将两者作为两个分析单元直接对比。

**已知的报告侧适配点**：`tools/report/scripts/generate_eval_report.py:350` 按 harness 名
分支选择 request 抽取器，`("astroncode", "codex")` 走 Codex 系抽取器，未命中的 harness
在 else 分支 `raise ValueError`。该分支**仅在分档定价模型上触发**（单档定价在 342 行提前返回），
因此影响面有限。本设计的应对是：collect 阶段把 `usage.json` 写全（token 用量与工具调用数
均已解析落盘），使报告无需回退到按 harness 分支的轨迹重解析。若后续要对分档定价模型出成本对比，
再在报告侧把 `astroncode-desktop` 并入 Codex 系分支——属报告侧一行改动，不影响本设计。

### ③ grade — 评分

对每个已采集的 run：

1. `start_container(task_id, project_dir, docker_image=...)` 把项目目录挂为容器 `/tmp_workspace`。
2. `docker cp` 把 `gt/` 送入 `/tmp_workspace/gt`（复刻 `run_batch.py:130` 手法）。
3. 调 `run_grading()`，参数由 `parse_task_md()` 原样透传。
4. `score.json` 写入结果目录，容器销毁。

评分完全走现有 `run_grading()`，v2 混合评分（规则 + LLM rubric）随之自动生效，无需额外适配。

## 错误处理

单用例失败不中断批次，失败原因落盘 `execution_status.json`：

| 阶段 | 失败情形 | 处理 |
|---|---|---|
| prepare | 源工作区缺失 | 跳过并列入 skipped，批次继续 |
| collect | 轨迹零命中 | 记 `trace_missing`，批次继续 |
| collect | 轨迹多命中 | 取最新并告警 |
| grade | 容器启动失败 / `grade()` 抛异常 | 复用 `write_error_score()` 写 error score，与 CLI 侧一致 |

三个脚本均支持 `--only <task_id>` 重跑单个用例，以及 `--resume` 跳过已完成项。

## 可比性与差异披露

桌面端 Prompt 必须改写路径，这是与 CLI 侧**唯一的输入差异**，属必要差异
（路径须真实存在才能执行）。两项措施把它压到最小并使其可解释：

1. **尾部结构对齐**：项目目录命名为 `<task_id>/tmp_workspace/`，Prompt 只替换前缀，
   尾部路径结构与 CLI 侧一致。
2. **完整披露**：保留 `prompt_original.txt` 与 `prompt_desktop.txt` 两份，
   结果中记录 `prompt_rewritten: true` 与 `prompt_rewrite_map`，供报告明确标注。

除此之外，用例文本、工作空间内容、评分代码、GT 三者与 CLI 侧完全同源。

## 测试

单测放 `tests/`，跟随现有约定，覆盖：

- `manifest.json` 相对路径解析：换 `--e2e-root` 后路径正确重解析
- Prompt 改写：前缀替换正确、尾部结构保持、原文保留
- GT 隔离：prepare 产出的项目目录不含 `gt/`（回归断言）
- 轨迹匹配：按 `cwd` + 时间窗命中；零命中与多命中的分支行为
- usage 解析：token 累加与工具调用计数
- 错误分支：源工作区缺失、轨迹缺失、评分异常各自落盘正确状态

端到端联调需桌面端实机，本期以 CLI 侧已有轨迹样例做匹配逻辑的替身验证。

## 未纳入本期范围

- **Codex Computer Use 批量驱动桌面端**（含授权中断处理）：桌面端 UI 元素与中断行为均未知，
  属高不确定性投入。三阶段拆分已使执行环节可替换，后续补自动化时无需改动采集与评分链路。
- **多轮（round-N）与多模型并行编排**：本期固定 `round-1`，多模型靠重复执行三阶段实现。
- **异常检测接入**：`src/utils/anomalies.py` 面向容器内 `agent.log`，桌面端无对应日志源。

## 待实测确认项

以下三项均已设计成"默认值 + 可覆盖 / 局部适配"，不阻塞实现：

1. **桌面端轨迹根目录**：默认 `~/.acode/sessions`（对齐 CLI 侧 `/root/.acode/sessions` 命名）。
   实机不符时由 `--trace-root` 覆盖；目录不存在时显式报错，不静默漏采。
2. **轨迹是否含 `session_meta.payload.cwd`**：Codex Desktop 轨迹实测含该字段
   （`"originator":"Codex Desktop"` 样例已验证）。AstronCode 桌面端字段名若不同，
   仅需适配 collect 的轨迹解析处。
3. **轨迹 usage 字段结构**：影响 `usage.json` 解析细节，不影响得分。

## 待用户提供

- 用例 task-list 清单（用户已确认稍后提供），框架不内置清单。
