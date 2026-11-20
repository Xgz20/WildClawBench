---
id: 05_Software_Engineering_task_006_config_migration
name: 多层配置合并与兼容迁移
category: software_engineering
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "software_engineering", "category_name": "软件工程与故障修复", "category_order": 4, "checkpoint_capabilities": {"boundary_cases": ["code_generation"], "business_correctness": ["code_generation"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 多层配置合并与兼容迁移

## Prompt

修复多层配置合并与兼容迁移，只修改 /tmp_workspace/project/config.py。实现确定的迁移和defaults < project < user覆盖顺序，区分缺失、显式null、0、False与空串，保留未知键，并保证重复迁移/重复合并稳定，不能擅自重置用户配置。

先读 /tmp_workspace/schema.md 的类型、旧新键冲突、嵌套合并与逐键来源合同。/tmp_workspace/fixtures/configs/ 下10份JSON是新旧键、空值和未知键的本地合成样例；保留全部固定case_id。/tmp_workspace/project/test_public.py 是旧接口基础测试，/tmp_workspace/tools/run_migration_checks.py 是实际迁移和回归记录工具，/tmp_workspace/requirements.lock 声明仅用Python3.11+标准库。/tmp_workspace/project/__init__.py 同样受保护。

保持migrate_config与merge_configs(...,with_audit=False)旧接口；with_audit=True须按schema.md返回config、逐终端键sources和全部旧键migrations事件。目标新键即使为零/空值仍优先；中间层null擦掉的子树不能被高层局部dict复活；输入和返回结果不能相互别名。未知值/列表顺序不能擅改，False与0不同。

交付修复后的 /tmp_workspace/project/config.py，以及实际运行 python -B tools/run_migration_checks.py 生成的 /tmp_workspace/results/migration_audit.json 和 /tmp_workspace/results/tests.txt。后者也为JSON格式：记录真实命令、returncode、完整stdout/stderr、逐测试状态及最终源码/audit SHA。audit记录所有固定case_id的实际逐键来源、迁移变化或错误、最终源码及输入SHA。最终源码改变后须重跑，不能漏项改分母或以自述替代运行。公开基础测试可能在原工程已全绿，不能证明边界已正确；可在results补充自己的回归说明。

仅读取本题exec映射到/tmp_workspace的材料，GT不提供给候选。只改上述一份源码，不改公开测试、schema、fixtures、锁、工具和其它输入，不增添源码模块；报告仅写results，自动__pycache__/*.pyc可忽略。离线完成，不安装依赖、不访问真实账号、真实用户配置、网络或付费接口，不发送消息。结论区分事实、推断和未知，不虚构缺失信息。

## Expected Behavior

仅修改指定配置源码，在不改输入的情况下按层迁移并深合并，严格保留显式值、未知键与元数据，重复迁移稳定；交付绑定最终源码及真实运行的逐键来源/变化和回归记录。

## Grading Criteria

- [ ] `business_correctness`: 固定12项规范化结果：逐层迁移、深合并、正确优先级、已知/未知字段及旧接口；不匹配参考源码或固定字典排版。
- [ ] `boundary_cases`: 固定20项：0/False/null/空串、祖先擦除与空dict、幂等/重复合并、输入所有权、来源事件与JSON Pointer、无效已知类型。严格区分bool和数字，浮点容差1e-12。
- [ ] `delivery_integrity`: 源码可读可解析(.30)、保护输入及修改范围(.40)、audit/tests两件结果可解析各(.15)；单个业务根因不清零无关项。
- [ ] `evidence_binding`: audit源码/固定输入SHA(.20)、tests源码SHA(.20)、固定10个case_id与当前源码实际重跑结果一致(.40)、真实测试命令/返回码/状态和audit SHA(.20)。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import runpy
    from pathlib import Path
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    helper=root/"gt/grader.py"
    if not helper.is_file() or helper.is_symlink():
        raise RuntimeError("H046_GT_REQUIRED: grader.py")
    result=runpy.run_path(str(helper))["grade"](workspace_path=str(root),transcript=kwargs.get("transcript"))
    return {"business_correctness":result["business_correctness"],"boundary_cases":result["boundary_cases"],
            "delivery_integrity":result["delivery_integrity"],"evidence_binding":result["evidence_binding"],"overall_score":result["overall_score"]}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/05_Software_Engineering/05_Software_Engineering_task_006_config_migration
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 严格对应蓝图order46；L3为设计估计未做多模型验证，900秒为元数据。
- 自动规则=.55业务+.25边界+.15交付+.05证据。业务12/边界20/公开绑定10项分母冻结，漏交不能缩小分母。
- 原始输入和32项oracle先于参考冻结；路径事件/祖先屏障与独立递归归并/有理数转换两条计算路径在参考前全部复核一致；同一作者计算，不宣称独立人类/盲审。
- 允许合理等价实现、事件顺序和额外来源元数据；只按规范化结果/来源语义比较。False与0严格区分，数值容差1e-12，字典顺序无关，列表顺序保留。
- 候选源码/类型/运行错误按固定行为机会失分；可信GT/脚本缺失或SHA不符、解释器不可用为typed评测异常，不补能力零分。
- 保护输入违规仅归交付；私有运行使用可信原始辅助文件。audit/tests遗漏或过期仅按对应交付/绑定机会计，不代替业务结论。
- 作者使用真实受管prepare/run-rules及正常/去runtime/独立目录保管复核；不运行Harness、Judge或finalize，不构成正式评测或四端可用性证明。
