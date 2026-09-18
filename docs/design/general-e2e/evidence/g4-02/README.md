# G4-02 独立报告实现证据

## 结论

`report-general-e2e 0.2.0/operational` 已实现独立回传校验、聚合、同源 JSON/Markdown/Excel、资源覆盖与 CLI 结果适配。当前结论来自 macOS 开发机上的离线 fixture、Artifact Tool 实际工作簿和独立 Skill ZIP；未启动 AstronStudio、未调用真实 Codex/API Judge、未启动 Docker，不能据此声明 G4-03 或 Windows 真机通过。

## 实现边界

- 从 batch manifest、report config 和 import index 确认每个 unit 的显式 package 选择；冲突未选择时拒绝报告。
- 重算 return package ID 和逐成员类型、mode、大小、SHA；校验 collect/package/import receipt、submission、execution record、score、resource metrics 及相互身份和来源 SHA。
- 报告全集按 task run 统计，同时保留唯一 task 数。有效 `0.0` 进入能力分母；`evaluation_error/unscored` 保持 null，不补零。
- 分类、难度、unit 和 judge protocol/model/reasoning 分组复用同一冻结集合。
- 11 个资源字段分别记录完整总量、已知小计、task-run 覆盖、原生观察覆盖、部分记录和来源状态；缓存和推理子集不重复计入总 Token。
- 批次壁钟与任务流程耗时之和分别展示。
- `general_e2e_report_data.json` 是同源数据，驱动 Markdown、四 Sheet Excel、CLI adapter 和 report receipt。
- Artifact Tool 工作簿执行 `recalculate()`，扫描公式错误并检查四个关键范围；各 Sheet PNG 已人工视觉检查。
- 输出在同父目录暂存，全部验证通过后原子发布；Excel runtime 无效时不保留部分报告。
- 独立 report Skill ZIP vendoring `general-contracts`；Node 和 `@oai/artifact-tool` 作为显式外部 runtime 注入，不读取 checkout。

## 验证结果

| 门禁 | 结果 | 说明 |
| --- | --- | --- |
| General E2E Python | PASS，123/123 | 包含 9 个 report 聚焦测试、发布后 report receipt 登记、独立 ZIP 入口和既有全链路回归 |
| 旧 `eval_e2e` | PASS，60/60 | 旧入口兼容；日志中的模拟 Docker 错误为测试 fixture，本项未启动 Docker |
| Skill 校验 | PASS，13/13 | Web 6 + General 7 个 canonical Skill |
| layout | PASS | 7 Skills、6 components、0 errors |
| Excel 实际生成 | PASS | 4 Sheets、4 个关键范围检查、公式错误 0、四张 PNG 视觉检查通过 |
| 原子失败注入 | PASS | 缺失 Artifact Tool runtime 时无最终目录、无 pending 残留 |
| 独立 report ZIP | PASS | 隔离目录、`python -I`、空 PATH 下加载 vendored contract validator 并显示 CLI help |
| Python/Node 静态检查 | PASS | `py_compile` 与 `node --check` |
| `git diff --check` | PASS | 无空白错误 |

Excel smoke 使用固定四题 fixture，覆盖有效 0 分、有效非零分、API Judge 评测异常、未评分、完整资源、部分资源和全缺失资源。报告在 batch 内原子发布，产物路径由 `run-general-e2e record-receipt --stage report` 实际重验并登记成功；生成目录位于系统临时目录，未作为生产报告保留。正式报告必须使用 G4-03 的真实回传包重新生成。

## 未完成项

- G4-03 AstronStudio macOS 四题执行→证据→Codex/API 评分→回传→报告真实闭环仍为 `NOT_RUN`。
- O-01 的真实 Codex 评分模型和推理强度须在首次评分前冻结。
- Windows 的 Node/Artifact Tool runtime、junction fallback、路径和视觉结果仍须 G5 真机验证。
