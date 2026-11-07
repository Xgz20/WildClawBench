# HR规则返回诊断的时间序列化

Score0.10.79的独立HR修复attempt已用v1 Profile完整导出六份证据JSON，随后在受管Worker对规则返回字典执行严格JSON校验时再次失败：诊断错例仍含Excel原生`datetime.time`。旧attempt没有规则组件、复核请求或裁判，Worker及六份JSON保持原件。

Score0.10.80／Core0.2.8的精确HR v2 Profile保留v1的导出时间处理，并用同一个原`to_jsonable`策略规范规则返回字典。只改变JSON表示层：时间为ISO文本，原字段、数值计算、比较、分母与权重不改，也不把时间或未知值填零。v1的精确修正配方与源码SHA保存在历史表，既有manifest不追加v2行为。

修复在新的私有诊断副本中运行完整受管Worker至退出，验证JSON返回、50项复核上下文和全部六份证据文件；发现模式仍抑制所有临时数值，不赋复核决定。控制器不得用诊断替代正式独立评分。

Orchestrate0.11.63严格绑定旧v1的契约、原始源码、有效发现源码、Profile、TypeError原文和真实Worker退出证明，锁定六份原JSON后保留旧未评分。修复评分继续从同一冻结执行建立独立attempt；原执行、旧评分尝试、失败和其他有效成绩不覆盖。
