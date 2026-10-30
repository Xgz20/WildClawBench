# 已冻结候选与实时源目录的 Office 属性变体

只用于正式采集已发布后，冻结候选及全部原回执仍满足原 SHA，而实时源 Workspace 的 Office 文件被追加指定 CWM 自定义属性的情况。评分仍使用原冻结候选；它的业务内容、身份、SHA、任务范围、评分契约与权重不变。

先保全原回执、冻结候选和实际源变体，并确认原生任务已终态、被测客户端已收尾。此入口不代替原生身份、进程清理、原始轨迹、完整性或评分准入检查。

```text
PYTHON_ABS -X utf8 COLLECT_SKILL/scripts/source_office_metadata.py prepare --unit-root UNIT --task-id TASK --output-root UNIT/evidence/source-office-metadata-variances/TASK/NEW_ID
```

生产器要求原始 exact-all 策略、原回执对候选描述及执行/证据清单的 SHA 绑定、完整冻结候选树和同一原生 cwd。源目录不能新增、删除或更换文件类型。改变的文件必须为 Office 包，ZIP 其他成员保持原字节；仅允许符合固定结构的 CWM 属性及必要的 custom-properties 内容类型/关系声明，其他属性和关系也须一致。稳定检查通过后写入新目录中的 `variants.zip` 和补充清单；ZIP 同时保留冻结规范字节与当前源字节。

正式不可变核验时显式选择这份补充包：

```text
node COLLECT_SKILL/drivers/workbuddy/finalize.mjs --verify-only --unit-root UNIT --task-id TASK --source-office-metadata-supplement SUPPLEMENT --source-office-python PYTHON_ABS
```

其他 Harness 的通用 finalizer 同样识别这两个 verify-only 参数。裁判和报告不得据此把源变体当作原评分输入，或改写原执行/候选/采集回执。核验结果分别列出当前源 SHA 和冻结规范 SHA，并明确 `raw_source_matches_original=false`。

每次核验都重新比对全文件范围、原回执、规范字节、业务成员、属性结构及归档变体；不信任补充清单的自述。补充包过期、归档变化、普通文件变化、其他 Office 元数据变化、冻结副本变化均失败关闭。该入口不适用于首次采集尚未稳定的 Workspace，不自动选择补充包，不重跑 Harness 或补做评分。
