---
id: general_hard_software_engineering_task_009_package_migration
name: 仓库打包迁移与旧入口兼容
category: software_engineering
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "software_engineering", "category_name": "软件工程与故障修复", "category_order": 4, "checkpoint_capabilities": {"boundary_cases": ["code_generation"], "business_correctness": ["code_generation"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 仓库打包迁移与旧入口兼容

## Prompt

完成Python包的src结构迁移，保留旧CLI入口、资源定位和配置兼容，并在临时安装目录实际验证，不能依赖当前仓库cwd偶然成功。

先读 /tmp_workspace/acceptance.md 和 /tmp_workspace/mutable_paths.json。/tmp_workspace/project/ 是含旧flat包、未完成src骨架、legacy入口和资源的原始项目；只可修改mutable_paths.json列出的12个源码/pyproject路径，required_sources必须交付，旧可选源码可按许可保留兼容或移除，其它文件不可改。

保护输入包括 /tmp_workspace/tests_public/ 旧接口回归、/tmp_workspace/offline_wheels/ 已锁SHA且保留许可证的本地pip/setuptools wheel、/tmp_workspace/fixtures/records.json 与 /tmp_workspace/fixtures/configs.json。/tmp_workspace/tools/verify_install.py、package_matrix.py、offline_driver.py、installed_probe.py 均是不可改的真实构建/临时安装/入口验证工具。只用预置Python3.11与3.12，缺解释器须如实报告，不允许联网或安装外部依赖；工具仅在本题临时目录解压锁定构建工具、将待测wheel安装到临时target，不改宿主环境。

交付 /tmp_workspace/project/ 允许清单内的修复源码/打包配置、/tmp_workspace/results/install_matrix.json 和 /tmp_workspace/results/migration.md。实际运行 python -B tools/verify_install.py（必要时以--python311/--python312指定已有解释器）；矩阵须保留两版本真实构建/安装/新旧入口命令、cwd、returncode/完整输出、wheel SHA与保留的wheel、模块origin和最终源码/夹具SHA。源码改变后须重跑。compat说明需清楚交接新旧入口、资源方法、配置语义、实际版本与限制，不得声称未运行的版本通过。

规范化配置、0/False/None、旧键与未知键、CLI返回码、包内资源、src来源与旧console/module/API约定均以acceptance.md为准。须从异cwd和非ASCII临时目录测试，wheel保留于results/install_artifacts；禁止editable安装、以PYTHONPATH指回checkout或修改测试来蒙混。既有源码cwd烟雾测试能跑不代表安装后可用。

仅读取本题exec映射到/tmp_workspace的材料；GT不提供给候选。保护资源、LICENSE、锁定wheel、工具、测试和输入原字节不变，不增添未允许源码，所有额外报告只写results。离线、不访问真实账号、不发消息、不调用付费接口或真实数据库；事实、推断、未知分开，不虚构安装/兼容实测。

## Expected Behavior

完成真实src打包迁移，安装后新旧console/module/API和资源、配置结果等价；实际双解释器隔离构建安装，保留绑定最终源码的矩阵、wheel和兼容说明。

## Grading Criteria

- [ ] `business_correctness`: 两个预置解释器各10配置×新/旧API，共40项真实安装后业务机会；每次同时核返回结果与records/config末态结构和标量类型不变，不单独重复扣交付分。
- [ ] `boundary_cases`: 每解释器16项固定边界，共32项：构建/安装、src字节、资源/zip资源、origin、四新旧入口、错误码、异cwd旧脚本、公开回归和版本metadata。
- [ ] `delivery_integrity`: 必交源码/pyproject可读取解析(.30)、保护输入与修改范围(.40)、matrix与非空兼容说明各(.15)。
- [ ] `evidence_binding`: 最终mutable源码和夹具SHA(.40)、28项公开API/入口与独立当前安装重放一致(.40)、两版实际保留wheel的SHA/源码字节绑定(.20)。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import runpy
    from pathlib import Path
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    helper=root/"gt/grader.py"
    if not helper.is_file() or helper.is_symlink():raise RuntimeError("H049_GT_REQUIRED: grader.py")
    result=runpy.run_path(str(helper))["grade"](workspace_path=str(root),transcript=kwargs.get("transcript"))
    return {"business_correctness":result["business_correctness"],"boundary_cases":result["boundary_cases"],
            "delivery_integrity":result["delivery_integrity"],"evidence_binding":result["evidence_binding"],"overall_score":result["overall_score"]}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/software_engineering/general_hard_software_engineering_task_009_package_migration
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 严格对应蓝图order49；L4为设计预估未做多模型验证，900秒仅元数据。
- 总规则=.55业务+.25边界+.15交付+.05证据；固定分母业务40、边界32、公开重放28、版本2，不因漏项缩小。
- 10个配置结果oracle在reference前用直接过滤求和与独立旧键选择/排除关系/Decimal累计复核一致。实际工具在两解释器均已离线构建安装证明；原工程源码cwd全绿但安装后资源/API失败。
- 两条计算路径由同一作者完成，不宣称人类/盲审。参考与importlib.resources/pkgutil等价资源实现不进入GT或规则，不匹配参考源码字符串。
- Python3.11/3.12为预置真实依赖，实际当前作者解释器3.11.11/3.12.8；锁定pip24与setuptools79原wheel及厂商许可证来自已有本机ensurepip，无网络下载/宿主安装。
- 候选构建、导入、资源或CLI错误按相应机会失分；可信GT/工具/wheel缺失或SHA异常、所需解释器缺失为typed评测异常，不补能力零分。
- md自动部分只查可读非空交付，不以措辞关键词替代构建/安装/兼容正确性。更深叙述质量仍需root审阅。
- 真实managed作者控制及正常/独立去runtime归档保管，不运行Harness/Judge/finalize。临时安装只含本题无外部依赖包，不证明其它OS、真实服务或恶意构建后端安全沙箱。
- v2私有API probe在每次新载入的records/config调用前后作独立深拷贝，按既有40个业务机会核末态结构/类型不变；不声称无瞬时内部动作。v1的21控制保留，mutation-only漏检先真实复现并快照，v2仅重跑正例/等价、新反例/末态恢复合法例、受影响入口及typed控制，分开记录，不冒称旧21均在v2重跑。
- root v3补保留wheel完整模块/资源规范路径、当前源码元数据/入口与RECORD绑定；只归E，当前源码本身缺入口或错误语义仍由原B/boundary承担，不重复处罚。旧v2与不完整wheel假满分回执保留。
