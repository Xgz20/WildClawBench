# AstronCode 桌面端端到端评测（eval_e2e）

用 WildClawBench 现有用例在 **AstronCode 桌面客户端**上做端到端评测，
与 CLI 侧结果对比，验证两种产品形态的多模型评测结论是否一致。

评分复用 `src/utils/grading.py`（import，不复制），与 CLI 侧**同源同码**，
故分差可归因为产品形态差异而非评分器差异。

## 三阶段流程

```
① prepare  →  [人工在桌面端执行]  →  ② collect  →  ③ grade  →  tools/report
```

三个脚本通过 `manifest.json` 串联，人工执行插在中间。

## ① 准备工作空间

```bash
python3 eval_e2e/prepare_workspaces.py \
  --task-list my_e2e_tasks.txt \
  --model xopglm52 \
  --reasoning-effort medium \
  --e2e-root eval_out_e2e
```

`--task-list` 是纯文本文件，每行一个用例 md 的仓库相对路径，`#` 开头为注释：

```
tasks/extension/02_Code_Intelligence/02_Code_Intelligence_task_001_temperature_cli_fix.md
tasks/extension/02_Code_Intelligence/02_Code_Intelligence_task_002_inventory_aggregator.md
```

产出：

- `eval_out_e2e/<model>/<task_id>/tmp_workspace/` — 项目目录，**不含 GT**
- `eval_out_e2e/<model>/<task_id>/prompt_desktop.txt` — 改写过路径，供粘贴
- `eval_out_e2e/<model>/<task_id>/prompt_original.txt` — 原文，供审计
- `eval_out_e2e/manifest.json`
- `eval_out_e2e/执行清单.md` — 人工执行清单

## ② 人工在桌面端执行

按 `执行清单.md` 逐个用例操作：

1. 桌面端新建项目，路径选清单里的项目目录（尾部为 `tmp_workspace`）
2. 选清单指定的模型与推理强度
3. 粘贴 `prompt_desktop.txt` 全文，触发执行
4. 执行结束后在清单上打勾，进入下一个用例

## ③ 采集轨迹与产物

```bash
python3 eval_e2e/collect_runs.py \
  --e2e-root eval_out_e2e \
  --out-root eval_out_e2e/results \
  --trace-root ~/.acode/sessions
```

`--trace-root` 默认 `~/.acode/sessions`。**若桌面端轨迹目录不同，用该参数覆盖**；
目录不存在时显式报错，不静默漏采。

轨迹按 `session_meta.payload.cwd` 匹配项目目录 + `timestamp` 落在执行时间窗定位。
多命中取最新并告警，零命中记 `trace_missing` 并继续处理其余用例。

## ④ 评分

```bash
python3 eval_e2e/grade_runs.py \
  --e2e-root eval_out_e2e \
  --out-root eval_out_e2e/results \
  --docker-image wildclawbench-astroncode-ubuntu:v0.4
```

把项目目录挂为容器 `/tmp_workspace`，单独 `docker cp` 送入 `gt/`，再调 `run_grading()`。
需要本机 Docker 与该镜像。

## ⑤ 出报告

结果目录与 CLI 侧同构，harness 名为 `astroncode-desktop`：

```
eval_out_e2e/results/round-1/<model>/astroncode-desktop/<category>/<task_id>/<run-slug>/
    score.json  usage.json  chat.jsonl  task_output/  manifest_entry.json  execution_status.json
```

可直接交给 `tools/report`，与 CLI 侧 `astroncode` 并列对比：

```bash
python3 tools/report/scripts/generate_eval_report.py \
  --result-root eval_out_e2e/results/round-1 \
  --models xopglm52 \
  --harnesses astroncode astroncode-desktop \
  --target-model xopglm52
```

## 通用参数

| 参数 | 说明 |
|---|---|
| `--only <task_id>` | 只处理单个用例，用于重跑 |
| `--resume` | 跳过已完成项 |

## 设计要点

- **GT 隔离**：prepare 只拷源工作区的 `exec/`，`gt/` 留在仓库，仅评分时进容器。
- **路径对齐**：容器内固定 `/tmp_workspace`（184 个用例中 164 个的 `grade()` 硬编码该字面量，
  用例一律不改）；项目目录尾部也命名 `tmp_workspace`，故 Prompt 只需替换前缀。
- **可移植**：`manifest.json` 内路径全为相对路径，换机器只需换 `--e2e-root`。
- **唯一输入差异**：桌面端 Prompt 的路径前缀。已保留双份 Prompt 与
  `prompt_rewrite_map` 供报告披露。

## 已知报告侧适配点

`tools/report/scripts/generate_eval_report.py:350` 按 harness 名选 request 抽取器，
`astroncode-desktop` 未在白名单内，else 分支会 `raise ValueError`。该分支**仅对分档定价模型触发**
（单档定价在 342 行提前返回）。本链路在 collect 阶段已把 `usage.json` 写全，报告无需回退解析。
若后续要对分档定价模型出成本对比，在报告侧把 `astroncode-desktop` 并入 Codex 系分支即可。

## 未纳入

- Codex Computer Use 自动化驱动桌面端（执行环节已可替换，补自动化不需改采集与评分）
- 多轮 round-N 统计（当前固定 `round-1`）
- 异常检测（`src/utils/anomalies.py` 面向容器内 `agent.log`，桌面端无对应日志源）
