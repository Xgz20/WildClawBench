---
name: report-general-e2e
description: 校验并汇总 General E2E submission 和回传包，生成同源 JSON、Markdown 与 Excel 报告；不执行用例、补评分或把评测异常计为能力零分。
---

# 汇总 General E2E 报告

从通过身份、哈希和协议校验的回传包生成可复算汇总，显式披露范围、覆盖率与异常分母。

## 当前能力门禁

先运行：

```bash
python -m eval_general_e2e skills --name report-general-e2e --json
```

只有 `implementation_status` 为 `operational` 时才发布正式报告。当前 `interface_only` 表示 General 聚合与渲染实现尚未交付；不得把 Web 报告或旧 CLI 报告仅改标题后发布。

## 责任边界

- 输入：校验通过的 submission、回传包和冻结报告配置。
- 输出：同源可复算 JSON、Markdown、Excel，以及资源覆盖率和异常分母。
- 枚举冻结任务全集；失败和未评任务保持显式状态，不能缩小分母。
- 未全量覆盖的资源指标只展示已知小计与覆盖数；全缺失不补零。
- 不调用被测 Harness、不补做 criterion 判断、不覆盖旧 attempt。
