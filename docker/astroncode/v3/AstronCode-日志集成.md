1. # 客户端日志

1. ## session文件

在 ~/.acode/sessions/year/month/day 目录下

1. ## 模型API日志

- 注入环境变量：export CODEX_ROLLOUT_TRACE_ROOT=/tmp/rollout-traces （自定义trace存放日志目录）
- 启动astron-code
- 正常使用

开启后，每次启动 Thread 都会生成一个目录：

```Plain
/tmp/rollout-traces/trace-xxxx/
  ├── manifest.json
  ├── trace.jsonl
  └── payloads/
      ├── 1.json
      ├── 2.json
      ├── 3.json
      └── ...
```

**信息包括：**

- 发送给模型的完整 Responses 请求 Body。
- instructions、input、tools、模型名称、reasoning 配置等。
- 模型返回的原始 Response 事件。
- 模型发起的工具调用及参数。
- 工具执行结果、Shell 命令和终端输出。
- Thread、Turn、子 Agent 的运行过程。
- 上下文压缩请求、摘要和替换历史。

  **关闭开关：**

  unset CODEX_ROLLOUT_TRACE_ROOT

暂时无法在i讯飞文档外展示此内容

1. # 模型引擎日志

1. ## 获取session文件

在 .acode 目录下，有相关会话文件

![img]()

1. ## 使用工具获取

mac版本：

暂时无法在i讯飞文档外展示此内容

![img]()

-input session文件

-output 输出json文件

-flow old 固定值，不需要更改

1. ### result.json

astron-code-jsonl.id: session文件中模型返回的sid

talk_text: 输入到引擎提示词

content、reasoning_content、tool_calls：模型输出

sid:模型引擎日志id

![img]()

## WildClawBench Harness 采集行为

AstronCode Harness 默认开启 rollout trace，评测命令无需显式设置
`ASTRONCODE_TRACE_ENABLED`。如需关闭采集和导出，设置：

```bash
ASTRONCODE_TRACE_ENABLED=0
```

每个评测 run 只生成一个 trace 产物，全部 `trace-*` 目录会压缩到结果目录中的：

```text
astroncode_traces.tar.gz
```

列出归档内容：

```bash
tar -tzf astroncode_traces.tar.gz
```

解压到独立目录：

```bash
mkdir -p astroncode_traces
tar -xzf astroncode_traces.tar.gz -C astroncode_traces
```

归档保留以下结构：

```text
rollout-traces/
  trace-*/
    manifest.json
    trace.jsonl
    payloads/
```

`execution_status.json.trace_export` 记录导出状态：`exported` 表示归档成功，
`disabled` 表示已显式关闭，`failed` 表示归档失败；其中还会记录归档文件名、
trace 数量和错误信息。

Trace 包含完整的模型请求、响应、工具参数和命令输出，属于敏感评测数据。
归档以 `0600` 权限写入仅限制主机文件访问权限，不代表内容已经脱敏或适合公开；
不得上传到公开仓库或发送给无权限人员。
