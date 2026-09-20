# QwenWork General CB-B collector

`collector.mjs` 是 QwenWork macOS General 的原生证据采集层。它只读取已经终态的 CB-A attempt journal、unit 内的 Prompt/binding evidence，以及 QwenWork 已落盘的 `projects/<session_id>.jsonl` 和 `logs/sessions/*/<session_id>/segments/*.jsonl`；不会启动、停止、重启或通过 CDP 操作客户端。

```bash
node collector.mjs \
  --unit-root /absolute/unit-root \
  --journal-file /absolute/unit-root/qwenwork-attempt-journal.json \
  --client-trace-root /absolute/.qwenworkcn \
  --output-root /absolute/unit-root/.general-e2e/collection/<attempt>
```

输出目录包含 `execution/automation-state.json`、规范化 `trace/transcript.jsonl`、全部原始 transcript/segment、`trace/bindings/` 副本、`trace/trace-index.json`（CB-B trace-index v2）和 `resource-metrics.json`（resource-metrics v1）。原生没有可证明的 thread/turn/lifecycle ID 时保持 `null`；稳定的 QwenWork `session_id` 是唯一会话身份来源。

采集器在归档前失败关闭以下情况：终态/一次发送/Prompt 或 cwd 不一致；binding evidence 哈希、身份、session、project、终态观察不一致；transcript/segment 的 session 或 workspace provenance 缺失或漂移；原始路径存在符号链接、越界、重复或内容变化；SQLite snapshot 元数据存在但 quick check、sidecar 读模式或摘要不可信。活动 SQLite 不在 collector 中重新读取，必须使用 execute 阶段已产生并哈希锁定的 binding evidence。

归档前的 `metadata_coverage` gate 会记录 transcript 和 segment 的 `known/total/missing/mismatched` coverage。transcript 每行必须有匹配的 sessionId 和绝对 cwd；segment 的原生行级字段允许部分缺失，这是因为正式收口同时使用已校验的 session 目录绑定和行级 provenance：segment 目录必须唯一绑定到目标 session，至少一行必须提供匹配的绝对 workspace claim，任何显式 session/workspace 错配都阻断采集。缺失字段不会从目录名、其它行或文件顺序补写；`directory_binding` 与 `cwd` coverage 必须原样交接。gate 也不会据此推断 usage 或 terminal 状态。

QwenWorkCN 1.0.6 真机采集前，按可恢复顺序执行以下清单：

1. 重新读取当前客户端版本、目标 task/attempt、workspace 和 Prompt digest；若版本、attempt 或 workspace 不一致，停止，不复用旧 attempt。
2. 确认客户端空闲、没有活动/待处理会话，申请一个新的桌面 slot；发送前只接受当前视图中唯一可回读的 project trigger。
3. 发送前写入并哈希锁定 CB-A journal/binding evidence；一次发送后保存原生 session_id、transcript 路径和 segment 目录路径。发送不确定时标记 `NEEDS_ATTENTION`，禁止重发。
4. 采集前运行 metadata gate：transcript 行级 session/cwd 必须全覆盖；segment 允许原生日志字段缺失，但目录绑定、显式 workspace claim 和冲突检查必须通过。不得从目录名或其它日志补齐字段。
5. 仅在 UI/原生终态和 active stream 停止均有证据时交给 CB-B collector；恢复只按原生 session_id 进入原会话，并重新执行第 3、4 步。
6. 交接时保留 `usage=null/unavailable`、terminal 未验证和各自 coverage；真机必须单独确认日志字段是否覆盖，不能用离线 fixture 代替。

工具状态只按原生完成证据归一化：shell `exit_code=0` 才是 `success`，`tool.execution.finished.status=completed` 单独不会升级为成功；冲突或缺失保持 `unknown`。当前 QwenWork 1.0.6 token profile 尚未验证，因此所有 usage 值保持 `null/status=unavailable`，并以 `coverage` 保留 model-response 分母，不补零。

本目录的 fixture/test 只证明脱敏文件的契约和失败关闭规则，不代表 QwenWork 真机采集、cleanup、评分或生产准入已经验收。
