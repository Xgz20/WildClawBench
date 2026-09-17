---
name: collect-general-e2e
description: 收集 General E2E 执行状态、终态 Workspace、原始轨迹和资源数据并形成正式执行回执；不用于导入评分回传包或决定分数。
---

# 采集 General E2E 证据

将一次执行 attempt 收口为冻结候选和可审计证据，阶段名固定为 `collect-evidence`，不与 `import-return` 混用。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name collect-general-e2e --json
```

只有 `implementation_status` 为 `operational` 时才写入正式证据目录。当前 `interface_only` 表示轨迹适配和资源采集组件尚未交付；不得从最终文件反推或补造工具记录、Token、请求次数及原生会话身份。

## 责任边界

- 输入：执行状态、原生轨迹和终态 Workspace。
- 输出：冻结候选、原始/标准轨迹、资源指标、证据清单和执行回执。
- 校验 attempt 身份、Prompt digest、原生会话绑定及候选完整性。
- 未知指标保留 `null` 和来源状态；不能按零值填充。
- 不调度评分、不判定 criterion、不导入管理员侧回传包。
