# 每题资源指标采集

采集发生在 Driver 判定执行终态后、写入 `execution_record.json` 时；只读本机原生会话数据，不调用模型、不修改客户端数据库、不读取认证配置。评分 Agent 只透传执行记录，不能估算 Token 或把评分自身消耗记到被评 Harness。

## 支持范围和口径

| Harness | 输入 / 输出 / 总 Token | 缓存 | 模型请求数 | 工具次数 | 智能体耗时 |
| --- | --- | --- | --- | --- | --- |
| AstronStudio | 原生目标 turn 累计值减前轮基线 | 读取量是输入子集；写入量未知 | 推导值：与增量 usage 对账的累计快照推进次数 | 唯一原生 call_id | task_started 到 task_complete |
| WorkBuddy | 原生 messageId 去重的 usage | 读取量是输入子集；写入量未知 | 唯一已持久化响应 ID 数 | 唯一 callId，不含 result | 首个人工消息到最终助手消息，标记 inferred |
| QwenWork | 默认隐藏；已验运行时中逐响应非零 usage 与主 turn 终值对账后可用；未知组合保留 unverified | 读取量是输入子集；写入量未知 | 主 turn 的 model.request.started ID 数 | 主 turn 的 tool.requested ID 数 | SDK turn.finished.duration_ms |

这是主任务口径，**不等于账单总量**。后台记忆整理单列在 `background_operations`，未关联子智能体、客户端后台服务和不可见 HTTP 重试排除。各 Harness 的模型请求数来源并不完全相同，不能统一声称是底层 HTTP 请求次数；`request_attempt_count` 没有可靠原生数据时为 null。费用、工具格式准确率不从次数推断。

输入 Token 已包含缓存读取部分；推理输出是输出 Token 子集，汇总时均不能重复相加。不能跨 provider 仅凭字段名套用缓存公式。未采集到的字段保留 null，不补 0；真实的明确零值可以为 0。

当前实现只适配以上三个 Driver。其他 Harness 以及缺失、损坏、无法唯一关联或多人工轮次会话返回 unavailable，不从 UI 标题或相近时间猜测。AstronStudio 通过桌面 thread/turn → 原生 session 数据库映射定位；另两者用稳定 session ID。三者必须核对完整 cwd；来源 JSONL 记录相对路径与 SHA-256，不复制正文、工具参数或认证信息。

## 数据契约

沿用 execution/v1 的标准分组：

- `usage`：`input_tokens`、`output_tokens`、`total_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`、`reasoning_output_tokens`、`request_count`、`request_attempt_count`。
- `tools.call_count`：原生工具调用次数。
- `execution.duration_seconds`：沿用执行控制流程壁钟时间，包含 UI 操作和终态收口。
- `execution.agent_duration_seconds`：原生任务耗时或明确标注的推导耗时。
- `usage.collection`：采集器版本、每指标 `status` / `basis`、`sources` 哈希、会话/attempt、警告、后台操作与排除范围；存在不完整 usage 时可提供 `known_subtotals`，不冒充完整总量。

状态：`observed` 原生观测；`inferred` 有明确依据的推导；`partial` 不完整；`masked` 客户端隐藏；`unverified` 非零但口径待验证；`unavailable` 不可用。旧记录没有 collection 时报告按 `legacy` 兼容读取。

采集在隔离 Node 子进程中运行，默认硬超时 25 秒，限制文件大小、遍历数和输出大小。失败只使资源字段为空并记录枚举原因，不能改变执行终态或触发 Prompt 重发。显式设置 `WEB_E2E_RESOURCE_METRICS=off` 可停用；这不会关闭原有执行状态记录。

## QwenWork 实验开关

QwenWork 运行时使用进程级开关 `QODERCN_EXPOSE_TOKEN_USAGE` 暴露原生 usage。execute-web-e2e 1.12.4 / QwenWork Driver 1.10.15 起由 Driver 自动管理：全新单题默认安全重启客户端，全新批次默认只在第一题前安全重启，并仅向新客户端子进程注入 `QODERCN_EXPOSE_TOKEN_USAGE=1`。调用者无需设置环境变量，也不能把它写入系统全局环境或题目 Prompt；已有进程不会因为控制 Harness 的环境变化而自动生效。

```bash
bash <execute-skill>/scripts/run-qwenwork.sh <全新单题根目录>
```

Windows CMD：

```bat
call <execute-skill>\scripts\run-qwenwork.cmd <全新单题根目录>
```

开关存在、环境变量设置成功或界面显示数字均不代表适配验收通过。不要修改应用二进制或全局用户设置。

采集器 1.1.3 已核对 macOS QwenWork 1.0.5，以及 Windows QwenWorkCN 1.0.5.0、1.0.6.0 的精确客户端身份，并兼容 Windows Node 18 对超过 `MAX_PATH` 的日志文件无法直接 `realpath(file)` 的限制；采集器会真实解析受信根和父目录，文件叶节点仍须为普通非符号链接。三种客户端身份的 SDK 均为 `@ali/qodercn-agent-sdk-next@1.0.28`、transcript 版本均要求 `1.1.32`，且 qoder provider runtime SHA-256 完全相同。`drivers/metrics/qwen-profile.mjs` 分平台和客户端版本冻结精确身份，1.0.6.0 使用独立 Profile ID；采集时只读当前应用比对，客户端版本、SDK、transcript 版本、平台或哈希不同均不放行 Token 归一化。应用已升级或迁移后的历史采集可能因无法复核原运行时而保留 unverified，不能用环境开关强制放行。Windows 1.0.6.0 的非零 Token 已完成全新 L1 与下述对账门禁；历史 masked 样本不会因新增 Profile 被改写。自动注入的新 Driver 身份仍须重新完成至少一个全新 L1，不能仅凭代码测试继承实机 `PASSED`。

该版本的原生 `input_tokens` 直接来自 `prompt_tokens`，**已经包含缓存读取**；总 Token = input + output，不再加 cache read。须按 request ID 去重并核对请求/响应集合、逐响应有效非零输入/输出、缓存不大于输入，以及 `turn.finished` 终值。缺响应、混入隐藏零值、缺终态/字段时保留 partial 与已知小计；终值冲突保留 unverified。请求数、工具数、耗时独立判断，不因 Token 不可用一起丢失。`cache_creation_input_tokens=0` 是适配器默认值，标准缓存写入量仍为 null；不声称已观察到真实零写入。

2026-09-16 隔离单题实测：8 请求、7 工具、输入 293981、输出 3115、缓存读取 281792、总 Token 297096、原生耗时 108.356 秒；主任务后的记忆整理另有 1 请求，排除于主任务汇总。该样本证明 macOS 指定运行时口径，不代表所有模型/客户端版本或 Windows 生产验收通过。

## 历史结果只读验证

```bash
node <execute-skill>/scripts/collect-resource-metrics.mjs \
  --state /absolute/automation_state.json \
  --workspace /absolute/execution/tasks/<task_id> \
  --harness workbuddy \
  --output /absolute/audit/task-resource-metrics.json
```

AstronStudio 另需 `--session-db /absolute/state.sqlite`。输出必须是新文件。此命令只生成旁路 JSON，不回填历史 execution_record、task_score、submission 或回执，不改变候选哈希。正式历史回填需要另外设计带审计的迁移，不能手改冻结记录。
