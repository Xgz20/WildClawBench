# WorkBuddy 原生 JSONL 指标与补采

正常 collector 自动在 `~/.workbuddy/projects` 按绑定的 session ID 找唯一日志；`--native-projects-root` 可指定其他安装数据根。JSONL、binding、标准 transcript 和指标一起进入正式 trace-index/collect 回执。没有日志时保留不可用；身份、Prompt、原生调用或 usage 冲突时失败关闭。

JSONL 的 `providerData.messageId` 是模型响应去重键，同一响应可含多个 function_call；`providerData.usage` 与 `rawUsage` 必须对账，`message.usage` 是同一消费的镜像，不累加。输入已含缓存读取，total=input+output。底层 HTTP 请求失败和重试次数不由完成响应数推断。

## 对已有完整 unit 补采

每题运行一次：

```bash
node drivers/workbuddy/supplement-resources.mjs \
  --unit-root /absolute/unit \
  --execution-record /absolute/unit/evidence/tasks/TASK/ATTEMPT/execution-record.json
```

只接受原 completed record 与 collect receipt，冻结来源 record/resource/receipt SHA、dataset、task/attempt，并从原 trace-index 的 runtime binding 验证新增 JSONL。输出固定在 `evidence/resource-supplements/<task-id>/`：`native.jsonl`、`resource-metrics.json`、`supplement.json`。已存在的目录拒绝覆盖。原 candidate、transcript、execution record、score、submission 与旧 ZIP/报告不改写。

`run-general-e2e package-return` 会把新增目录按成员 SHA 打包成新 package ID。导入后若与旧包冲突，显式 `select-import` 选择新包，然后用 report `>=0.3.0` 生成新的报告目录。报告端重验包、原记录与补充证据，并再次运行相同原生解析器复算指标；旧 score 仍绑定原 execution record，不需要重做 Harness 或重新判分。

报告 JSON 的 lineage 同时记录 `resource_metrics_sha256`、`base_resource_metrics_sha256` 与 `resource_supplement_sha256`，可追溯本次更正。补充只影响资源统计，不修改任务分数或执行状态。

## 原生任务耗时

collector 从已绑定的运行时请求采集两项：

| 字段 | 起止点 | 包含内容 |
| --- | --- | --- |
| `agent_duration_seconds` | `request.startedAt`（回退 `timestamp`）→ `completedAt`（回退 `finishTimestamp`） | 请求生命周期，包含工具与客户端处理 |
| `duration_seconds` | `prompt.sent_at` → 同一原生完成点 | 用户发送后的流程，额外包含发送及排队等待 |

两者均非纯模型推理时间；不使用会话创建/更新时间、日志 mtime、采集结束时间或题目 `timeout_seconds`。JSONL 缺失不影响原生时间采集。缺字段保留 null，真实零值为 0，非法类型或倒序拒绝采集；内部 `finishTimestamp` 早于 `completedAt` 是正常的不同完成阶段。

旧批次可仅用冻结证据补齐耗时：

```bash
node drivers/workbuddy/supplement-timing.mjs \
  --unit-root /absolute/unit \
  --execution-record /absolute/unit/evidence/tasks/TASK/ATTEMPT/execution-record.json
```

输出为 `evidence/timing-supplements/<task-id>/` 的 `resource-metrics.json` 和 `supplement.json`；有旧 Token 补采时先验证并绑定其 SHA，保留全部非时间指标。旧 JSONL 补采算法版本 `0.1.0` 继续可验证，组件版本为 `0.2.0`。补采目录不可覆盖；如需两项补采，先 Token 后时间。按上节 package/import/select，改用 report `>=0.3.1`；JSON lineage 新增 `timing_supplement_sha256`，无需重做评分。
