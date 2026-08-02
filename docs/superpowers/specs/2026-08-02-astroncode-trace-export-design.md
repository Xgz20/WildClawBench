# AstronCode Trace 采集与归档设计

## 决策摘要

WildClawBench 的 AstronCode Harness 默认开启 Codex rollout trace。每个评测 run 在容器清理前，将该 run 产生的全部 `trace-*` 目录压缩为结果目录中的单个 `astroncode_traces.tar.gz`，不导出散落的 trace 文件。

公开开关为 `ASTRONCODE_TRACE_ENABLED`：未设置或设置为空时开启；`1/true/yes/on` 开启；`0/false/no/off` 关闭；其他值视为配置错误。Harness 开启 trace 时，向容器注入 AstronCode/Codex 原生开关 `CODEX_ROLLOUT_TRACE_ROOT=/tmp/rollout-traces`。

Trace 归档失败不改变评测执行状态、分数或有效性，只在 `execution_status.json`、`agent.log` 和运行日志中记录失败。

## 现状与证据

AstronCode 0.0.13 镜像中的二进制支持 `CODEX_ROLLOUT_TRACE_ROOT`。`docker/astroncode/v3/AstronCode-日志集成.md` 说明该变量启用后，每个 Thread 会在指定根目录下产生一个 `trace-*` 目录，包含 `manifest.json`、`trace.jsonl` 和 `payloads/`。

当前 Harness 没有注入该变量。`AstronCodeAgent.collect_usage()` 只复制 `/root/.acode/sessions` 到 `astroncode_sessions/`，之后 `eval/run_batch.py` 删除任务容器。对本地 `eval_out_debug` 的扫描结果是 53 个 AstronCode session JSONL、0 个 `trace.jsonl`、0 个 trace `manifest.json` 和 0 个 `trace-*` 目录；其中包含使用 AstronCode 0.0.13/v0.3 镜像完成的 run。

因此缺口位于 Harness 的启用和导出流程，不需要修改 AstronCode 核心或重建 Docker 镜像。

## 目标与约束

### 目标

- 现有 AstronCode 评测命令不增加参数时也默认采集 trace。
- 一个 run 无论产生多少个 Thread、Turn 或子 Agent trace，结果目录只增加一个压缩包。
- 模型执行成功、失败或超时时，只要容器存在，都尝试导出已产生的 trace。
- 归档失败可观测但不阻断评分。
- 关闭开关后不注入核心 trace 变量，也不生成归档。

### 非目标

- 不解析、筛选、合并或脱敏 trace 内容。
- 不改变 session JSONL、`chat.jsonl` 或 `chat_openclaw.jsonl` 的现有采集方式。
- 不为 Codex Harness 同步增加该能力。
- 不在本次改造中增加归档大小上限、保留周期或远端上传。

### 约束

Trace 可能包含完整模型请求、响应、instructions、工具参数、命令输出和上下文摘要。归档必须以 `0600` 权限落盘，并在文档中标注敏感信息风险。单文件归档解决文件数量问题，但不会限制总存储体积。

## 配置契约

| 配置 | 默认值 | 行为 |
| --- | --- | --- |
| `ASTRONCODE_TRACE_ENABLED` | 开启 | 控制 Harness 是否采集和导出 AstronCode trace |
| `CODEX_ROLLOUT_TRACE_ROOT` | `/tmp/rollout-traces` | Harness 内部注入的容器路径，不作为评测命令公开配置 |

布尔值解析在 `AstronCodeAgent` 构造时完成并快照，避免同一批评测中环境变量变化导致 run 间行为漂移。非法值在启动首个任务前抛出明确配置错误。

## 数据流

1. `AstronCodeAgent` 构造时解析 `ASTRONCODE_TRACE_ENABLED`，空值按开启处理。
2. 开启时，`_start_container()` 注入 `CODEX_ROLLOUT_TRACE_ROOT=/tmp/rollout-traces`。
3. `_prepare_workspace()` 创建 `/tmp/rollout-traces`，保证尚未发起模型请求时也有稳定的归档根目录。
4. AstronCode 为主 Thread、子 Agent 或其他内部 Thread 分别生成 `trace-*` 子目录。
5. 评分完成后，`collect_usage()` 在现有 session 采集之外调用独立的 trace 归档方法。
6. 容器内使用 `tar -czf` 将整个 `rollout-traces/` 目录压缩为临时文件，并统计第一层 `trace-*` 目录数量。
7. Harness 使用 `docker cp` 将临时文件复制为 run 目录下的 `astroncode_traces.tar.gz`，再将宿主机文件权限设为 `0600`。
8. `eval/run_batch.py` 按现有流程收集其他产物并删除容器。

归档内部保持原始目录结构：

```text
rollout-traces/
  trace-xxxx/
    manifest.json
    trace.jsonl
    payloads/
      1.json
      ...
  trace-yyyy/
    ...
```

结果目录中不复制 `trace-*` 目录或单个 payload 文件，只出现：

```text
astroncode_traces.tar.gz
```

## 状态与失败处理

`execution_status.json` 增加 `trace_export` 对象：

```json
{
  "trace_export": {
    "enabled": true,
    "status": "exported",
    "archive": "astroncode_traces.tar.gz",
    "trace_count": 3,
    "error": null
  }
}
```

状态定义：

- `exported`：归档复制成功，`trace_count` 可以为 0；空目录仍生成合法压缩包。
- `disabled`：开关显式关闭，不生成压缩包。
- `failed`：容器不存在、压缩失败、复制失败或权限设置失败；删除不完整的宿主机压缩包。

归档失败时：

- `execution_status.json` 保留原有 `status`、`exit_code` 和 `error`，只更新 `trace_export`。
- `agent.log` 追加 `runner.trace_export` 结构化事件。
- Python logger 输出 warning。
- `collect_usage()` 继续返回 usage，后续评分产物和异常扫描继续执行。

错误文本不得包含 trace 内容、凭证或完整 Docker 环境，只记录失败阶段和经过长度限制的 stderr。

## 关键取舍

采用 Harness 级开关而不是让用户直接设置 `CODEX_ROLLOUT_TRACE_ROOT`，避免评测命令依赖容器内部路径，也防止调用方误传宿主机路径。内部仍使用 AstronCode/Codex 原生变量，不修改核心逻辑。

采用每 run 单归档而不是逐文件 `docker cp`，因为一次 run 可能产生多个 `trace-*` 及大量 payload。压缩后结果目录文件数稳定，且保留原始层级，便于后续离线排查。

复用 `collect_usage()` 所在的容器清理前阶段，是因为该方法当前已经负责复制原生 session，且在成功、执行错误和超时路径上都会调用。本次增加独立私有方法隔离 trace 逻辑，不扩展所有 Harness 的公共接口。

## 测试与验收

自动化测试覆盖：

- 未设置、空值和真值默认开启。
- `0/false/no/off` 显式关闭。
- 非法布尔值抛出配置错误。
- 开启时 Docker 环境包含固定的 `CODEX_ROLLOUT_TRACE_ROOT`，关闭时不包含。
- 多个 `trace-*` 目录只导出一个 `astroncode_traces.tar.gz`，归档保留顶层目录结构。
- trace 数量为 0 时仍生成合法归档并记录 `trace_count=0`。
- 压缩、复制或 chmod 失败时记录 `failed`，删除不完整归档且 usage 采集不抛异常。
- 执行错误和超时后的 `collect_usage()` 仍触发 trace 导出。

真实冒烟验收使用 AstronCode 0.0.13/v0.3 运行一个现有单用例，不显式配置 `ASTRONCODE_TRACE_ENABLED`。验收结果必须满足：

1. run 目录存在且仅存在一个 `astroncode_traces.tar.gz` trace 产物。
2. `tar -tzf` 能列出 `rollout-traces/trace-*/manifest.json` 和 `trace.jsonl`。
3. `execution_status.json.trace_export.status` 为 `exported`，`trace_count >= 1`。
4. 原有 score、usage、session 和 workspace 产物保持生成。
5. 显式设置 `ASTRONCODE_TRACE_ENABLED=0` 后复跑，不生成归档且状态为 `disabled`。

## 文档变更

- `.env.example`：增加默认开启的 `ASTRONCODE_TRACE_ENABLED` 和显式关闭示例说明。
- `docker/astroncode/v3/AstronCode-日志集成.md`：补充 WildClawBench 默认采集行为、归档路径、解压命令、关闭方式和敏感信息提示。
- 现有 AstronCode 评测命令无需增加开关；文档说明不配置时默认开启。

## 回退

运行时可设置 `ASTRONCODE_TRACE_ENABLED=0` 立即恢复为不采集 trace，无需更换镜像。代码回退只涉及 AstronCode runner、配置示例、日志文档和对应测试，不影响其他 Harness。
