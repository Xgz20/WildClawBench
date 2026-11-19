# 评测任务目录

题面位于 tasks/<场景>/<数据集>/<分类>/<任务 ID>.md。逐题素材在 workspace/ 下使用相同的场景、数据集、分类和任务 ID。

- general/wildclawbench/en 为上游原版题面。cn 是阅读译本，共用 en 的素材。
- general/regression、general/work、general/challenge 分别维护基础回归、真实工作和挑战场景。
- web/artifactsbench、web/custom 和 ppt/custom 分别维护 ArtifactsBench、自建 Web 及 PPT 专项。

固定范围的批次按数据集冻结清单选题。目录和 CLI 的说明见[通用场景自建评测集说明](../docs/guides/general-e2e/通用场景自建评测集说明.md)。

## QwenWork macOS General 前置核验

真机执行前，使用仓库内的只读入口核对原始日志 metadata：

```bash
python3 tools/qwenwork_metadata_preflight.py /绝对/原始日志根
```

入口只读取指定文件或目录下的 `.json`/`.jsonl`，从日志对象显式字段提取
`sessionId` 和绝对 `cwd`，并统计每个 segment 的 `known`、`total`、`missing`、
`mismatched`。它不会启动 QwenWorkCN、申请 slot、读取历史 canary、读取 usage 或
terminal，也不会从目录名或其他日志推断绑定关系。`usage` 和 `terminal` 固定为
`null`，缺少真机原始日志时状态为 `blocked`。
