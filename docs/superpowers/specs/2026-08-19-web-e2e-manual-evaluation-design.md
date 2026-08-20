# Web 站点端到端人工评测方案

## 决策摘要

新建一条与 `eval_e2e/`、WildClawBench Runner、`run_grading()`、既有 LLM Judge 和固定 Playwright checker 完全分离的人工评测链路。WildClawBench 只提供产品圈定用例的题目定义和初始 `Workspace/exec`；测试人员在 Harness 桌面端逐题手工触发执行，再在桌面评分智能体中逐题手工触发评分 Skill。评分 Agent 使用自身浏览器工具启动、操作和取证，不由代码控制浏览器。

交付拆成三个 Skill：

1. `prepare-web-e2e-workspaces`：按用例 ID 和 Harness 列表生成执行包、评分增量包、独立评分 Skill ZIP 和兜底工具；
2. `score-web-e2e`：作为评分客户端独立安装、可单独升级的 Skill，驱动评分 Agent 对单题站点操作取证，并用 Node.js 校验生成标准 JSON；
3. `report-web-e2e`：校验多个回传包，读取工程内批次配置，生成领导版 Markdown、报告数据 JSON 和三 Sheet Excel。

三个 Skill 的 canonical 源目录统一位于 `tools/report/skills/<skill-name>/`，`.agents/skills/<skill-name>` 只保留指向 canonical 源的相对软链接。

脚本只处理确定性工作：复制 Workspace、改写路径、隔离私有评分材料、合并目录、校验 JSON、计算分数、过滤敏感内容和渲染报表。脚本不发题、不调用 Harness、不控制浏览器，也不决定 criterion 分数。

## 范围与非目标

### 范围

- 产品提供约 20 个完整用例 ID；准备脚本不内置固定用例清单。
- 未显式指定批次号时，使用本机时间生成 `web-e2e-YYYYMMDD-HHMMSS`，避免同一天多次生成发生目录冲突。
- 首批 Harness 为 AstronStudio、Codex、WorkBuddy、Trae，也允许增加新的安全 slug。
- 每个 Harness、每个用例使用独立工作空间；每个评分会话只评一个用例。
- 评分依据严格来自该题 Prompt、Expected Behavior、LLM Judge Rubric 和实际浏览器证据。
- 支持总分、得分率、满分率、完成率、难度、一级/二级 Web 维度、资源指标和独立页面美观度。

### 非目标

- 不自动驱动桌面端输入 Prompt。
- 不自动批量创建桌面工作空间或会话。
- 不复用 `eval_e2e/` 的执行、轨迹匹配、容器评分或结果目录。
- 不复用 WildClawBench 的 `run_grading()`、LLM Judge 或网站 Playwright checker。
- 页面美观度采用产品定义的 `web-aesthetic-v1`：6 个加权一级维度和 32 个二级检查项，对同一用例的代表性截图集合统一判定，独立于功能总分。

## 分包与目录契约

每个 Harness 生成两个 ZIP。

### execution 包

execution ZIP 带固定顶层目录，测试人员解压后直接得到 Harness 根目录：

```text
<batch_id>__<harness>/
├── manifest.json
├── 执行清单.md
├── execution/
│   └── tasks/
│       └── <task_id>/
│           ├── PROMPT.md
│           └── workspace/
├── score/                              # 预置空目录
├── tools/
│   └── prepare_scoring_workspace.py
├── 准备评分工作空间.command            # macOS 双击兜底
└── 准备评分工作空间.cmd                # Windows 双击兜底
```

执行时，被评 Harness 每题选择以下目录作为桌面工作空间：

```text
<harness-package-root>/execution/tasks/<task_id>/
```

工作空间根只存在一个有效 `PROMPT.md`。测试人员在新会话中粘贴该文件内容，候选产物写入同级 `workspace/`。选择 `execution/tasks/<task_id>/workspace/` 会丢失题目标识，因此不采用。

默认不生成 `execution_record.json`，单题执行目录只有 `PROMPT.md` 和 `workspace/`。若管理员确实需要采集 Token、耗时、成本或执行错误，可在准备批次时显式启用执行记录；该能力保留，但不作为当前人工流程的默认负担。单题 `task_manifest.json` 不生成：它既重复根目录批次索引，又会向被评 Harness 暴露评分文件路径。

候选 Harness 可见的 execution 包不得包含 Expected Behavior、Rubric、`eval/`、`gt/`、评分 fixtures 或 `score-web-e2e` Skill。

### scoring 包

scoring ZIP 不带 Harness 顶层目录，内容直接从 `score/` 开始，只提供增量评分材料：

```text
score/
└── tasks/
    └── <task_id>/
        ├── private-scoring/
        │   ├── task_contract.json
        │   └── fixtures/               # 仅 Rubric 实际引用的 eval 文件
        └── .web-e2e-scoring-ready
```

scoring ZIP 不能包含或覆盖 `workspace/`、`PROMPT.md`、`task_manifest.json` 和 `execution_record.json`。

整个批次另生成一份 `<batch_id>__score-web-e2e-skill.zip`。测试人员通过评分智能体的离线 Skill 导入功能安装一次；评分 ZIP 和单题目录都不复制 Skill。后续优化评分逻辑时只需重新分发独立 Skill ZIP，不需要重建每个用例的评分材料。

### 评分前人工合并

Harness 全部执行完成后：

1. 将整个 Harness 根目录压缩备份，并把备份移到根目录外；
2. 将 `execution/tasks/` 整个复制到根目录已有的 `score/` 下，得到 `score/tasks/`；
3. 把对应 scoring ZIP 解压到 Harness 根目录，选择合并同名目录，不能替换整个 `score/`；
4. 每题检查 `workspace/`、`private-scoring/` 和 `.web-e2e-scoring-ready` 同时存在，并确认评分智能体已启用独立安装的 `score-web-e2e` Skill。

合并后的结构为：

```text
<harness-package-root>/
├── execution/tasks/<task_id>/          # 原始执行区，评分期间不修改
└── score/tasks/<task_id>/              # 独立评分副本
    ├── PROMPT.md
    ├── workspace/                      # 候选站点副本
    ├── execution_record.json           # 仅显式启用执行记录时存在
    ├── private-scoring/
    │   ├── task_contract.json
    │   ├── fixtures/
    │   ├── score_input.json            # 评分时生成
    │   ├── task_score.json             # finalize 后生成
    │   └── evidence/
    └── .web-e2e-scoring-ready
```

如果 ZIP 工具不能可靠合并，用户把 scoring ZIP 放在 Harness 根目录同级或根目录内，保持预置 `score/` 没有真实内容，再双击 macOS 或 Windows 封装文件。Python 兜底只依赖标准库：先在临时目录复制 `execution/tasks`，安全解压 scoring ZIP，拒绝路径穿越、符号链接和候选产物覆盖，使用根目录 `manifest.json` 与私有 `task_contract.json` 校验任务范围、身份、哈希和 marker，全部通过后再生成 `score/`。已有 `score/` 仅含空目录或 `.DS_Store`、`.localized`、`Thumbs.db`、`desktop.ini`、`._*` 等系统元数据时允许安全清理并重新生成；存在任何真实文件、评分结果、符号链接或未知特殊文件时仍拒绝覆盖。若本机没有 Python，则回退上述人工 ZIP 流程。

## 路径改写与信息隔离

题目原始 Prompt 中的 `/tmp_workspace` 是 WildClawBench 容器路径。桌面工作空间中统一改写为：

```text
/tmp_workspace/path → ./workspace/path
/tmp_workspace      → ./workspace
```

Expected Behavior 和 Rubric 只存在评分契约中，另加：

```text
/tmp_workspace_eval/path → ./private-scoring/fixtures/path
/tmp_workspace_eval      → ./private-scoring/fixtures
```

原始题目及 SHA-256 留在 WildClawBench 工程审计，不在 Agent 可见目录同时放置 `prompt_original`/`prompt_desktop` 或两份 task contract。这样可避免桌面智能体误选文件，也避免绝对准备机路径进入分发包。

## 执行与评分会话隔离

每题分别创建桌面工作空间和新会话：

- 被评 Harness：`execution/tasks/<task_id>/`；
- 评分 Agent：`score/tasks/<task_id>/`。

不能把 Harness 根目录或整个 `score/tasks/` 选为评分工作空间。新会话只能隔离上下文，不能隔离同一项目下的文件索引；选择单题目录才能确保评分 Agent 看不到其他题目的 Prompt、Rubric、候选产物和评分结果。

评分 Agent 从客户端已安装的 Skill 位置调用脚本，读取当前单题契约，启动 `workspace/` 中的站点，使用自身浏览器工具实际点击、输入、切换、刷新、改变视口或上传文件，并逐 criterion 记录动作、观察、理由和证据。固定脚本只负责初始化评分输入、校验字段和加权计算，不依赖题目目录内的 `.agents/skills/`。

## 状态与计分

默认未采集执行记录时，执行状态为 `not_recorded`；若显式启用执行记录，还可为 `completed`、`execution_error`、`timeout` 或尚未回传的 `pending`。评测状态为 `completed`、`evaluation_error`。`not_recorded + completed` 视为正常完成，不影响评分；执行错误、超时和评测异常仍生成 `task_score.json`，以 0 分进入全部声明用例的总平均分，并保留原始异常类型。

正常完成时 criterion 分数为 0–1，按原始权重计算：

```text
总分 = Σ(criterion_score × criterion_weight) / Σ(criterion_weight) × 100
```

一级和二级维度在题目内按该维度 criterion 权重归一，再跨题目等权平均。若站点无法启动或浏览器不可用，未判断 criterion 保持 `null`，不伪造动作或证据；汇总用的总分和各维度强制为 0。

页面美观度使用独立结构，评分 Agent 填写六维分数和检查项状态，确定性脚本计算总分：

```json
{
  "score": 77.5,
  "max_score": 100,
  "included_in_total": false,
  "status": "completed",
  "rubric_id": "web-aesthetic-v1",
  "primary_dimensions": {
    "render_integrity": 90,
    "layout_hierarchy": 80
  },
  "secondary_dimensions": {
    "v-01": "MET",
    "p-01": "MET"
  },
  "secondary_dimension_scores": {
    "v-01": 100,
    "p-01": 100
  }
}
```

美观度检查点按 `MET=100`、`PARTIAL=50`、`UNMET=0` 固化百分制分值，`NA` 为 `null` 且不进入分子和分母。每个一级维度按所属适用护栏项与加分项等权平均，加分项同样增加分子和分母；再按产品权重计算美观度总分。评分 Agent 只填写检查点状态以及维度理由和证据，不填写一级维度分数。

美观度从本次操作过程选择带标签的代表性截图集合，至少覆盖两个桌面状态和一个窄屏状态，并对整个集合一次统一判断，不逐图给总分后平均。它永远不参与功能总分、得分率或满分率；单独取证失败时记录 `aesthetic.status=evaluation_error` 和空分，不影响功能总分。

## 回传与报告配置

全部单题评分完成后，在不参与单题评分的管理会话中选择 Harness 根目录，调用 `build_submission.mjs`：

- 先关闭站点进程，删除执行区和评分区中由本次 `npm install` 生成、可重新安装的 `node_modules`，以及候选过程意外生成的 `.git`；
- 校验全部 task score、证据路径、批次和题目身份；
- 拒绝 `.env*`、私钥、凭证文件、`node_modules` 和 `.git`；
- 在 Harness 根目录生成唯一 `submission.json`。

测试人员再用本机 ZIP 工具压缩整个 Harness 根目录回传。

模型、Harness 友好名称、推理强度和表格顺序在评测前写入工程内配置，不进入任何分发或回传包：

```text
tools/report/config/web-e2e/<batch_id>.yaml
```

报告脚本至少使用回传中的 `harness_id` 匹配配置；若回传带原始 `model_id`，再使用 `model_id + harness_id` 双键校验。这样测试人员无需为报告映射手工修改分发包 JSON。配置声明的单元与回传范围不一致、或同一 Harness 无法唯一对应模型时停止生成，不能静默混算。

## 报告产物

领导版 Markdown 固定包含：结论、总览、难度等级、一级维度、二级维度。总览表保留模型、Harness、总平均分、四类状态、完成率和资源指标。

Excel 只生成：

1. `站点评测指标`：结果/效率指标、站点一级/二级维度、美观度一级/二级维度；结果表在得分率、满分率后增加美观度总分；
2. `难度对比`；
3. `用例对比明细`。

本方案不修改 `tools/report/scripts/generate_eval_report.py`。两条链路的数据协议和评分有效性边界不同，独立实现可以避免影响 WildClawBench 正式报告；未来如需复用，只抽取纯展示层。

## 一致性与安全门禁

- 全部回传包必须具有相同 `batch_id`、`source_revision` 和有序 `task_ids`。
- 每个回传包只能包含一个 `model@harness`；重复单元拒绝汇总。
- 题目、执行 Workspace 和分发包记录 SHA-256，不同源结果不能混算。
- 启动候选网站会执行不受信任的 npm 脚本；评分环境不得带真实凭证，只监听 `127.0.0.1`。
- Token、成本、请求数等缺失时保留 `null`；只有单元内全部题目提供时才汇总，未知量不能填 0。

## 验收条件

- 一个真实 Web task 和四个 Harness 均能生成 execution/scoring ZIP；execution 包预置空 `score/` 且没有私有评分材料。
- execution 单题目录默认只有 `PROMPT.md` 和 `workspace/`；显式开关才生成 `execution_record.json`，永远不生成单题 `task_manifest.json`。
- scoring ZIP 只从 `score/` 开始，不含候选 Workspace、Prompt、execution record、task manifest 或评分 Skill 副本；批次另有且只有一份可独立安装的评分 Skill ZIP。
- 人工复制 `execution/tasks` 到 `score/` 后可用普通 ZIP 工具合并；Python 双击兜底也能生成相同结构并拒绝覆盖已有评分结果。
- 每个 Agent 可见工作空间只有一个有效 Prompt 或一个有效评分契约；评分 Agent 每题只看到一个用例。
- 正常评分缺项、重项、越界分数或空证据不能 finalize；异常评分允许 criterion 保持未判断但总分和维度必须为 0。
- 美观度正常评分必须完整提供 6 个维度理由、32 个检查点和桌面/窄屏截图证据；一级维度与美观度总分必须由检查点分值确定性推导。
- 回传包可被报告 Skill 读取，批次 YAML 映射和排序生效。
- 两个以上回传包能生成指定章节 Markdown、报告数据 JSON 和恰好三张 Excel Sheet，并通过数值与视觉校验。
