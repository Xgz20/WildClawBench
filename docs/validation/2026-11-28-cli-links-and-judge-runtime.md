# CLI 符号链接封存与评分运行副本修复

实现分支：`feat/cli-freeze-and-judge-isolation-20261128`，基于 `a2217ad3`。对应执行 #49–#52 的两类框架问题；原始排查材料保存在独立调查目录，本轮不回写这些批次。

## 符号链接封存

CLI `freeze_input`、评分输入验证、裁判候选复制及桌面返回验证现在保留真实相对符号链接，清单记录路径、类型、目标及目标字节摘要，不将链接展开成普通文件。

封存验证同时检查工作区边界和封存包边界，阻止工作区链接逃逸到 `task.json`、轨迹文件等兄弟元数据；已有文件清单和内容漂移检查保留。文件型旧版 v1 清单保持兼容，不修改数据集或评分规则。

## Docker CLI 裁判

- `candidate/` 保留为原件，并在容器内独立以只读子挂载暴露；继续逐项验证路径、类型、权限、字节及链接目标。检查结果写入 `candidate-integrity.json`，失败仍报 `CLI_JUDGE_CANDIDATE_DRIFT`。
- 每次裁判调用创建独立 `runtime/candidate/`，将裁判当前目录设置为 `runtime/`。原有相对 `candidate/` 文件引用因此指向等价运行副本，Python 测试、构建或其他复核写入不会改变原件。
- 设置 `PYTHONDONTWRITEBYTECODE=1`，临时文件和通用缓存指向 `runtime/tmp`、`runtime/.cache`。即使复核程序自行开启字节码缓存，也只写入运行副本。
- 裁判响应优先从实际当前目录的 `judge-response.json` 读取，兼容原绝对路径回传和原生最终答复。模型、推理强度、冻结 Rubric 和原评分权重不变；运行副本用于验证，不能用修复后的实现替换原交付评分。
- 桌面裁判的输入说明保持原语义；本轮为其复制/返回验证补齐符号链接类型，不重建或部署 Windows 控制器。

## 异常收尾

`run_single_task` 将资源清理放到独立外层 `finally`。封存或评分抛出异常后，仍尝试保存真实 usage、收集工作区/轨迹和异常信息，再关闭进程及清理本次容器。usage 采集失败不会覆盖原封存异常，也不会补造资源数字。

收尾故障记录在 `post-execution-errors.json`，与 Harness 的 `execution_status.json` 分开。原生 `finished/exit_code=0` 保持原样，框架错误继续向批次调用者传播，不生成用于掩盖异常的零分。

## 验证

| 检查 | 结果 |
| --- | --- |
| CLI 评分、链接复制、输入/候选漂移、异常收尾、跑批汇总及原 usage 收集顺序 | 通过 |
| 既有 Windows 链接、Docker headless、桌面评分/导入兼容回归 | 通过；合计 97 项 |
| 本机真实 Docker：四份保留工作区重放封存 | 4 份均通过，原快照不变，链接未展开 |
| 本机真实 Docker：原清理规则的合成正例/链接物化负例 | 正例 1.0；负例仍扣分；零次裁判调用 |
| 本机真实 Docker：#50 事件流水线原候选的 Python 测试 | 只读原件写入被拒绝；在运行副本强制生成 `.pyc` 后完整性验证仍通过 |
| Docker 集成合计 | 3 项通过，全部本机离线；模型调用入口替换为确定性验证函数，没有请求模型 |

集成检查仅使用自有短期本机容器和原始证据的副本；临时容器已清理。#49–#52 的原评分、未完成封存包和服务器残留容器均未修改。业务补封存、补评分及生产部署仍待后续授权和验收。

可复现命令（在具备依赖的 Python 环境中运行）：

```bash
python -m unittest tests.test_cli_scoring tests.test_cli_scoring_isolation tests.test_run_batch_finalization
WCB_RUN_CLI_SCORING_DOCKER_TESTS=1 python -m unittest tests.test_cli_scoring_docker_integration
```

Docker 集成使用本机已有 `python:3.11-bookworm`，不构建或拉取正式评分镜像。`WCB_CLI_REPLAY_ROOT` 可选择包含 `bounded-49` 至 `bounded-52`、`score-error-50-1023/scoring-input/workspace` 的只读调查快照；未提供时跳过四样本重放，使用合成样本检查缓存隔离。Colima 下临时挂载目录放在用户目录内，也可通过 `WCB_DOCKER_TEST_ROOT` 指定 Docker 可见目录。
