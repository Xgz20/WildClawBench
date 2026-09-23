# Web 站点端到端自动化评测指标说明

更新：2026-09-23。本文定义 Web Profile、分数、状态、资源和报告聚合。轨迹来源/采集分析见[技术方案](Web站点端到端自动化评测技术方案.md#3-轨迹采集分析)，接入步骤与平台支持进度见[统一契约](../e2e/端到端自动化评测Harness接入契约.md#integration-progress)。

## 1. Profile 与任务分数

| Profile | Agent 输入 | 确定性输出与展示 |
| --- | --- | --- |
| web-e2e-detailed-v1 | 各 criterion 的 0–1 分、理由、动作与证据；独立 aesthetic | 功能总分和维度按 contract 权重归一至 0–100；独立美观度不并入功能总分 |
| artifactsbench-web-v1 | 原始 criterion 的 0–10 整数 raw_score | score=raw_score/10，再按原权重归一总分至 0–100；不生成独立美观度或详细维度 |

每个 criterion 必须恰好出现一次，不改 ID/权重/原始锚点。精确 JSON、证据类型和兼容默认以[scoring-contract](../../../tools/report/skills/web-e2e/score-web-e2e/references/scoring-contract.md)为准。

详细 Profile 美观度使用既定 6 个维度、32 个检查项，MET/PARTIAL/UNMET/NA 对应 100/50/0/null；NA 不进分母，脚本推导维度及总分。至少两张桌面和一张窄屏截图，检查项引用实际截图标签；完整取证规则见[aesthetic-scoring](../../../tools/report/skills/web-e2e/score-web-e2e/references/aesthetic-scoring.md)。功能分和美观度分别保留 completed/evaluation_error。

## 2. 执行状态、评分异常与分母

Web 的已发布协议在执行错误、历史 timeout 或 evaluation_error 时保留状态并将功能总分记为 0。聚合器按 submission 中全部任务的 total_score 求均值，不能直接套用 General 只对 valid 求均值的口径。跨场景比较必须披露协议与异常数；不能把基础设施异常导致的零总分解释为真实能力零分。

| 报告指标 | 当前含义 |
| --- | --- |
| 总平均分 / 得分率 | submission 所列任务总分的平均值，0–100 |
| 严格满分率 | total_score==100 的任务数 / 全部任务数 |
| 完成率 | execution 为 completed（兼容旧 not_recorded）且 evaluation completed 的任务数 / 全部任务数 |
| 执行错误 / 历史超时 / 未记录 | 分别按 execution.status 计数 |
| 评测异常 | 可评分执行状态下 evaluation_error 的数量，独立展示 |
| 美观度均分 / 样本数 | 仅详细 Profile，基于完成且有值的独立美观度结果 |

题目 timeout 元数据不作为当前被测 Harness 的执行期限或能力评分项；历史状态继续可读。低层 UI、采集、评分和进程清理的基础设施保护不能混同题目时长。

## 3. 资源字段与状态

| 分组 | 字段 | 语义 |
| --- | --- | --- |
| usage | input_tokens / output_tokens / total_tokens | 归一化输入、输出及两者之和；已包含的缓存/推理子集不再加一次 |
| usage | cache_read_input_tokens / cache_creation_input_tokens / reasoning_output_tokens | 缓存读取、缓存写入、推理子集；无可信来源为 null |
| usage | request_count / request_attempt_count | 原生请求/持久化响应/明确推导计数；HTTP 尝试数单列，不能用前者冒充 |
| tools | call_count | 按原生 call ID 去重，result 不再计一次 |
| execution | agent_duration_seconds | 原生任务耗时或有明确依据的推导 |
| execution | duration_seconds | 控制执行流程壁钟，包括 UI 与终态收口 |
| usage.collection | status / basis / sources / coverage / known_subtotals | 来源、哈希、字段可用性与缺失分母；并非单个布尔“采集成功” |

状态为 observed、inferred、partial、masked、unverified、unavailable；历史无 collection 的记录按 legacy 兼容。报告完整总量只使用完整可观测值；partial/隐藏/未验证量进入已知小计和覆盖，不进入完整总量。真实明确零值可保留 0，未知绝不补零。

## 4. Harness 字段映射与 Profile 边界

| Harness | Token/缓存 | 请求 / 工具 | 原生耗时 |
| --- | --- | --- | --- |
| AstronStudio | 原生目标 turn 累计量扣既往基线；读取是输入子集，写入未知 | 对账的 usage 推进次数（inferred）/唯一 call ID | task_started → task_complete |
| WorkBuddy | messageId 去重的原生 usage；缓存读取为输入子集 | 唯一持久化响应 ID /唯一 callId | Web 消息时间推导，标 inferred；不能套用 General runtime snapshot 的观测等级 |
| QwenWork | 暴露开关 + 已验 runtime Profile + request/response/主 turn 对账；默认隐藏值不可用 | model.request.started / tool.requested 主 turn ID | SDK turn.finished.duration_ms |
| DoubaoWork | 当前没有可信完整用量 | 已绑定 trajectory 的工具 known subtotal；覆盖分母未知时不是完整总量 | 未验证，保留 null |

Qwen Web Profile 登记 macOS 1.0.5、Windows 1.0.5.0/1.0.6.0 的指定 SDK/transcript/runtime 语义；以[当前 Profile 源码](../../../tools/report/skills/web-e2e/execute-web-e2e/drivers/metrics/qwen-profile.mjs)为准。General 的 macOS 1.2.0 校验结果不直接升级 Web。开关在新 Qwen 客户端进程启动时注入，不能靠控制终端改环境影响旧进程；旧 masked 样本不回填。

已验 Qoder 口径 input 包含 cache read，total=input+output。逐 request ID 去重，要求请求/响应集合、逐项非零 usage 与唯一主 turn 终值一致；cache read 不得超过 input。Cache Write 日志默认 0 未经验证，仍为 null；请求、工具、耗时可独立有值，Token 缺失不把这些字段一起抹掉。

## 5. 聚合与报告

完整资源总量要求所选任务字段全部有效；同时输出 known_subtotal、覆盖任务数/总任务数、partial/inferred 数。平均输入/输出/总 Token、流程耗时和耗时分位数使用报告器认可的完整值集合，覆盖不足保持空。主任务之外的后台、子代理、HTTP 重试、Judge 与控制器用量不混入被测主任务。

输入缓存命中率在 Web 当前聚合器中尚无独立展示字段；不把 General 的加权缓存命中率 Sheet 当作 Web 已实现。cost_usd 不等于积分；平均任务积分、统一异常率、工具成功率/格式准确率/不确定比例没有可靠统一口径时保持未实现，不能从次数推断。

详细 Profile 的报告保留一级/二级维度与独立美观度；ArtifactsBench 保留原始 Profile 的总分、难度等轻量结果。两种 Profile 的 submission 和 report-config 必须一致，不能混合汇总。

源码依据：[aggregate_web_e2e_results.py](../../../tools/report/skills/web-e2e/report-web-e2e/scripts/aggregate_web_e2e_results.py) 的 resource_summary/unit_summary、[finalize_score.mjs](../../../tools/report/skills/web-e2e/score-web-e2e/scripts/finalize_score.mjs)、[Web 采集接口](../../../tools/report/skills/web-e2e/execute-web-e2e/references/resource-metrics.md)。历史 Windows 三 Harness Token 门禁、Qwen 自动开关样本和对应 SHA 见[Web 验收档案](../e2e/archive/web/生产验收历史-20260923.md)；它们只证明各自冻结身份，不代表所有当前安装均已观测。
