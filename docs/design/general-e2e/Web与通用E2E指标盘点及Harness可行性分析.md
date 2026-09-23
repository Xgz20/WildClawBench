# Web 与通用 E2E 指标盘点及 Harness 可行性分析

核对日期：2026-09-23（Asia/Shanghai）。范围为本地 AstronStudio、WorkBuddy、QwenWork、DoubaoWork 的桌面 E2E 采集与报告。

本文按当前实现更新，不再沿用 2026-09-19 的待开发清单。核对基线为 `feature/astroncode-eval` 的 `555e1ac` 及当时工作区中尚未提交的 QwenWork Token collector/normalizer/profile 修改。后者已有 r22 原生非零样本和采集结果，本文分别标明源码、采集样本和正式报告的证据边界；新提交或发行仍需按实际哈希复核。旧[指标证据清单](e2e-metrics-analysis-evidence-20260919.json)仅用于历史字段与积分线索追溯，不作为本次源码的哈希清单。

## 1. 当前结论

**General E2E 已按标准 WildClawBench 通用评测报告的单元、分组、检查点与逐题对比方式组织指标。** 总览、效率对比、分类、难度、Agent 能力、模态、工具调用、用例对比明细和各单元评分详情均已实现。平均 Token、缓存命中率、原生任务耗时与流程耗时已进入报告，不能再写成待派生指标。

**QwenWork 可以统计 Token。** 当前 macOS 1.2.0 已通过客户端进程开关 `QODERCN_EXPOSE_TOKEN_USAGE=1` 暴露非零原生用量；General 工作区新增解析可在来源、运行时语义和请求/响应对账通过后输出输入、输出、总 Token 与缓存读取。开关关闭、来源未绑定或对账失败的旧/新样本仍保留缺失状态。Cache Write 尚未被验证，不能因日志默认值为 0 就报告“写入 0”。

| 指标 | General 当前实现 | Web 当前实现 |
| --- | --- | --- |
| 任务执行情况 | 已有正常完成、执行错误、评测异常、完成率及有效/未评分数；未输出独立“任务执行异常率” | 已有完成、执行错误、历史超时、未记录、评测异常与完成率；未输出统一异常率 |
| 工具调用数 | 已实现总数和按工具名对比 | 已实现调用次数；DoubaoWork 当前主要提供已知小计 |
| 工具成功率/格式准确率/不确定占比 | 本阶段暂缓；有工具结果事件不等于已有可靠比率 | `format_accuracy` 为兼容字段，不能视为各 Harness 已实现工具成功率 |
| 平均任务积分 | 无统一采集/报告字段；保留来源线索 | 同左；`cost_usd` 不等同于积分 |
| 输入缓存命中率 | 已实现：完整缓存读取总量 / 完整含缓存输入总量 | 有基础字段；当前 Web 聚合器未输出独立缓存命中率 |
| 平均任务 Token | 已实现：完整总 Token / 冻结任务运行数 | 已实现总/输入/输出 Token 的任务均值 |

两种 E2E 使用不同评分与报告入口。General 对齐标准通用报告的组织方式和七维能力映射，但保留 E2E 的有效性、缺失值和双耗时语义；Web 继续使用详细/ArtifactsBench Profile，不能把 General 的新 Sheet 或指标默认算作 Web 已交付。

## 2. 与标准 WildClawBench 通用报告的对齐

标准报告入口为 [`generate_eval_report.py`](../../../tools/report/scripts/generate_eval_report.py)；General 的正式入口为 [`report_general_e2e.py`](../../../tools/report/skills/general-e2e/report-general-e2e/scripts/report_general_e2e.py)，由 `report_views.py`、`report_case_views.py` 和 Excel 渲染器生成同源 JSON、领导版 Markdown、审计 Markdown 与 Excel。General 不通过运行旧 CLI 评分流程来生成这些表。

### 2.1 总览列及口径

当前 General 总览列顺序固定如下，**工具调用数紧跟总请求数**：

| 列 | 当前统计口径 |
| --- | --- |
| 模型@Harness | 使用已验证实际模型和友好 Harness 名称；模型未确认显示“未知模型@Harness”，不把裁判模型或 UI 档位当作被测模型 |
| 总平均分 | `score_status=valid` 的任务分算术平均后乘 100；真实 0 分保留，评测异常和未评分不补零 |
| 用例数 | 当前单元所选 submission 的冻结任务运行数 |
| 正常完成数 | `execution_status=completed` 的数量，独立于评分有效性 |
| 执行错误数 | `execution_status=candidate_error` 的数量 |
| 评测异常数 | 执行 `infrastructure_error` 或评分 `evaluation_error` 的任务并集，同题只计一次 |
| 完成率 | 正常完成数 / 冻结用例数；不是正确率，也不是有效评分率 |
| 有效评分数 / 未评分数 | 分别按 `valid` / `unscored` 统计 |
| 总tokens | 全部所选任务均完整可观测时累加 `total_tokens` |
| 总请求数 | 累加各客户端已验证的 `request_count`；具体是响应数、请求事件数或 usage 推进次数，见第 4 节 |
| 工具调用数 | 累加每题 `call_count`；标准轨迹按 `call_id` 去重，不将 result 再计一次 |
| 任务耗时(s) | 累加 `agent_duration_seconds`，表示原生请求/主 turn 生命周期，包含工具与客户端处理，不是纯模型推理时长 |
| 流程耗时(s) | 累加 `duration_seconds`，按 Driver 记录的发送/执行起点至完成点计时；起止点见原生来源，不包含整个评分和报告阶段 |

General 总览不展示总成本、超时数及暂缓的工具质量比率。标准 CLI 当前还有首 Token 响应时间、成本、多轮与工具质量指标；这些没有全部接入 General，本文不把 CLI 已有列列作 E2E 已支持。CLI 的执行四态归类与 General 的执行/评分双状态也不同，不能仅因列名近似就混用分母。

### 2.2 效率对比及其余 Sheet

效率表紧随总览，列顺序为：

| 模型@Harness | 总 Token | 平均 Token | 普通输入 Token | 缓存命中输入 Token | 缓存写入输入 Token | 输出 Token | 缓存命中率 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 每单元一行 | input + output | 总 Token / 冻结任务运行数 | input − cache read − cache write | Cache Read | Cache Write | output | cache read / input |

“缓存写入输入 Token”指 **Cache Write**，属于输入，不是输出。三类输入都已取得可信数值时才能用减法计算普通输入；当前渲染器没有独立普通输入字段回退。Cache Write 缺失时显示 `-`，普通输入也显示 `-`，但已完整可观测的总 Token、平均 Token 和缓存命中率仍可展示。

| Sheet | 当前实现 |
| --- | --- |
| 分类对比 / 难度对比 / 模态对比 | 各单元百分制总平均分及分组有效均分，保留有效/冻结样本覆盖 |
| Agent能力对比 | 复用标准报告 `checkpoint_capability_map7.yaml`；代码生成、工具调用、数据处理、检索验证、推理规划、内容生成、验证交付七维。先求每题映射检查点均值，再跨任务平均；缺失映射检查点不补零、不用整题总分替代 |
| 工具调用对比 | 按模型@Harness 展示全部工具总量、工具名调用数和明细覆盖；覆盖不足时仅给已知小计 |
| 用例对比明细 | 一题一行，各单元得分并列；含分类、ID、名称、难度、模态、标签、Prompt、预期、规则、检查点、最优单元和最大分差；不足两个有效单元不判最优 |
| 评分详情_<单元> | 每单元独立 Sheet，含冻结题面、规则、Workspace/Skills/Env/Warmup、执行/评分状态、检查点、失分点、判词、错误、Token/请求/工具、双耗时和标准 JSONL 引用 |
| 资源覆盖与异常 | 11 项指标覆盖与缺失状态、维度分母、评测异常/未评分及来源信息 |

共 **9 张公共表 + 每单元 1 张评分详情表**，单单元为 10 Sheet。题面与规则来自经 SHA 校验的冻结评分材料，旧包缺字段不从当前仓库题目补写。领导版 Markdown 不含根因分析；判词、失分点不是另行生成的根因诊断。

## 3. 公共指标模型与聚合公式

### 3.1 11 项基础指标

| 类别 | 字段 | 语义 |
| --- | --- | --- |
| Token | `input_tokens` | 归一化后的输入总量；已纳入的缓存读取/写入不再额外累加 |
| Token | `output_tokens` | 输出 Token；已包含的推理子集不重复累加 |
| Token | `total_tokens` | 输入 + 输出 |
| 缓存 | `cache_read_input_tokens` | 缓存命中输入 Token |
| 缓存 | `cache_creation_input_tokens` | 缓存写入输入 Token；缺少可信来源时为 null |
| 推理 | `reasoning_output_tokens` | 可观测的输出子集，缺少来源时为 null |
| 请求 | `request_count` | 原生模型请求/响应或已核实的 usage 推进计数，需保留 observed/inferred 与来源 |
| 请求 | `request_attempt_count` | HTTP 层尝试计数；当前所核对的采集路径不能完整恢复失败重试 |
| 工具 | `call_count` | 原生调用 ID 去重计数，不将结果事件重复计入 |
| 耗时 | `agent_duration_seconds` | 原生任务生命周期耗时 |
| 耗时 | `duration_seconds` | Driver 记录的任务执行流程耗时 |

Web 将请求字段放在 `usage`、耗时放在 `execution`；General 分为 `usage / requests / tools / timing`，每项附 value/status/basis，并通过 collection 记录来源和覆盖。可出现 `observed / inferred / partial / masked / unverified / unavailable`；Web 另兼容历史 `legacy`。掩码零值不能当作真实零消耗。

### 3.2 已实现的派生统计

```text
General 总平均分 = Σ有效任务分 / 有效评分任务数 × 100
平均任务 Token = Σ所选任务 total_tokens / 冻结任务运行数
输入 Token 缓存命中率 = Σcache_read_input_tokens / Σinput_tokens
普通输入 Token = input_tokens − cache_read_input_tokens − cache_creation_input_tokens
批次墙钟耗时 = 最晚执行完成时间 − 最早执行开始时间
```

- 缓存命中率按 Token 总量加权，不能平均逐题命中率；Cache Write 不属于缓存命中。输入总量为 0 或任一侧覆盖不足时，比率为 null。
- 平均 Token 的分母包含所选范围内的失败/未评分任务；若其用量缺失，全量平均为 null，不用已知小计除以全部任务数，也不只挑成功题。
- 每项指标仅在所有任务完整覆盖时展示总量；另保留 `known_subtotal`、任务覆盖、原生来源覆盖和状态分布。`collection.status=partial` 不意味着每一项都不可用：例如未知 Cache Write 不阻止已核实输入/输出总量参与聚合。
- 任务耗时总和、流程耗时总和与批次墙钟分别统计；执行并发会让总和大于墙钟。队列占槽峰值、原生 turn 重叠峰值是并发验收证据，不是请求数或工具数。
- 当前报告统计**选定回传包/submission 的任务运行**，没有覆盖所有被替换历史 attempt 的消费账本。若要统计“所有重跑花费”，还需独立全 attempt 聚合。
- 用量范围一般是目标主任务/主 turn，不包含 Judge、控制器以及无法绑定的子代理、后台服务或隐藏 HTTP 重试；不能直接当账户计费总量。

原始协议要先归一化。OpenAI Chat Completions 的 `prompt_tokens` 包含其 cached token 子集；Anthropic Messages 的含缓存输入为 `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`。当前已验证的 AstronStudio、WorkBuddy 和 QwenWork 路径中，归一化输入已含缓存读取；不能因字段名类似就再次加缓存。供应商接口差异由 adapter 处理，报告只消费归一化指标。

### 3.3 执行时限与评分边界

题目 `timeout_seconds` 不控制 E2E 被测 Harness 的任务截止时间，也不进入能力评分。当前 General 新建评分编排的 `score_timeout_seconds`、thread `deadline_at` 均为 null，旧参数不再设置任务级评分时限。历史 timeout 状态与旧 deadline 恢复逻辑仍保留用于审计；低层 CDP/UI、HTTP、规则 Worker 和进程清理保护不能解释为题目时长评分。

执行状态、资源完整性和评分有效性分别保留。General 均分只接受 `valid`，未知量为 null；不能扫描日志任意 `error` 或仅凭某个工具失败就认定整个任务异常。最终完成的任务也可能有工具失败后恢复的轨迹。

## 4. 各 Harness 的实际采集能力

| Harness | Token 与缓存 | 请求 / 工具 | 耗时 | 原生积分 |
| --- | --- | --- | --- | --- |
| AstronStudio | Web/General 已有输入、输出、总 Token、缓存读取及可观测推理 Token；Cache Write 未暴露时为 null | General 请求数由 usage 增量与累计量对账推断；工具按原生 item/call 身份统计 | 原生 turn 与执行状态时间 | 未接入正式指标；历史源码有结算字段线索 |
| WorkBuddy | Web/General 已接入原生 session JSONL；输入含缓存读取；Cache Write 和无原始证据的推理量未知 | 模型响应按 `providerData.messageId` 去重；工具按 `callId`，不是“一条用户消息=一次模型调用” | request 原生开始/完成与 Prompt 发送时间，均已支持 | 历史 SQLite 有 `session_usage.credit_json`，尚未映射到正式评测积分 |
| QwenWork | 开关开启且来源/语义/对账通过后可统计 input/output/total/cache read；General 1.2.0 新采集已得到非零结果，Cache Write/推理未知 | 主 turn 的 `model.request.started` ID 和 `tool.requested` ID，响应参与 Token 对账 | `turn.finished.duration_ms` 与 Driver 流程时间 | 尚无正式字段 |
| DoubaoWork | 当前 Web parser 未取得可信 Token/cache；General 尚未接入 | Web 已能从显式 session trajectory 提取去重工具已知小计；完整分母、请求和工具成功率未验证 | 原生完整耗时未验证 | 历史 UI “消耗”仅为线索，单位/归属/结算未确认 |

模型请求数小于工具调用数可以是正常现象：一次模型响应可同时发起多个工具调用。WorkBuddy 以模型响应 ID 计数，QwenWork 以原生请求事件计数，都不要求与工具次数相等；二者也不等于 HTTP 总尝试数。

### 4.1 指标从哪里读取：原生文件、表和归档路径

下面的相对路径使用三个基准，`<…>` 是待替换的身份或目录名，不是固定值：

- **用户目录 H**：macOS 当前用户目录；例如 `H/.qwenworkcn` 对应 `~/.qwenworkcn`。
- **执行单元 U**：解压的 `<batch-id>__<unit-id>/` 根目录；每题独立 Workspace 位于 `U/execution/tasks/<task-id>/workspace/`。
- **正式证据 E**：`U/evidence/tasks/<task-id>/<attempt-id>/`；采集暂存根 C 由 collector 的 `--output-root` 指定，例如 `U/.general-e2e/collection-token/<task-id>/`。下表的 `trace/...` 均相对 C 或正式归档 E，以实际 `trace-index.json` 引用为准。

#### 原生来源与计算分工

| Harness / 场景 | 原生来源（相对 H 的路径示例） | 从此来源计算或核对的指标 | 计算入口（相对仓库根） |
| --- | --- | --- | --- |
| AstronStudio General | `.acode/acode/userdata/state.sqlite` 的只读快照；`provider_runtime_events` 表，按 `thread_id + turn_id` 筛选 | Token/cache/推理量来自 `thread.token-usage.updated.payload.usage` 的 `last*` 与 `total*`；请求数为通过对账的 usage 推进次数；工具数来自 `item.started` 唯一 ID；任务耗时来自 `turn.started/turn.completed` | `tools/report/skills/general-e2e/collect-general-e2e/scripts/archive_astronstudio_trace.mjs::queryBoundNativeTrace` → `collect_astronstudio_resource_metrics.mjs` |
| AstronStudio General | 同一 SQLite 的 `projection_turns / projection_threads / projection_projects`；Driver 的 `automation-state.json` | SQLite 核对 turn 终态、原生身份和 Workspace；Driver 开始/结束时间计算流程耗时 | `tools/report/skills/general-e2e/execute-general-e2e/scripts/lib/astronstudio-state.mjs` 与上述归档/指标脚本 |
| AstronStudio Web | SQLite 反查原生 session/cwd；随后读取 `.acode/sessions/<年>/<月>/<日>/*-<session-id>.jsonl`，或 `.acode/acode/acode-home-overlay/sessions/` 下同类布局 | Web 的资源从原生 rollout JSONL 解析，SQLite 主要承担身份定位；不能把 General 的 SQLite 事件查询与 Web 的 rollout 解析视为同一路实现 | `tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/collect.mjs::collectLocalMetrics` → `tools/report/e2e-shared/resource-metrics/native-parsers.mjs::parseAstron`；`trace-io.mjs::astronSessionRoots` |
| WorkBuddy General/Web | `.workbuddy/projects/<编码工作目录>/<session-id>.jsonl` | 模型响应数、input/output/total/cache read；General 校验 `providerData.usage/rawUsage` 镜像；工具 `function_call` 按 `callId` 去重，并与绑定的 runtime 调用集合核对 | `tools/report/e2e-shared/workbuddy-jsonl-metrics/index.mjs::parseBoundJsonl`；`tools/report/e2e-shared/resource-metrics/native-parsers.mjs::parseWorkBuddy` |
| WorkBuddy General | 客户端 runtime API 的冻结 `runtime_snapshot`，落盘为 attempt 的 `native-binding.json`；不是另一个原生 JSONL | 原生 request 状态、`startedAt/timestamp/completedAt/finishTimestamp`、工具内容和回复用于终态/轨迹核对；与 Prompt 发送时间组合计算双耗时 | `tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/runtime-binding.mjs` → `tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/collector.mjs`；`tools/report/e2e-shared/workbuddy-jsonl-metrics/timing.mjs` |
| WorkBuddy probe / 历史积分线索 | `Library/Application Support/WorkBuddy/codebuddy-sessions.vscdb` 的 `ItemTable`、`session:%`；另有 `.workbuddy/workbuddy.db` 的 `session_usage` 历史线索 | 前者用于会话发现/状态前检；后者 `credit_json` 尚未接入积分指标。当前 Token 与耗时不从数据库文件大小、mtime、WAL 或 `used/size` 快照计算 | `tools/report/skills/general-e2e/execute-general-e2e/drivers/workbuddy/probe.mjs::queryWorkBuddySessions`；积分仅见历史证据清单 |
| QwenWork General/Web | `Library/Application Support/QwenWorkCN/data/agents.db`；`sub_chats / chats / local_projects / projects` | 绑定 session/conversation/sub-chat/project/cwd，检查 `stream_id`、`chats.ext.taskStatus`；**该数据库不是当前 Token 求和源** | `tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/session-state.mjs::QWENWORK_SESSION_QUERY` |
| QwenWork General/Web | `.qwenworkcn/projects/<编码工作目录>/<session-id>.jsonl` | Prompt、assistant transcript 版本、session/cwd 和会话内容 provenance；用于配合原生 segment 确定指标范围，不与 segment 中相同消费重复累加 | `tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/collector.mjs`；Web `drivers/metrics/collect.mjs` |
| QwenWork General/Web | `.qwenworkcn/logs/sessions/<编码工作目录>/<session-id>/segments/<segment>.jsonl` | General 从唯一主 turn 的 `model.request.started` 计请求、`model.response.completed.data` 累加 Token/cache read、`tool.requested` 计工具；`turn.finished` 用量对账和 `duration_ms` 计原生耗时。Web 使用独立 `parseQwen` 及其 Profile | `tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/native-normalizer.mjs::buildQwenStrictResourceMetrics`；Web `tools/report/e2e-shared/resource-metrics/native-parsers.mjs::parseQwen` |
| DoubaoWork Web | `Library/Application Support/DoubaoWork/Default/.doubaowork/agent_mode/workspace/.sessions/<session-id>/agents/<agent-id>/system/trajectory.jsonl` | 按 session + agent + call ID 去重的工具已知小计；不能从这些轨迹推定完整 Token、请求数或原生耗时 | `tools/report/skills/web-e2e/execute-web-e2e/drivers/doubaowork/native-evidence.mjs::parseTrajectoryJsonl/buildNativeEvidence` → `drivers/metrics/parsers.mjs::parseDoubao` |

AstronStudio General 的原始数据来源是 **SQLite 原生事件表**，之后导出成 JSONL 供可复算采集；WorkBuddy 的用量来自 **session JSONL**、原生耗时来自 **runtime 快照**；QwenWork 的用量来自 **session segment 日志**、SQLite 用于会话身份/状态；DoubaoWork 当前只有 **trajectory 的工具小计**。数据库文件或日志存在，不表示其中每种指标都已实现。

#### 采集结果与报告读取路径

| 内容 | 相对路径示例 | 后续如何消费 |
| --- | --- | --- |
| AstronStudio 导出的原始事件 | `E/trace/raw/astronstudio-provider-events.jsonl` | 保留 SQLite sequence/event/thread/turn 身份；指标来源可追溯到具体 JSONL 行 |
| WorkBuddy 原生用量与 runtime 绑定 | `E/trace/raw/workbuddy-session.jsonl`、`E/trace/bindings/01-native-binding.json` | 前者算 Token/模型响应；后者 `runtime_snapshot.request` 算原生耗时，编号以 `trace-index` 为准 |
| QwenWork 原始 transcript/segments | `E/trace/raw/transcript.jsonl`、`E/trace/raw/segments/<segment>.jsonl`、`E/trace/bindings/01-session-binding.json` | transcript/绑定确定归属，segments 求和并对账；r22 实例 segment 文件名为 `2026-09-23T14-03-08-569+08-00-9y7wsf-p61550.jsonl` |
| QwenWork Token 开关和配置证据 | `C/trace/raw/token-config.json`、`C/trace/raw/token-probe.json` | 绑定发送前进程开关、运行时身份和 config digest；正式归档按 trace-index 携带这些来源 |
| General 标准化资源 | `E/resource-metrics.json` | 报告通过 execution record 的 `resource_metrics_path` 读取 `metrics.usage/requests/tools/timing` 及覆盖；不是生成报告时重扫用户的活动数据库 |
| 执行状态 / 标准工具轨迹 | `E/execution-record.json`、`E/trace/trace-index.json`、`E/trace/transcript.jsonl` | 状态计数来自 execution record；按工具名明细来自经过哈希验证的标准 `tool_call`，并与 `call_count` 对账 |
| WorkBuddy 旧任务补采 | `U/evidence/resource-supplements/<task-id>/native.jsonl`、同目录 `resource-metrics.json/supplement.json`；`U/evidence/timing-supplements/<task-id>/` | 新回传包选择后，报告校验补采与旧回执绑定并复算，不改旧评分 |
| 分数 / 分组 / 评分详情 | 所选 `submission.json`、其 `tasks[].score_path` 指向的 `<scoring-attempt>/score.json` 与冻结 `task.md/contract.json`；unit `manifest.json` | 分数和判词来自独立 Judge/规则结果；类别、难度、模态来自冻结任务定义，七维映射来自标准报告数据，均不从客户端 SQLite 推测 |

`E` 是正式 finalizer 发布目录；`.general-e2e/collection*` 是采集工作目录，二者不能仅凭文件名相同视为已完成正式回传。Web 原始来源另记录在采集结果的 `collection.sources` 中，聚合器从 Web submission 的 `usage/tools/execution` 读取；不要求它使用 General 的 `E` 布局。具体路径随配置、平台和 attempt 变化，应跟随冻结 config、trace-index、execution record 和 submission 的相对引用。

### 4.2 WorkBuddy：已实现，不再列为 General 待接入

collector 从 `~/.workbuddy/projects/<编码目录>/<sessionId>.jsonl` 读取与 runtime session/cwd/Prompt/工具集合/最终回复绑定的日志，`providerData.usage` 与 `rawUsage` 对账，镜像 usage 不重复累加。原生时间从冻结 runtime snapshot 读取，不依赖 JSONL 是否存在或 SQLite/日志的更新时间：

| 字段 | 当前起止点 |
| --- | --- |
| `agent_duration_seconds` | `request.startedAt`，缺失回退 `timestamp`，至 `completedAt`，缺失回退 `finishTimestamp` |
| `duration_seconds` | `prompt.sent_at` 至同一原生完成点 |

[五题 Token 补采证据](evidence/workbuddy-jsonl-metrics-20260921/README.md)记录输入 769,118、输出 4,347、总 Token 773,465、缓存读取 703,040、模型响应 21、工具 19；[报告详情证据](evidence/general-report-details-20260921/README.md)对应平均 Token 154,693、缓存命中率 91.4086%。[原生耗时补采](evidence/workbuddy-native-timing-20260921/README.md)已验证任务耗时 306.295 秒、流程耗时 511.448 秒。它们证明指定冻结批次的采集与报告，不能扩成其它运行的数值。

SQLite 的 usage/上下文容量快照不能替代逐响应累积 Token；`.db-wal` 是 SQLite WAL 文件，不是独立的 Token 指标接口。JSONL 缺失且没有可信补采时，模型用量保留 unavailable。

### 4.3 QwenWork：开关、采集准入与实测值

开关必须注入 **QwenWork 客户端进程**，仅在控制终端设置环境变量并不能证明已运行客户端启用。General 已有 `token-launch.mjs`：只在空闲且客户端/CDP 身份确认后处理精确监听进程，使用 `open -na ... --env QODERCN_EXPOSE_TOKEN_USAGE=1 --args ...` 启动，并通过 `token-process.mjs` 回读对应进程的开关。队列的 `--require-token-exposure` 将此要求冻结进运行配置；probe 记录 `app.token_usage_exposure.status=enabled`。

General 新增 Token 采集还检查：

1. 冻结 config/journal/task/attempt/trace root 一致，发送前 probe 的 SHA、时间和精确监听进程开关通过校验。
2. 当前 profile 匹配 macOS 1.2.0、`@ali/qodercn-agent-sdk-next` 1.0.46、目标 assistant transcript 1.1.59 与 runtime SHA。profile 约束的是 Token 字段语义，不是对整个 Harness 执行设置客户端版本白名单。
3. 只选唯一主 turn，模型 request/response ID 集合一致、无重复，Qoder 响应字段为合法计数且不是默认全零，缓存读取不超过输入。
4. 逐响应输入/输出/缓存读取之和与 `turn.finished` 累计量一致；输入已含缓存读取，`total=input+output`。

本次只读复算了 `qwenwork-macos-general-token-smoke-20260923-r22` 的 `01_Productivity_Flow_task_005_support_handoff`，核对 6 份指标来源文件的 SHA/size、11 个请求/响应 ID 及主 turn 汇总：

| 指标 | r22 新采集结果 |
| --- | ---: |
| 输入 Token（含缓存） | 474537 |
| 输出 Token | 9589 |
| 总 Token | 484126 |
| 缓存命中输入 Token | 425379 |
| 输入缓存命中率（由原生总量复算） | 89.6408% |
| 模型请求数 / 工具调用数 | 11 / 14 |
| 任务耗时(s) / 流程耗时(s) | 122.852 / 280.088 |
| 缓存写入输入 / 普通输入 / 推理 Token / HTTP 尝试数 | 未知，不补 0 |

原件为本地调试根下 `qwenwork-macos-general-token-smoke-20260923-r22/worker/qwenwork-macos-general-token-smoke-20260923-r22__qwenwork-macos-x86-64/.general-e2e/collection-token/01_Productivity_Flow_task_005_support_handoff/resource-metrics.json`；调试根为 `/Users/gzx/debug-workspace/e2e-evaluate`，该文件 SHA-256 为 `b1d7882fa697031e31ac4fb4818afffd2bc731c12be441e2fa00b06801a35c0f`。

这是新 Token 采集与对账证据；核对时 collector/normalizer/profile 尚有未提交修改，不能仅据此宣称正式发行、评分回传与 Excel 已全部更新。[r20 五题正式报告](evidence/qwenwork-macos-five3-20260923/README.md)中的 Token/cache 仍为 unavailable，已验证请求 23、工具 21、任务耗时 180.759 秒、流程耗时 617.23 秒。旧包与旧报告不改写；新能力应通过新采集/回传与报告留证。

Web 的 `drivers/metrics/qwen-profile.mjs` 当前登记的是 macOS 1.0.5、Windows 1.0.5.0/1.0.6.0 Profile；不能由 General 新增的 macOS 1.2.0 解析，推定 Web 同版本也已完成采集准入。未命中 Profile、掩码全零或对账不一致时，应分别保留 unavailable/masked/partial/unverified，而不是承诺“开了开关就无条件完整统计”。

## 5. Web 当前报告边界

`aggregate_web_e2e_results.py::unit_summary/resource_summary` 仍按 Web submission 汇总：

| 类别 | 已有内容 |
| --- | --- |
| 结果与状态 | 平均总分/得分率、严格满分率、完成率、执行错误、历史超时、执行未记录和评测异常计数 |
| 详细 Profile | 内容与结构、交互与功能、视觉与布局及细项；审美得分/有效样本数及主次维度 |
| ArtifactsBench | 独立轻量 Profile；不强填详细维度 |
| 资源 | 11 项基础指标的总量/已知小计/覆盖；总/输入/输出 Token 均值、模型请求数、工具次数 |
| 时间 | 平均流程耗时、P50/P90、流程总耗时与智能体耗时总量 |
| 兼容字段 | `average_cost_usd / total_cost_usd / format_accuracy`；缺字段时可为 null，不表示已采到真实费用或完成工具质量判定 |

Web 完成率要求执行 `completed` 或历史 `not_recorded`，且评分 `completed`。General 完成率仅看原生执行完成，二者不能直接互换，更不能统一用 `1 - completion_rate` 代替执行异常率。Web 当前聚合保留对缺失分数取零及发布协议下的异常零分行为；General 保留有效分母。本文只更新事实，不更改任一评分协议。

## 6. 尚未实现或暂缓的指标

以下为后续建议，不属于当前正式报告已交付指标。

| 指标 | 建议口径 | 当前缺口 |
| --- | --- | --- |
| 独立任务执行异常率 | 确认非正常终态的执行尝试数 / 实际开始执行的尝试数；分开候选、Harness、基础设施和人工取消原因 | 当前主要是状态计数与完成率；全 attempt 分母与统一异常归因未落地，终态未知不能填完整比率 |
| 工具调用成功率 | 明确成功调用数 / 全部原生调用尝试数，同时披露 unknown 与终态覆盖 | 本阶段暂缓；协议 completed 不代表业务 success，需各工具错误/退出码语义 |
| 平均任务积分 | 所有被纳入尝试的已结算积分 / 执行尝试数，单位与结算范围明确 | 缺公共字段、attempt 绑定、去重和延迟结算对账 |
| 全 attempt 消费视图 | 同题所有执行尝试的 Token/积分分别汇总 | 当前报告基于所选回传，不汇总所有被替换重跑 |

积分来源保留为历史线索，不能写成已采集指标：

- AstronStudio：历史源码 revision `12d9be52a1745cedd879a724879af2e430a42a53` 的 `TurnBillingReactor` 将 `billingTurnId / chargedPoints / settledAt` 写入 `turn.billing.settled`。不是看到 `credits` 名称就可以使用，仍需目标 turn 的真实结算对账。
- WorkBuddy：历史 5.5.3 安装包 `SqliteConversationUsagePort.persistUsage` 按 `credit[requestId] += usage.cost.amount` 累计至 `session_usage.credit_json`；历史样本约 269.14 仅证明来源存在。必须绑定评测 request/attempt，不能累加多次轮询同一累计快照。
- QwenWork：当前未确认正式任务积分来源。
- DoubaoWork：历史 2.28.12 目标 UI 出现“消耗 0.46”，尚未确认单位、结算范围和精度，不能反推 Token。

后续优先把已实现采集纳入可复核发行和正式报告，再补真实缺项。工具质量比率、平均积分、全 attempt 账本按用户优先级推进；不再把 General 平均 Token、缓存命中率和 WorkBuddy 原生耗时重复列作待开发。各 Harness 的上线状态与故障验收单独见[接续入口](README.md)，不从某个指标可采推导整个客户端生产就绪。

## 7. 可复核依据

| 依据 | 本文对应结论 |
| --- | --- |
| [标准报告入口](../../../tools/report/scripts/generate_eval_report.py)：`write_overview_sheet` 与用例/工具/能力表 | 常规报告的布局与字段；CLI 特有指标的边界 |
| [General 聚合器](../../../tools/report/skills/general-e2e/report-general-e2e/scripts/report_general_e2e.py)：`score_summary/resource_summary/timing_summary` | 有效分母、完整总量、覆盖、批次墙钟 |
| [General 展示表](../../../tools/report/skills/general-e2e/report-general-e2e/scripts/report_views.py)：`build_views/capability_scores/trace_tools` | 总览顺序、效率公式、七维映射和工具次数 |
| [用例与详情表](../../../tools/report/skills/general-e2e/report-general-e2e/scripts/report_case_views.py)：`build_case_views`；[Excel 渲染](../../../tools/report/skills/general-e2e/report-general-e2e/scripts/render_general_e2e_excel.mjs) | 对比明细、单元详情、9+N Sheet |
| [公共原生解析器](../../../tools/report/e2e-shared/resource-metrics/native-parsers.mjs)；[AstronStudio General 采集](../../../tools/report/skills/general-e2e/collect-general-e2e/scripts/collect_astronstudio_resource_metrics.mjs) | Token 归一化、响应/usage 增量计数 |
| [WorkBuddy JSONL 采集与补采](../../../tools/report/skills/general-e2e/collect-general-e2e/drivers/workbuddy/README.md) | 已实现用量和双耗时、冻结补采 |
| [Qwen Token 启动](../../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/token-launch.mjs)、[进程校验](../../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/token-process.mjs)、[队列](../../../tools/report/skills/general-e2e/execute-general-e2e/drivers/qwenwork/batch.mjs) | 开关注入、精确 PID 回读与 `--require-token-exposure` |
| [Qwen General collector](../../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/collector.mjs)：`readFrozenTokenContext`；同目录 `token-profile.mjs`、[native-normalizer.mjs](../../../tools/report/skills/general-e2e/collect-general-e2e/drivers/qwenwork/native-normalizer.mjs)：`buildQwenStrictResourceMetrics` | 工作区新增 Profile、provenance、请求/响应与 turn 对账；核对时含未提交文件 |
| [Web 聚合器](../../../tools/report/skills/web-e2e/report-web-e2e/scripts/aggregate_web_e2e_results.py)；[Web Qwen Profile](../../../tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/qwen-profile.mjs)；[Doubao parser](../../../tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/parsers.mjs)：`parseDoubao` | Web 指标、Profile 范围与 Doubao 工具小计 |
| [General 指标 Schema](../../../eval_general_e2e/contracts/schemas/resource-metrics-v1.schema.json) | 11 项基础字段与状态契约 |

本次验证：`tests.general_e2e.test_general_report_views`、`tests.general_e2e.test_report_general_e2e`、`tests.test_report_web_e2e` 共 38 项通过；另对 r22 现存原始 segment 与采集来源执行只读复算。没有重跑 Harness、Judge 或生成新报告，也没有修改采集/评分源码。
