# 冻结轨迹 Office 审计副本保护与受控恢复

Office 初始输入审计的 `original.bin`、`observed.bin` 仍是 Office ZIP 字节。
采集 staging、正式 trace 和新评分交接均保护这些 opaque 副本；macOS 设置
user immutable，防止宿主元数据写入。正常验分继续逐字节校验，错误包含漂移路径。

历史副本发生漂移时不能接受新 SHA，也不能用源 Workspace 或当前输出反推原件。
`scripts/recover_trace_office_copies.py` 是显式维护入口：要求原 execution ZIP
与 round-unit 锁一致，其内 manifest 与正式 unit manifest/编排锁一致；唯一题内
输入必须逐字节满足原 trace 引用的 SHA 和大小。只处理尚处于 RULES_READY、
无项目、preflight、裁判和分数的任务；仅允许 `*-original.bin` 的严格 CWM
元数据差异。业务成员、其他自定义属性、关系、未知差异均拒绝。

先将全部变体写入不可覆盖审计目录和 intent，再把原位置文件移入同一审计目录，
原位置恢复精确原字节并保护。原 manifests、冻结 SHA、候选、私有参考、题面、
契约和成绩不改写；所有原生会话保持。该流程不放宽普通 verifier，不补零。
已启动评分的受影响题目须另外创建独立评分 attempt，不能使用此维护入口。

```bash
python recover_trace_office_copies.py \
  --unit-root UNIT \
  --orchestration-root ORCHESTRATION \
  --execution-zip ORIGINAL_LOCKED_EXECUTION_ZIP \
  --output-root UNIT/evidence/trace-office-recoveries/NEW_REPAIR
```

维护后必须使用原冻结实现重新 `verify-score`/编排验分，并复验正式采集。
中断或重复 output 失败关闭，检查 intent 和原始变体后再决定恢复，不能盲重试。
新实现保持旧 60 题、无 Office 审计和旧 trace schema 的原评分语义。
