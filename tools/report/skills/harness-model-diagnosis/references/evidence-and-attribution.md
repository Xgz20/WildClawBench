# 证据与归因规则

## 工具问题：沿一次真实调用核验

按“本次请求中实际可见 schema → 模型输出的工具名/参数 → Harness 分派或拦截 → 工具结果是否回注 → 后续恢复 → 交付与评分”定位。配置里声明 MCP、发现返回 schema、下一请求注入 schema、实际调用成功，是不同证据等级。不能用当前工具列表替代失败请求当时的列表。

| 现象 | 应核对什么 | 可以得出的结论 |
| --- | --- | --- |
| 参数/协议错误 | 本次 schema 声明 `cmd`，模型却传 `command`；返回错误与重试 | 首先是 L1b 模型协议遵循错误；若实际 schema 自相矛盾或适配破坏参数，另证 L2 |
| 工具暴露与能力不匹配 | 会话模型实际能力、schema 注册条件、运行时拒绝及下一轮行为 | 对不支持图片的会话仍暴露 `view_image`，可属 L2 能力感知/工具暴露问题；调用时拒绝可能正是正确安全守卫，不必等合法调用被错误执行才承认 L2 |
| 执行/回注故障 | 合法调用的分派、权限、工具进程、网络响应及结果回注 | Harness 错分派/丢失结果属 L2；外部服务或环境失败属 L3；需追到失败层，不能见报错就归模型 |
| 接口简化候选 | 相近工具 schema、错误率/分母、恢复路径、不可替代能力 | 同时有 `bash` 和 `exec_command` 可提出简化实验；数量为二不等于 bug，CC/DSH 单工具成功不证明删除另一工具必然更好 |

讨论只保留 bash 时，检查工作目录、环境变量、超时、流式输出、异步会话/续读、取消、输出截断、sandbox/审批、平台差异是否等价。可以建议保留底层执行能力而统一模型入口；不要未经核验就建议删掉底层实现。默认只提出方案，不修改目标 Harness。

“产生一次错误并恢复”“增加请求/耗时”“因此失去某检查点分数”分开陈述。满分任务也可能有可优化试错，但不得计入已证明的失分根因；额外 token/耗时需要调用级计量，不把总差额全部算在工具错误头上。

## 其他根因边界

- 提前结束：确认任务需要工具、未完成交付、最后模型响应不再发必要调用；`SHORT_TRANSCRIPT`、`QUICK_EXIT_SUSPICIOUS`、`completed`、零工具调用只是筛查信号。API 错误/超时与模型推理后直接终止分开计数。读 Skill 后停止，不自动证明 Skill 冲突或 MCP 未注入。
- 共性失分：读历史契约、原始产物与评分器；共同零分可能来自模型共同违约或评分器漏识别。不能拿 HEAD 的评分器解释历史分数。严格 YAML/长度违规不因内容不错而洗成评分错误；安全禁令对象不清时不把执行安全副本说成执行恶意代码。
- 分层：`L1a` 知识/事实，`L1b` 规划/推理/指令或工具协议遵循，`L2` Harness，`L3` 外部服务/环境，`L4` 评测框架/契约/评分，`uncertain` 未定。
- 强度：`confirmed` 已有直接证据，`probable` 重要促成因素但仍有替代解释，`hypothesis` 待实验，`unresolved` 证据不足。Harness 能做兜底不代表根因属于 Harness；固定一个模型跨 Harness 重复，也不能证明其他模型一定更好。
- 分母：区分受影响任务、run、调用及实际检查数量；同一任务的多个问题不能相加为额外任务或重复总失分。异常记录条数不能直接作为失败任务数。

## 可选源码核验

当用户提供源码或询问机制是否属实时，再开启源码核验：

1. 记录路径、Git commit、branch、dirty、运行版本/镜像；`--source-dir` 只自动记录静态快照，不自动验证机制。脏文件还应记录相关文件哈希或局部 diff 边界。
2. 找注册条件、模型能力来源、请求序列化/适配、执行守卫、结果回注的具体符号与行号，明确分支触发条件。报告同时保留运行侧 `run_id` 和源码侧 commit/符号。
3. 对照评测版本与代码提交/镜像构建信息。若部署映射未知，只说“本地此提交存在该逻辑，运行轨迹与之吻合”，不宣称历史二进制已被源码证明。
4. 把静态可达、单元测试通过、线上实际触发、干预后改善分开。发现反例（同配置成功调用、恢复满分）要用来收窄结论，不隐藏。

## 问题账本

文件顶层为 `{"findings": [...]}`。每项示例：

```json
{
  "id": "H-01",
  "target": {"kind": "harness", "id": "astroncode"},
  "title": "工具入口简化候选",
  "finding_type": "optimization_candidate",
  "layer": "L2",
  "confidence": "hypothesis",
  "observation": "本次 schema、错误和恢复行为的具体事实",
  "scope": {"affected_tasks": 1, "examined_tasks": 60, "affected_runs": 1, "examined_runs": 60},
  "task_ids": ["完整任务ID"],
  "impact": {"observed": "已测得影响及单位", "causal": "已有证据证明的机制", "not_proven": "尚不能归因的失分/token/耗时"},
  "evidence": [{"evidence_type": "runtime", "unit": "model@harness", "task_id": "完整任务ID", "run_id": "实际run目录名", "call_id": null, "request_id": null, "source": "/absolute/run/path/agent_interaction.jsonl", "line": 17, "locator": "event 17 / error", "excerpt": "最小必要脱敏摘录"}],
  "counterevidence": ["同模型成功路径、恢复满分或替代解释"],
  "recommendation": "建议的改进或实验",
  "validation": "固定模型/API/参数/用例/版本，比较什么指标，何为通过"
}
```

`finding_type` 可为 `confirmed_problem`、`optimization_candidate`、`unresolved`。没有反例证据时如实写“未检索到/未深读”，不编造；只检查一个失败任务不能声称扫过 60 个任务的语义轨迹。

每条运行证据必须准确匹配 profile 中的 `unit + task_id + run_id`，路径必须在该 run 下；`call_id`/request ID 可得时填写，未记录则 null，不能把事件序号伪装成 request ID。事件序号/JSON Pointer/时间戳放 `locator`，`line` 若提供必须是实际文本行号。

源码证据使用 `evidence_type: source_code`，增加 `commit`、`symbol`，保留绝对 `source`、`locator`、`excerpt`。源码证据不能替代至少一条运行证据。当前源码有潜在风险但无运行触发时，标明未验证，不列作本轮已确认的运行失败。

证据链接标签采用 `Harness版本@模型｜完整任务ID或简称｜文件名:定位`，另有独立 `run_id` 列。允许可解析的相对链接，但不能只显示光秃文件名。摘录不含凭证、请求头或无关用户数据；脚本做结构校验，不保证自动识别所有敏感信息，交付前人工检查。

研发排查项应包含复现条件、调用链、源码入口（有则给）、用户可见影响、成功反例、修复候选及验收计划。统计相关性、机制证据和干预证据不可混写。
