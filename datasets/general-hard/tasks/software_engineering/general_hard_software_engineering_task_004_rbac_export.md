---
id: general_hard_software_engineering_task_004_rbac_export
name: 登录黑名单与导出授权的跨层修复
category: software_engineering
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
tags:
  - custom
  - general-hard
dataset_report: {"category": "software_engineering", "category_name": "软件工程与故障修复", "category_order": 4, "checkpoint_capabilities": {"boundary_cases": ["code_generation"], "business_correctness": ["code_generation"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 登录黑名单与导出授权的跨层修复

## Prompt

请修复这个本地合成校园服务的登录黑名单与导出跨层授权，不允许账户已禁用、入黑名单、撤销或过期的旧会话继续导出，同时保留正常角色的合法功能。主要交付是源码修复，只允许修改以下三个文件：
- /tmp_workspace/project/auth.py：登录与当前身份/会话校验
- /tmp_workspace/project/export.py：直接导出服务授权、资源/行/字段边界
- /tmp_workspace/project/routes.py：请求入口与调用链一致

先阅读 /tmp_workspace/contract.md 的公开API和完整权限矩阵。/tmp_workspace/fixtures/users.json 包含惰性合成用户、租户、角色、禁用/黑名单、资源与行数据；它是示例，不能写死ID、用户名或测试输出。/tmp_workspace/tests/test_public.py 是受保护的正常功能公开测试，/tmp_workspace/tools/run_security_tests.py 是实际测试记录工具；/tmp_workspace/requirements.lock 声明仅用Python标准库，无需安装任何依赖。/tmp_workspace/project/__init__.py 同样受保护。

合同要求：所有入口使用当前服务端账户状态，不能信任缓存身份或请求自报的角色/租户；student只导出已参与资源的本人行，teacher只导出本人所属资源，tenant_admin也不能跨租户，auditor不能导出。默认和显式字段权限、拒绝错误、行过滤、状态不被意外修改及会话时效以contract.md为准。直接调用export_data也必须成立，不能只修路由或一律拒绝。

完成后运行 python -B tools/run_security_tests.py，交付 /tmp_workspace/results/security_tests.txt：由实际运行产生、绑定最终三份源码SHA的JSON格式测试记录（扩展名为.txt）。公开测试只是兼容性烟雾样本，原工程通过也不能证明授权正确；请自行针对安全边界验证，额外说明可写results。修改最终源码后必须重新运行并更新记录。不可改公开测试、夹具、依赖锁、工具或其它输入来制造通过。

离线完成，仅使用本题映射到/tmp_workspace的材料，不访问真实账号、不联网、不发消息、不调用付费接口。全部输入和保护文件保持原字节，仅上述三个源码可改，所有新增报告写results；不新增其它源码模块。自动__pycache__/*.pyc可忽略。GT和评分说明不提供给候选。结论区分事实、推断和未知，不虚构缺失信息。

## Expected Behavior

仅修改列出的三个源码，修复登录规范化黑名单、账户当前状态和会话校验，以及租户、角色、资源归属、行与字段授权；正常功能继续可用。交付绑定最终源码的实际测试记录。

## Grading Criteria

- [ ] `business_correctness`: 当前登录/黑名单与角色×资源×字段授权的真实行为；合法和拒绝样本各占本项一半，保留正常功能。
- [ ] `boundary_cases`: 独立旧会话、即时禁用/黑名单/角色或租户变更、撤销/过期、直接入口、身份伪造、混租户行与非法字段边界；含合法控制，不以全部拒绝取满分。
- [ ] `delivery_integrity`: 三份指定源码可读取和解析(.5)，保护输入与允许修改范围完整(.5)；输入变更不扩为其它项自动清零。
- [ ] `evidence_binding`: 实际公开测试记录绑定最终源码SHA(.5)，其命令、returncode和逐测试状态与评分侧真实独立重跑一致(.5)；漏交/无效记录仅归本项。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import runpy
    from pathlib import Path
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    helper=root/"gt/grader.py"
    if not helper.is_file() or helper.is_symlink():
        raise RuntimeError("H044_GT_REQUIRED: grader.py")
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
datasets/general-hard/workspace/software_engineering/general_hard_software_engineering_task_004_rbac_export
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 严格对应蓝图order44；L3为设计预估尚未经多模型结果验证，900秒是元数据，不据此设置候选总截止。
- 总自动规则=.55业务+.25边界+.15交付+.05证据；overall_score不重复映射能力。业务/边界各按正向与拒绝样本均衡计算。
- 源输入与105个显式oracle先于参考冻结；两条不同计算路径交叉复核一致，由同一作者执行，不宣称独立人类/盲审。参考与等价解不进入GT或运行时规则。
- 保护输入违规只归delivery_integrity，测试记录遗漏/过期只归evidence_binding；私有测试使用可信原始辅助文件，仍独立评价候选三源码行为，不按候选测试或补丁字符串评分。
- 候选语法/运行/行为错误或测试超时按相应行为机会失分；GT/可信脚本缺失或字节不符、解释器不可用等保留typed评测异常，不补能力零分。
- 作者验证只运行真实本地规则Worker和独立子进程；没有Harness执行、语义Judge或finalize，不代表正式评测或四端可用性。
- 所有数据为惰性原创合成，无真实用户、账号、秘密、联网或安装依赖；本机进程是复现工具而非恶意代码安全沙箱。
