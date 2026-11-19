# quillship-cli 发布看板

**当前：local_validation / blocked。** 本轮未推进；下一候选为 repair_alignment。

| 阶段 | 状态 |
|---|---|
| draft_intake | done |
| scope_freeze | done |
| local_validation | blocked |
| repair_alignment | not admitted |
| handoff_ready | not admitted |
| release_wrap | not started |

## 当前检查

- 已修复：docs 查询缺口、manifest 缓存依赖、看板漂移、工作区分类 snapshot 和审计同步。
- 唯一阻塞：bundle_integrity 为 stale。10:37 回执仍测试旧 docs 值；10:44 回执不属于本轮截止时点。
- docs 已 locally_reconciled；manifest 缓存 current，但组件 awaiting_validation。CLI/completion 保留 frozen 和原有效回执，不因 docs 改动失效。
- 旧 handoff/mostly green 是历史复制文案，现已纠正。AUD-QS-041 是历史警告；新增 AUD-QS-042 记录刷新与阻塞。
- 本轮选源和后续交接详见 outputs/release_progress_report.md。未执行外部发布。
