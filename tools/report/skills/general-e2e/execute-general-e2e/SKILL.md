---
name: execute-general-e2e
description: 在 AstronStudio 等桌面 Harness 中执行单个或批量 General E2E 用例；用于自动或人机协作做题，不负责正式证据收口、评分或报告。
---

# 执行 General E2E 用例

驱动或协助桌面 Harness 执行 execution 包，并持久化可恢复的发送和原生会话状态。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name execute-general-e2e --json
```

只有 `implementation_status` 为 `operational` 时才发送 Prompt。当前 `0.2.0/interface_only` 已提供 AstronStudio macOS 只读探针，但正式会话状态机、Prompt 单次发送与恢复仍未交付；除探针外应保留输入包、明确报告未就绪并停止。不要用 Web E2E Driver 或旧 `eval_e2e` 替代，因为它们的终态、证据和恢复语义不同。

## AstronStudio macOS 只读探针

在发送任何 Prompt 前运行：

```bash
node scripts/probe_astronstudio_macos.mjs \
  --output /absolute/new/probe.json \
  --config-output /absolute/new/run-config.json
```

探针只读取 macOS、应用包、精确主进程、GUI 锁定状态、CDP 元数据与可见模型/推理/权限、状态库快照和依赖版本。它不启动、退出或重启 AStudio，不点击 UI，不选择工作空间/模型，不读取 composer 内容，也不发送 Prompt。输出路径必须是新文件。

只有探针返回 `PASS` 才会写 `run-config.json`；CDP 缺失或不属于已核对主进程、`DevToolsActivePort` 早于当前进程、状态库快照不完整、模型/推理/权限不能从可见 UI 回读时均返回 `NEEDS_ATTENTION`，不会用最近线程的持久化模型冒充当前配置。完整字段和失败语义见 [AstronStudio macOS 探针契约](references/astronstudio-macos-probe.md)。

## 责任边界

- 输入：execution 包、Harness 配置和执行策略。
- 输出：原生 thread/turn/session/cwd 绑定、执行终态和初步资源记录。
- Prompt 发送意图和 digest 必须先持久化；发送状态不确定时进入人工关注，不重发。
- 支持 `automated` 与 `human_assisted`，人工语义干预必须单独记录。
- 不读取 scoring 包，不冻结正式候选，不启动裁判或汇总报告。
