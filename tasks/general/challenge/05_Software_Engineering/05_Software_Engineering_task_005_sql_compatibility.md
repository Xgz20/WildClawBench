---
id: 05_Software_Engineering_task_005_sql_compatibility
name: SQL生成器的边界语法与参数绑定
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

# SQL生成器的边界语法与参数绑定

## Prompt

修复查询生成器的SQL边界语法与参数绑定，保持参数化，并让空集合、NULL、保留字、多条件分组和结果多重集合符合公开合同。只允许修改 /tmp_workspace/project/query_builder.py；不能通过放宽测试、改夹具或拼接输入值来制造通过。

请先读取 /tmp_workspace/contract.md，保持公开build_query(spec)接口。输入包括：
- /tmp_workspace/project/query_builder.py：存在语法、参数顺序与NULL/空集合语义问题的原始生成器。
- /tmp_workspace/fixtures/queries.json：固定ID的空集合、NULL、保留字、嵌套条件、日期窗口和引号情境。
- /tmp_workspace/fixtures/schema.json、/tmp_workspace/fixtures/schema.sql、/tmp_workspace/fixtures/data.json：两张惰性合成表的白名单、SQLite建库和确定性数据。
- /tmp_workspace/project/test_public.py：基础兼容性公开测试；/tmp_workspace/project/db_fixture.py：受保护的本地内存库构造器。
- /tmp_workspace/tools/run_regression.py：实际执行查询并记录回归结果的保护工具；/tmp_workspace/requirements.lock：仅用Python3.11+标准库sqlite3、SQLite3.35+，无需安装。

交付修复后的 /tmp_workspace/project/query_builder.py，以及运行 python -B tools/run_regression.py 实际生成的 /tmp_workspace/results/query_audit.json 和 /tmp_workspace/results/tests.txt。tests.txt同样为JSON格式：保留真实命令、returncode、完整stdout/stderr、测试状态、最终源码和query_audit SHA；audit保留全部固定查询ID的实际SQL、params、结果/错误及源码/输入SHA。修改最终源码后须重跑，不能删掉失败项改变分母或写死输出。

只读SELECT、标识符白名单、匿名?或:name绑定、可空成员集合、NULL安全相等/不等、布尔分组和排序/重复行语义以contract.md为准。SQL排版、引号方式及合法等价实现不限，评分按实际执行与重绑定结果核验。基础公开测试可能在原工程已通过，不能替代边界回归。本题不要求第二引擎、JOIN或聚合，不得虚构跨引擎实测。

仅读取本题exec映射到/tmp_workspace的材料，GT和评分说明不提供给候选。只改列明的一份源码；project/__init__.py、公开测试、辅助模块、所有fixtures、合同、锁和工具保持原字节，不增添其它源码。所有新增报告写results，Python自动__pycache__/*.pyc可忽略。离线完成，不访问真实账号、不发送消息、不调用真实付费接口、真实数据库或网络，不安装依赖。结论区分事实、推断和未知，不虚构缺失信息。

## Expected Behavior

仅修复指定生成器，维持参数化和输入只读，正确处理空集合、NULL、保留字、条件分组与排序/多重集合；交付绑定最终源码和真实SQL/命令结果的两份记录。

## Grading Criteria

- [ ] `business_correctness`: 固定12项真实SQLite结果语义：保留字、多个绑定及顺序、嵌套条件、ISO日期文本窗口、排序、投影和重复行；不比对参考SQL字符串。
- [ ] `boundary_cases`: 固定28项边界：空集合/空组、NULL相等/不等和含NULL成员集合、非法标识符/类型、实际占位符绑定以及同一SQL参数重绑定后结果。漏项/异常不改变固定分母。
- [ ] `delivery_integrity`: 源码可读可解析(.30)、保护输入与修改范围完整(.40)、query_audit与tests两份交付可解析各(.15)；不因单一SQL错误清零无关项。
- [ ] `evidence_binding`: 当前源码/输入SHA的audit绑定(.20)、tests源码绑定(.20)、固定11个公开查询的实际独立重放与当前生成结果一致(.40)、真实测试命令/退出码/状态与audit SHA一致(.20)。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import runpy
    from pathlib import Path
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    helper=root/"gt/grader.py"
    if not helper.is_file() or helper.is_symlink():
        raise RuntimeError("H045_GT_REQUIRED: grader.py")
    result=runpy.run_path(str(helper))["grade"](workspace_path=str(root),transcript=kwargs.get("transcript"))
    return {"business_correctness":result["business_correctness"],
            "boundary_cases":result["boundary_cases"],
            "delivery_integrity":result["delivery_integrity"],
            "evidence_binding":result["evidence_binding"],
            "overall_score":result["overall_score"]}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/05_Software_Engineering/05_Software_Engineering_task_005_sql_compatibility
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 严格对应蓝图order45。L3为设计估计、尚未经模型结果验证；900秒仅是任务元数据。
- 自动总规则=.55业务+.25边界+.15交付+.05证据；总体分不重复映射能力。业务12、边界28、公开audit11项均用冻结固定分母。
- 40项源先行oracle中，30项有效查询的Python关系运算结果及4个重绑定预期，在参考前由独立手写SQL在实际SQLite3.53.1复核；另10项非法结构按公开合同声明拒绝，并在最终交接前补充独立结构复核。同一作者计算路径，不宣称人类专家/盲审。无第二引擎实测。
- 原工程实际公开测试全绿，但6个公开查询报错；原始复现先于参考。参考与采用命名复用绑定、IS/IS NOT关系的等价实现不进入GT或运行时评分。
- 实际SQLite执行/ProgrammingError/OperationalError/非法候选SQL按对应机会失分；可信GT/脚本/数据/引擎缺失、SHA不符、锁定SQLite版本不匹配须typed评测异常，不补能力零分。
- 保护输入违规只归交付，私有测试用可信原始辅助文件；缺/坏/旧audit/tests依相应交付或绑定机会失分，不能替代或扩散成业务全零。
- 作者Worker只执行原生规则和独立本机SQLite子进程；不运行Harness/Judge/finalize，不构成正式评测、四端可用性或恶意代码沙箱证明。
