# Web 与通用 E2E 指标盘点及 Harness 可行性分析

核对日期：2026-09-19。范围为 AstronStudio、WorkBuddy、QwenWork、DoubaoWork 的本地桌面评测；不涉及云电脑执行。

2026-09-21 更新：WorkBuddy General 已接入与 Web 共用的原生 session JSONL 解析，v8 五题模型响应、输入/输出/总 Token 与缓存读取已补采并进入新版报告，详见[指标更正证据](evidence/workbuddy-jsonl-metrics-20260921/README.md)。下文仍保留初始盘点；新增五项指标的统一聚合另按 COMMON-CM01 推进。

交接说明：本文及哈希清单从原 probe worktree 原样保留事实与证据范围，纳入跨平台开发基线供新任务读取。它是下述 revision/文件哈希对应的历史盘点，不是最新客户端或新接口已验证的声明；运行字段以 [统一接入契约](../e2e/端到端自动化评测Harness接入契约.md)、实际 Schema 和新平台样本复核为准。

## 1. 结论

这五项指标适合补充，但需要先统一统计范围和缺失数据处理。当前 Web 和 General 已具备 11 项资源、请求、工具和耗时字段的契约；契约存在不代表每个 Harness 都能采集全部字段。

| 拟补充指标 | Web 当前情况 | General 当前情况 | 判断 |
| --- | --- | --- | --- |
| 任务执行异常率 | 有执行错误、超时、未记录等计数，没有独立统一异常率 | 有执行状态分布，没有独立异常率 | 需统一终态分类、执行次数分母及异常证据 |
| 工具调用成功率 | 只有调用次数；另有格式正确率字段 | 只有调用次数 | 需增加调用结果分类；“执行结束”不等于“成功” |
| 平均任务积分 | 无统一字段；`cost_usd` 为另一种费用字段 | 无积分字段 | AstronStudio、WorkBuddy 有明确接入线索；其余需继续核对 |
| 输入缓存命中率 | 已有输入与缓存读取 Token，没有独立比率 | 同左 | 可派生，但必须先保证分子分母口径一致 |
| 平均任务 Token | 已计算总/输入/输出 Token 均值 | 已汇总总量与覆盖率，尚无均值字段 | 优先复用原始指标；另补全部执行尝试的统计视图 |

资源指标契约和聚合公式由公共实现维护，各 Harness adapter 负责原生字段映射；当前直接在当前工作区分支串行修改，无需分配平台 worktree。COMMON-CM01 的当前待办范围见 [接续入口](README.md)。Web 与 General 的能力评分仍分别按各自任务协议计算。

## 2. 核对范围与证据等级

本次读取原工程当前文件，记录的 HEAD 为 `dd51eb6a4e03080f7a9f96917d06861df6001306`。另一个任务正在修改原工程，因此以附带证据清单的文件 SHA-256 为准确快照依据。

本分析与证据清单写在 `.agents/doubaowork-macos-probe`，分支 `feat/doubaowork-macos-probe`。该 worktree 基线早于上述 HEAD；不能把其中旧版公共代码当成本次盘点对象。本次没有修改采集器、修改原工作分支或新增评测运行。

证据分为三种：

- **当前实现**：Schema、采集器、聚合器和报告渲染器已有对应逻辑。
- **原始样本**：本机已有日志、冻结执行证据或 UI 快照实际出现字段。历史样本不自动证明新版本兼容。
- **候选来源**：源码或安装包提供可接入字段，但尚未完成指定任务的采集、对账与回执验证。

可复核索引：[字段、版本与源文件哈希](e2e-metrics-analysis-evidence-20260919.json)。样本统计只用于验证字段语义，不构成正式评测结果。

## 3. 当前指标清单

### 3.1 两种 E2E 的公共资源指标

| 类别 | 字段 | 现有语义与限制 |
| --- | --- | --- |
| Token | `input_tokens` | 归一化后包含缓存读取的输入 Token |
| Token | `output_tokens` | 输出 Token；若推理 Token 已包含在内，不重复相加 |
| Token | `total_tokens` | 输入加输出；不再额外加缓存或推理子集 |
| 缓存 | `cache_read_input_tokens` | 读取缓存的输入 Token |
| 缓存 | `cache_creation_input_tokens` | 写入缓存的输入 Token；未暴露时为 null |
| 推理 | `reasoning_output_tokens` | 推理输出子集；不是所有客户端都暴露 |
| 请求 | `request_count` | 按原生响应 ID、请求事件或 usage 增量统计；存在 observed/inferred 差异 |
| 请求 | `request_attempt_count` | HTTP 尝试次数契约；当前上述采集路径没有完整重试层证据 |
| 工具 | `call_count` | 按原生调用 ID 去重的调用数量，不把 result 再算一次 |
| 耗时 | `duration_seconds` | 评测执行流程耗时，包括控制与收口开销 |
| 耗时 | `agent_duration_seconds` | 原生任务执行耗时，或明确标记为 inferred 的时间差 |

Web 将请求计数放在 `usage`，耗时放在 `execution`；General 分为 `usage / requests / tools / timing`，每个指标携带 value、status、来源和覆盖信息。概念一致，JSON 结构目前并不完全相同。

公共聚合均保留全量总值、已知小计和覆盖率。全量数据不完整时，总值为 null；状态包括 `observed / inferred / partial / masked / unverified / unavailable`，Web 还兼容历史 `legacy` 数据。`masked` 的原始零值不表示实际零消耗。

当前 Token 范围主要为目标主任务/主 turn。子代理、后台记忆整理、不可见重试等并非全部归入主任务总量，部分仅单列后台操作信息。因此这些 Token 总量不能直接当作账户计费总量。

### 3.2 Web 当前报告指标

| 类别 | 已有指标 |
| --- | --- |
| 规模和状态 | 用例数、完成数、执行错误数、超时数、执行状态未记录数、评分错误数 |
| 汇总表现 | 平均总分/得分率、完成率、严格满分率 |
| 内容与功能 | 自建详细 Profile 的内容与结构、交互与功能、视觉与布局三级主维度及对应细项 |
| 审美 | 审美分、有效样本数；渲染完整性、布局层级、配色排版、组件状态、响应式、调性契合六项主维度，以及检查项达标分布 |
| 资源 | 上述 11 项的总量/小计/覆盖信息；输入、输出、总 Token 平均值；工具总次数、请求总次数 |
| 时间 | 平均流程耗时、P50、P90、流程总耗时、智能体总耗时 |
| 费用与格式 | `average_cost_usd / total_cost_usd` 和 `format_accuracy` 字段；默认可为 null，不代表桌面采集器已取得真实费用或格式判定 |

ArtifactsBench 轻量 Profile 与自建详细 Profile 分开，不能给轻量 Profile 强行填充详细维度。

当前 Web 的 `completion_rate` 条件是执行状态为 `completed` 或历史兼容 `not_recorded`，并且评分完成。因此它不是纯 Harness 正常终止率，不能用 `1 - completion_rate` 作为任务执行异常率。Web 对部分执行/评分异常还存在强制零分逻辑，和 General 的有效分母不同；盘点这些行为不表示建议统一为补零。

Web 的 Token 均值要求当前报告所选任务行全部有可用数值，否则为 null。它没有静默用“有数据的几道题”替代全批次均值。但当前报告输入是选定 submission 的任务行，并非所有历史重试尝试的账本。

### 3.3 General 当前报告指标

| 类别 | 已有指标 |
| --- | --- |
| 规模 | 唯一任务数、任务运行数、unit 数 |
| 分数 | 有效分数量、有效零分数、评分错误数、未评分数、有效分总和、有效分平均值及分母 |
| 执行状态 | `completed / candidate_error / timeout / infrastructure_error / cancelled` 分布 |
| 分组 | unit、任务类别、难度、裁判协议/模型/推理配置分组 |
| 资源 | 11 项字段的全量总值、已知小计、任务覆盖、原生来源覆盖和状态分布 |
| 时间 | 任务流程耗时之和、批次最早开始到最晚结束的壁钟耗时及覆盖率 |
| 溯源 | 逐任务运行、执行/评分状态、所选回传包和输入文件 SHA |

General 仅把 `score_status=valid` 的能力分纳入均值，真实零分保留；`evaluation_error / unscored` 不补零。执行异常的任务仍可能按任务规则形成有效能力分，二者要分别展示。

当前 General 已有明确范围的 AstronStudio、WorkBuddy 和 QwenWork macOS 证据；三者的题量、并发层级和故障覆盖不同，不能合并为同一支持声明。DoubaoWork General 尚未接入。报告的 task run 与所选回传包也不天然覆盖所有被替换的历史 attempt。

## 4. 五项补充指标的建议口径

### 4.1 任务执行异常率

推荐名称为“任务执行异常率”，统计单位是**实际执行尝试**。一题一轮且无重跑时，尝试数等于任务数；同一题重跑必须保留不同 attempt，不得只保留最后成功的一次。

```text
任务执行异常率 = 非正常终止的执行尝试数 / 实际开始执行的尝试数
```

完整率应在统计窗口内的尝试都已确认终态后给出。正在运行、终态未知或日志缺失时，保留分母清单和已知异常数，全量比率为 null；可另给“已确认终态子集异常率”，同时标明覆盖数/已开始数。未开始的计划任务不进入执行异常分母，应单列“未启动/准备失败”。执行开始以统一的 attempt 开始事件为准，另记录是否已发送给 Harness，以定位故障发生阶段。

建议异常计数按原因展开：Harness/候选执行错误、超时、评测基础设施故障、取消。取消再区分人工取消与异常中断。主“非正常终止率”可以包含全部非正常终态，但跨 Harness 归因时须同时展示这些分项，不能把评分器故障、人为取消或控制器故障都归因于 Harness。

红色图标可以作为证据入口，但应绑定目标会话、turn 和观察时间，并核对它是否对应最终终态。不能扫描日志里任意 `error` 单词来判异常：它可能来自被读取的文件、失败测试、工具返回或已恢复的重试。

建议另列“过程异常发生率”：执行过程中出现过异常事件的尝试数/尝试数。它与最终异常率分别回答“是否遇到异常”和“是否异常结束”。

**实证反例**：现有 AstronStudio `g2-03/s1` 原始证据中，两次命令工具以 `failed`、exitCode 1/2 结束，后续调用恢复成功，最终 `turn.completed.payload.state=completed`。这些调用属于工具失败，不能直接把该任务算为异常终止。

### 4.2 工具调用成功率

用户给出的“执行完成数/调用总数”更准确的名称是“工具调用完成率”。建议同时保留：

```text
工具调用成功率 = 明确成功的调用数 / 全部原生工具调用尝试数
工具终态覆盖率 = 已确认终态的调用数 / 全部原生工具调用尝试数
```

调用结局至少区分 `success / error / cancelled / timeout / unknown`。收到 result 或状态写着 `completed`，只证明协议结束，仍需检查工具的结构化错误、退出码及该工具定义的成功条件。非零退出码也需按工具语义判断，例如检索命令“没有匹配”不必一律归为工具故障。

**实证反例**：WorkBuddy 本机一个历史会话有 173 条 `function_call_result`，全部 `status=completed`，但其中一条 Write 的 `providerData.toolResult.error` 非空。直接按 completed 算成功会把已知业务错误计成成功；这里也不能据此断言其余 172 条都成功。

去重键应包含 Harness、session/turn、原生 call ID。重复落盘的同一调用只算一次；重新发起且 ID 不同的重试各算一次；孤立 result 不算新调用。主代理、子代理、后台工具应分别标记范围，不能只扩充分子或分母一侧。

存在未知结局时，正式全量成功率为 null；可报告已知成功数、已知失败数、未知数与覆盖率，以及明确标为下界的“已知成功数/全部调用数”。完全无工具调用时比率为 null/不适用，不填 100%。成功执行工具也不代表模型选对工具或完成了任务，能力评分继续独立。

### 4.3 平均任务积分

```text
平均每次执行积分 = 所有执行尝试的已结算积分总量 / 执行尝试数
```

每次失败、超时、取消或重跑实际消耗的积分都应保留。没有发生扣费与没有取得扣费记录不同；只有明确无收费结算证据才能记 0。结算尚未到账时为 pending/unavailable，不能在模型结束瞬间把积分冻结成零。

建议记录 `amount / unit / source / settlement_status / settlement_id / billing_scope`。账户余额、预估积分、定价倍率、请求扣费增量、会话累计积分需要分别识别。累计值只能取指定范围的最终快照或经核实的差值，不能对多次轮询快照求和。

不同 Harness 的积分定价、赠送额度、工具收费与模型倍率不同。积分可用于各产品内成本比较，但不能跨产品直接按数值排“谁更便宜”。`cost_usd` 也不能替代原生积分；基于 Token 和价格表估算的费用需另列为估算。

### 4.4 输入缓存命中率

用户公式合理，建议准确命名为“**输入 Token 缓存命中率**”：

```text
输入 Token 缓存命中率 = Σ缓存读取输入 Token / Σ全部输入 Token（含缓存）
```

这是按 Token 加权的比例，不能简单平均每个任务的命中率。缓存写入不属于缓存命中。另有“请求缓存命中率”（至少命中一部分缓存的请求数/请求数），它是另一个指标，不能混用。

供应商原始字段需要归一化：

| 原始协议/来源 | 分母 |
| --- | --- |
| OpenAI Chat Completions | `prompt_tokens`；分子为 `prompt_tokens_details.cached_tokens` |
| Anthropic Messages | `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`；按该协议三类输入相加 |
| 当前已验证的 AstronStudio、WorkBuddy、QwenWork 归一化结果 | `input_tokens` 已含缓存读取，不能再加一次 `cache_read_input_tokens` |

已读取 OpenAI 官方 SDK 的 `CompletionUsage / PromptTokensDetails` 定义，以及 Anthropic 官方 SDK 和 Prompt Caching 示例。Anthropic 示例中同一约 187,364 Token 的输入，在缓存命中时为 `input_tokens=3`、`cache_read_input_tokens=187361`；因此直接拿缓存读取除以原始 `input_tokens` 会得到不合理的大于 100% 的比例。Qwen 字段名虽相似，当前验证的适配器语义却是缓存已包含在 input 中，不能套用 Anthropic 加法。

分子分母必须来自相同请求/任务范围。任意一侧数据缺失，不能用不同覆盖子集的总和计算。全量不完整时为 null，可另给成对完整样本的比率及覆盖；输入总量为 0 时为 null。缓存冷热、任务顺序、并发、TTL、公共系统提示和重复运行会影响该指标，比较时应记录这些条件。它不等于任务质量，也不直接等于费用节省率。

### 4.5 平均任务 Token

```text
平均每次执行 Token = Σ执行尝试的归一化 total_tokens / 执行尝试数
```

同时展示平均输入、平均输出 Token；缓存与推理子集单列，不重复加到 total。失败执行消耗的 Token 也保留，不能只平均成功任务。

Web 已有按当前任务行计算的三种 Token 均值；General 可以在已有完整总量上派生。若需要用户所说的“所有执行次数”，两者都应增加全 attempt 消耗视图，避免重跑后旧消耗随 submission 替换而消失。还可另列“每个唯一任务的全流程 Token”，但必须与“每次尝试平均 Token”区分。

缺失数据时正式均值为 null，并显示已知小计与覆盖率。可额外给明确标注的完整样本均值，不能用已知小计除以全体任务数。跨模型 tokenizer 不同，Token 数也不完全等同于相同信息量。

## 5. 四个 Harness 的可行性

表中“可扩展”表示已有足够明确的数据来源，尚不表示新指标已接入正式报告。

| Harness | 任务异常率 | 工具成功率 | 平均积分 | 缓存命中率 / 平均 Token |
| --- | --- | --- | --- | --- |
| AstronStudio | 可扩展：原生 turn 终态与执行回执 | 可扩展：item ID、状态、exitCode；需覆盖各工具类型 | 源码候选明确：`turn.billing.settled`、`chargedPoints`；本次未完成运行时对账 | Web/General 已有基础采集，满足覆盖条件后可派生 |
| WorkBuddy | 可扩展：驱动终态与原生会话；仍需异常样本验收 | 可扩展：callId、result、结构化 error；completed 不够 | 可行性高：安装包累加逻辑和非空 `session_usage.credit_json` 均已发现 | Web 已有归一化采集；General 需接入共享能力 |
| QwenWork | macOS 1.0.6 已验证正常终态、数据库 status/taskStatus 与 `turn.finished.reason`；异常样本仍待扩充 | 已接入 `tool.requested`、`tool.execution.finished` 和 shell exit_code；本次单题为零工具 | 当前证据未确认任务扣积分字段，保留未知 | macOS 1.0.6 单题请求数和双耗时已验证；Token/cache 语义未验证，保持 unavailable |
| DoubaoWork | 目前仅本地任务 UI 终态；需补原生终态与故障证据 | 未验证稳定调用 ID、工具结果及错误语义 | 保存的目标会话 UI 出现“消耗 0.46”；单位、精度、归属和结算时间未验证 | 尚未验证本地原生 usage 来源；不能从“消耗”反推 Token |

### AstronStudio

冻结样本已证明 `thread.token-usage.updated`、`item.started / item.completed`、`turn.started / turn.completed` 可用于资源和执行分析。

积分字段不能直接认定为 `credits`。本地桌面源码 `12d9be52a1745cedd879a724879af2e430a42a53` 中，`TurnBillingReactor.settledBillingActivityCommand` 把 `billingTurnId / chargedPoints / settledAt` 写入 `turn.billing.settled`；前端按 turn ID 读取 `chargedPoints` 展示本轮积分。结算契约还有 `rated_points / charged_points`，账户的余额或通用 provider credits 不是同一概念。

后续应按目标 root turn/billingTurnId 读取最终结算结果，以结算 ID 去重，核对 billed scope 是否包含子代理等额外消耗。本次对 `~/.acode/acode/userdata/state.sqlite` 的只读访问遇到 database is locked，未打断客户端或绕过锁；因此结论仍为源码级可行，不能宣称已在已安装版本取得真实积分。

### WorkBuddy

安装版本 5.5.3。`app.asar/main/node.js` 中 `SqliteConversationUsagePort.persistUsage` 明确执行：

```text
credit[requestId] = (credit[requestId] ?? 0) + usage.cost.amount
```

数据库 `session_usage.credit_json` 是按 requestId 累加的字典。本次历史会话读取到约 269.14 的非空记录，证明本机确有此数据，不能把它当作正式评测任务的平均积分。

安装包 CLI 的用量发布逻辑还有模型、子代理/团队、生成工具等积分来源，所以只加主代理 Token 费用可能对不上积分。正式接入需映射 `conversationRequestId / requestId` 到执行 attempt，等待完整结算并核对 UI；不要每轮轮询都把累计字典再次相加。`session_usage.used / size` 为用量/上下文容量快照，不能代替累积任务 Token。

### QwenWork

现有 2026-09-16 的资源冒烟日志包含 `tool.requested`、`tool.execution.finished`、`tool.shell.finished`、`model.response.completed`、`turn.finished`；成功工具的 status 为 success，shell 有 exit_code，正常 turn 的 reason 为 end_turn。消息数据库样本还有 completed/cancelled 等状态。读取到的 `session_event_log` 没有记录，因此应优先沿现有 `.qwenworkcn` 会话与 segment 日志采集。

QwenWorkCN 1.0.6 / macOS x86_64 已完成一次正式单题采集：原生请求数 1、工具调用数 0、原生 turn 耗时 8.097 秒、流程耗时 111.967 秒。当前日志没有足够证据验证 Token/cache 字段公式，因此 input/output/total/cache read/cache write 均保持 `null/unavailable`，并保留 model-response 覆盖分母。旧 macOS 1.0.5 和 Windows 1.0.6.0 Profile 都不能替代当前运行时语义验证；原始默认零值、`QODERCN_EXPOSE_TOKEN_USAGE=1` 或版本号相近仍不够。

### DoubaoWork

本地 2.28.12 的 CDP + Playwright 控制已经完成单题站点冒烟；本次没有新增执行。既有会话 `38442617777983746` 的保存快照含“消耗 0.46”，仅证明 UI 有消费数值。当前主进程日志中与该会话匹配的记录主要是导航等信息，不能据此恢复完整工具轨迹或 Token。

后续先验证消费明细的单位、对应 turn/attempt、结算时点和可持久化来源，再决定是否纳入积分。若长期只能读到四舍五入的 UI 值，应明确记录 UI 来源和精度；没有真实 Token 字段时，保留 unavailable。

## 6. 落地顺序与并行边界

1. **公共口径先定**：冻结 attempt 主键、执行终态、工具结果分类、资源 scope、积分结算记录和 null/coverage 契约。补平均 Token 与缓存命中率的聚合，不改变评分分母。
2. **接入可验证来源**：AstronStudio 与 WorkBuddy 继续补终态异常、工具结果及积分；QwenWork 已接入 macOS 1.0.6 单题的请求/工具/双耗时，下一步补异常样本和 Token 语义验证。
3. **DoubaoWork 补证据链**：原生任务身份、终态、工具结果、消费与 usage。若部分来源暂缺，其余指标仍可独立接入。
4. **固定回归样本**：正常完成、工具失败后恢复、最终错误、超时、取消、重复事件、未知终态、零工具、真实零值与掩码零值。积分另验延迟结算和重复快照；缓存验包含/不包含缓存的两种协议。已有样本可先做解析验收，最终仍需目标客户端真实运行对账。

当前按 Harness 串行推进并直接在工作区分支修改，公共 Schema、原生解析接口和报告聚合随同一基线前进。后续若重新启用并行，平台专属 adapter/fixture 可以隔离到 `.agents/` worktree，但公共公式只由控制基线单点修改，避免分母、去重和缺失值语义漂移。

## 7. 主要依据

仓库路径均相对本次读取的原工程根，准确内容以证据清单中的 SHA 为准：

- `tools/report/skills/web-e2e/execute-web-e2e/references/resource-metrics.md`
- `tools/report/e2e-shared/resource-metrics/native-parsers.mjs`
- `tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/qwen-profile.mjs`
- `tools/report/skills/web-e2e/report-web-e2e/scripts/aggregate_web_e2e_results.py`：`resource_summary / complete_values / unit_summary`
- `tools/report/skills/web-e2e/score-web-e2e/scripts/finalize_score.mjs`：费用和格式字段默认值、评分状态处理
- `eval_general_e2e/contracts/schemas/resource-metrics-v1.schema.json`
- `eval_general_e2e/contracts/schemas/execution-record-v1.schema.json`
- `tools/report/skills/general-e2e/report-general-e2e/scripts/report_general_e2e.py`：`score_summary / resource_summary / timing_summary`
- `docs/design/general-e2e/evidence/g2-03/s1/raw/astronstudio-provider-events.jsonl`
- AstronStudio 桌面源码：`apps/server/src/turnBilling/TurnBillingReactor.ts`、`TurnBillingOutbox.ts`、`apps/web/src/components/chat/turnBillingPresentation.ts`
- [OpenAI 官方 SDK：用量及缓存字段](https://github.com/openai/openai-python/blob/main/src/openai/types/completion_usage.py)
- [Anthropic 官方 SDK：Usage](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/usage.py)
- [Anthropic 官方 Prompt Caching 示例](https://github.com/anthropics/anthropic-cookbook/blob/main/misc/prompt_caching.ipynb)

官方文档站点本次分别返回访问限制/地区页面，因此外部字段核对采用上述成功读取的官方 GitHub 源码和示例；示例时间与定价不作为本报告的评测性能或成本结论。
