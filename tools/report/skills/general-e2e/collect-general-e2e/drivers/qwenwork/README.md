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

归档前的 `metadata_coverage` gate 会记录 transcript 和 segment 的 `known/total/missing/mismatched` coverage。transcript 每行必须有匹配的 sessionId 和绝对 cwd；segment 可保留原生日志中的部分 sessionId/cwd 缺失，但必须有已绑定的 session 目录、至少一个匹配的绝对 workspace claim，且任何显式错配都会阻断采集。缺失字段不会从目录名或其它行补写，gate 也不会据此推断 usage 或 terminal 状态。

工具状态只按原生完成证据归一化：shell `exit_code=0` 才是 `success`，`tool.execution.finished.status=completed` 单独不会升级为成功；冲突或缺失保持 `unknown`。当前 QwenWork 1.0.6 token profile 尚未验证，因此所有 usage 值保持 `null/status=unavailable`，并以 `coverage` 保留 model-response 分母，不补零。

本目录的 fixture/test 只证明脱敏文件的契约和失败关闭规则，不代表 QwenWork 真机采集、cleanup、评分或生产准入已经验收。
