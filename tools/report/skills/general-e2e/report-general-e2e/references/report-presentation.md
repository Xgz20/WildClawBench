# 报告展示与跨批次审计

展示配置只改变派生报告，不改变来源身份、实际模型、判分、分母或资源profile。先使用冻结来源和显式逐题选择完成验证，再生成新的报告版本；不得从旧Excel抄分或重判criterion。

## 单元名与领导版目标

单元默认显示为`模型@Harness 客户端版本`。同模型的不同客户端版本保持独立，不自动附加round等轮次后缀；完全同名的独立单元仍使用unit ID区分，不能合并。来源轮次继续保留在原batch/unit/attempt及审计索引中。

`--target-unit`指定文字总结目标，不改变表格范围。两个报告入口均支持：

- `--leader-comparison-scope same-harness-version`：默认优先同Harness、同客户端版本的参照。没有匹配单元时明确回退到全部组合，缺少版本不视为同版本。
- `--leader-comparison-scope all-combinations`：按明确需要比较全部组合。
- `--leader-secondary-table 总览 --leader-secondary-table 难度对比`：仅在指定章节少量补充主要比较组之外的总体最高分参照。默认仅总览；`--leader-secondary-table none`关闭补充。其他章节和资源倍数优先使用主要比较组，所有比较表继续显示全部参评单元。

固定客户端版本仍是跨批次配置对照。平台、推理、权限、Judge及计时profile差异按来源披露，不能自动宣称严格单因素因果实验。不能因为客户端相同而补全未知配置。

用户要求使用客户端选项名时，通过`--display-config /absolute/display.json`传入JSON。以下仅是展示示例，unit ID必须替换为已验证的真实单元ID：

```json
{
  "schema_version": "wildclawbench.report-display-overrides/v1",
  "unit_model_labels": {
    "qwenwork-unit-id": {
      "label": "高级",
      "reason": "用户指定客户端选项名；原实际模型ID和验证状态保持不变"
    }
  }
}
```

不要将某个批次的“高级”选项写成所有QwenWork来源的默认模型身份。模型未知时仍保留原`actual_id=null`；显示覆盖不构成模型识别证据。

## 章节布局与数值

“效率与资源”下依次设置`Token对比`和`任务耗时对比`。Token总结位于Token表格上方；原生任务耗时总结位于任务耗时子标题下、任务耗时表格上方。兼容旧领导版JSON中合并保存的两个总结段落，禁止重复显示耗时总结。

所有差值先对最终Excel未舍入值相减，再按十进制ROUND_HALF_UP展示；不相减已经显示为两位小数的分数。Token和工具倍数使用各自冻结任务分母，并保留部分覆盖的上下界或观测值说明。缺失、零分母及不同字段覆盖不默认补零。

新生成Excel的模型名列加宽并换行，资源运行ID和依据文本保留可读行高。只切换文字总结目标、表格内容完全不变时，可以按规范ZIP成员SHA复用已验收XLSX及预览；必须明确记录字节相同和预览复用，不能冒充新渲染。若裸XLSX被宿主追加CWM等元数据，保留标记，以原规范ZIP为字节权威并记录OPC差异。

## 显式路径迁移与兼容性例外

`selected_report.py --data-output ABS --data-output-root ADMIN_ROOT`允许将只读复算JSON写入新管理员目录。输入包、manifest、索引和资源路径仍按原`--workspace-root`验证；新输出必须在明确边界内且文件不存在。默认不指定该参数时仍只允许workspace-root内输出，不写入批次专用绝对路径。

同一原unit的多个已验证来源包继续使用`imports[unit_id].packages`和逐题`source_package_id`选择。不同原unit/config的跨批次组合先完成源验证，再分配稳定的派生report_unit_id。更改显示名不能替代身份映射，不拼造新的标准return、collect或单来源报告回执。

确有缓存包装或既有grader修复差异时，派生报告可通过`definition_compatibility[task_id]`引用独立兼容性审计：

```json
{
  "status": "PASS",
  "audit_path": "/absolute/compatibility-audit.json",
  "audit_sha256": "审计文件的完整SHA-256",
  "accepted_signatures": [["原题面SHA", "原contract SHA"]],
  "comparison_signature": ["共享展示采用的题面SHA", "共享展示采用的contract SHA"]
}
```

该SHA还须与`lineage.compatibility_audit_sha256`一致。审计必须为PASS，并在`material_runs`中为每条当前任务运行唯一绑定原unit、batch、execution_attempt、execution record SHA、score SHA和原题面/contract签名。审计漂移、来源错映射、缺题或未知签名继续拒绝。规则语义、GT、Rubric、权重及路径映射的兼容证明仍由管理员审计负责，展示器只消费并核验明确绑定的证明，不替代评分或自行批准实质差异。

既有管理员裁决只沿用其准确绑定的原attempt及证据，不把原生unscored自动改为0。原评分、执行、manifest和receipt保持字节不变；派生裁决、材料等价映射及路径迁移均单独保留SHA与来源。新报告在新目录验证、封存并登记真实SHA，既有规范ZIP保持历史权威。
