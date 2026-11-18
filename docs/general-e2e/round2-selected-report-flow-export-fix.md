# round2 选定报告流程回执与研发导出对接

Report 0.8.66 的 selected_report 在同一生成进程内，按真实报告数据与已经生成的
全部制品调用标准 build_report_receipt，生成 receipts/report-receipt.json，
校验标准契约后一起封存。原 composite-report-receipt.json 仍保留其逐题选定谱系。
没有生成执行、采集或评分回执，也不改变分数、任务范围、来源验证或原时间。

显式外置交付目录的收据路径以 workspace-root 为制品基准；seal_report 使用同一
基准重验每个真实制品。Run收口时可将相同收据原字节保存到原batch的receipts内，
通过原 --canonical-report-archive 入口验证ZIP中的相同收据及全部制品SHA。

资源预览一次覆盖A:M的完整合并标题，异常区范围覆盖实际全部异常行。
每幅预览仍从新导入的同一导出工作簿生成，不回写或导出预览工作簿。

Run 0.7.31 的 selected-only研发导出保持五个核心报告成员强制存在，有运行审计时
强制保留该审计；标准回执、领导版JSON及已存在的附加验分索引一并保留。原生报告
没有生成的附加索引不再成为无条件必需成员。逐题选定身份、score/record/candidate
SHA和离线VERIFY检查保持。导出方仍可附上独立逐题只读验分回执作为明确诊断附件。

32项相关Python检查及隔离预览Node检查通过，覆盖外置报告真实收据的规范ZIP验证、
收据篡改拒绝、核心成员缺失拒绝、可选索引兼容、原始SHA/身份与恢复安全。
