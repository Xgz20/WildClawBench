# OpenCode 推理强度映射设计

## 目标

让 WildClawBench 的通用参数 `--thinking <level>` 在 OpenCode Harness 中实际生效。例如评测命令传入 `--thinking high` 时，OpenCode 无头命令应收到 `--variant high`。

## 现状

`eval/run_batch.py` 已将 `args.thinking` 写入 `AgentTaskSpec.thinking`，但 `OpenCodeAgent.run_task()` 调用 `_run_prompt()` 时没有继续传递该字段。当前 `_build_exec_command()` 生成的命令只有模型、输出格式和权限参数，因此 OpenCode 使用模型或 provider 的默认 variant。

OpenCode 镜像中的 `opencode run --help` 明确提供：

- `--variant <value>`：选择 provider 相关的推理强度，例如 `high`、`max`、`minimal`。
- `--thinking`：仅控制是否显示 thinking blocks，不控制模型推理强度。

## 设计

沿现有调用链显式传递可空的 `thinking`：

```text
AgentTaskSpec.thinking
  -> OpenCodeAgent._run_prompt()
  -> OpenCodeAgent._run_opencode_exec()
  -> OpenCodeAgent._build_exec_command()
  -> opencode run --variant <thinking>
```

规则如下：

1. `thinking` 为非空字符串时，使用 `shlex.quote()` 转义后追加 `--variant <thinking>`。
2. `thinking` 为 `None` 或空字符串时，不追加 `--variant`，继续使用模型或 provider 默认值。
3. 不维护 `low/medium/high` 白名单。OpenCode 的 variant 是 provider 相关能力，runner 应透传 `max`、`minimal` 等合法扩展值。
4. 不追加 OpenCode 的布尔 `--thinking`，避免混淆“输出思考块”和“设置推理强度”两种语义。

## 兼容性

未传 `--thinking` 的现有命令保持不变。已传 `--thinking high` 的 Linux/macOS 评测命令会开始真正控制 OpenCode 推理 variant。

若目标模型或 provider 不支持指定 variant，错误由 OpenCode/provider 按其原生行为返回；runner 不静默降级，也不替模型推断支持列表。

## 测试

新增 OpenCode runner 单元测试，覆盖：

1. `thinking="high"` 时生成命令包含 `--variant high`。
2. `thinking=None` 或空字符串时生成命令不包含 `--variant`。
3. variant 值经过 shell 安全转义。
4. `run_task()` 将 `spec.thinking` 传到执行链，防止只测试命令构造函数而遗漏上游传递。

实现遵循 TDD：先运行新增测试确认因缺少参数传递而失败，再完成最小实现并运行 OpenCode 相关测试及完整单测集。
