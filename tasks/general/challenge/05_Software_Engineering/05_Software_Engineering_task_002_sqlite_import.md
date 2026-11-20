---
id: 05_Software_Engineering_task_002_sqlite_import
name: 无外键声明下的事务导入一致性
category: software_engineering
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "software_engineering", "category_name": "软件工程与故障修复", "category_order": 4, "checkpoint_capabilities": {"boundary_cases": ["code_generation"], "business_correctness": ["code_generation"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 无外键声明下的事务导入一致性

## Prompt

预约导入模块在失败和重试时会破坏数据库一致性，请依据本地契约修复。

先读 /tmp_workspace/contract.md。源码位于 /tmp_workspace/project/store.py，公开测试为 /tmp_workspace/project/test_public.py，演示输入为 /tmp_workspace/fixtures/batch.json。保留公开API和既有schema，不新增外键声明、表或触发器；用应用层校验处理关联、冲突、累计容量和错误分流。一个批次失败必须整体回滚，重复导入不能产生新业务记录或重复占用容量；调用者已有事务时，不能提交或回滚调用者此前的更改。

只修改 /tmp_workspace/project/store.py，不改公开测试、样本和contract.md，也不添加其它项目源码。Python 3.11+、sqlite3标准库已可用，离线完成，不安装依赖或连接真实数据库。

在独立临时库按契约依次做首次导入、同批重试、缺失关联失败和中途注入失败，交付 /tmp_workspace/results/db_audit.json，保留三个表的实际前后状态及返回/错误信息；不要只写行数或口头声称回滚。实际运行公开测试，把最终源码SHA、退出码、命令和原始日志写入 /tmp_workspace/results/tests.txt。失败如实记录，最终记录必须绑定最终源码。临时DB放系统临时目录或results，Python缓存可自动生成，其它新文件只写results。

## Expected Behavior

按contract.md在应用层校验三表关联和容量，原子处理整批输入、重复数据和失败注入；保留调用者事务边界及独立连接可见性。独立SQLite驱动核对40组声明式状态向量并审计schema，同时复跑9个原始公开测试，核验演示记录和最终源码绑定。

## Grading Criteria

- [ ] `business_correctness`: 在不增加数据库ForeignKey声明的条件下修复校验和事务边界，整批失败不留半成品，重复导入不产生重复业务记录。
- [ ] `boundary_cases`: 逐项识别并正确处理：部分提交；重试重复数据；靠新增外键违背契约。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt" / "grader.py"))["grade"](root)
    return {
        "business_correctness": result["business_correctness"],
        "boundary_cases": result["boundary_cases"],
        "delivery_integrity": result["delivery_integrity"],
        "evidence_binding": result["evidence_binding"],
        "overall_score": result["overall_score"],
    }
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/05_Software_Engineering/05_Software_Engineering_task_002_sqlite_import
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H042；难度L2为预估。代码、演示输入及状态向量均为独立合成，不含线上用户原文或附件。
- 规则权重为业务0.55、边界0.25、交付0.15、证据0.05。业务按原子回滚/关联/幂等/调用者事务分别0.3/0.2/0.25/0.25汇总；边界按兼容/字段类型/错误优先级分别0.3/0.4/0.3汇总，各族内等权。
- schema出现外键、触发器、额外表或公开列漂移时，业务和边界项均为0；保护文件被改时，边界、交付和证据项为0。允许等价事务实现，不匹配源码风格或SAVEPOINT名称。
- 本地作者控制和独立状态向量验证见私有gt/validate_authoring.py及gt/authoring_validation.json。尚未验证Docker Worker封装、四端执行、独立人工审阅或实测区分度。
