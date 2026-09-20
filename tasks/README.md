# QwenWork macOS General 前置核验

真机执行前，使用仓库内的只读入口核对原始日志 metadata：

```bash
python3 tools/qwenwork_metadata_preflight.py /绝对/原始日志根
```

入口只读取指定文件或目录下的 `.json`/`.jsonl`，从日志对象显式字段提取
`sessionId` 和绝对 `cwd`，并统计每个 segment 的 `known`、`total`、`missing`、
`mismatched`。它不会启动 QwenWorkCN、申请 slot、读取历史 canary、读取 usage 或
terminal，也不会从目录名或其他日志推断绑定关系。`usage` 和 `terminal` 固定为
`null`，缺少真机原始日志时状态为 `blocked`。
