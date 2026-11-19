---
id: general_hard_software_engineering_task_011_security_regression
name: 修复方案审计与最小安全补丁
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

# 修复方案审计与最小安全补丁

## Prompt

请审查 /tmp_workspace/repair_plan.md 并修复小型导出服务的真实越权与CSV公式注入缺陷。保留合法导出和原接口，新增实际安全及正常回归，不能只隐藏按钮、改计划文字或关闭全部导出。先读 /tmp_workspace/contract.md、permission_matrix.csv、export_contract.json、plan_items.json 和 project 源码。数据原创合成、离线完成；L4仅设计估计，900秒为元数据而非能力分墙钟截止。

只允许修改 /tmp_workspace/project/authorization.py、project/exporter.py、project/routes.py。其他所有输入原路径原字节保护，包括health.py、__init__.py、矩阵、夹具、测试与回放器；新文件只写results。不得联网、安装、登录、发消息、调用真实账号/业务接口或读私有GT。三模块接口与完整状态协议见contract.md。

服务器当前actor角色、tenant、owner范围和columns决定权限。GET /download、/legacy/export、/preview、POST /jobs与GET /jobs/{id}都要有对应的当前授权，混合可见/不可见ID整批拒绝。[]只导表头，省略IDs才是全可见；保留请求去重顺序与列序。job必须属于当前创建人和tenant，取回时重新检查当前角色/action、记录归属和列权限；授权仍在才返回创建时快照。不能靠难猜ID或客户端role/tenant替代服务器判断。

按CSV列类型修复。文本在声明的危险前缀条件下，仅在原始完整值前加apostrophe，并正确使用CSV引用；普通文本、逗号、双引号和嵌入换行必须保留。amount按数值保持值并固定2位，负数、正号和零不加apostrophe。允许等价LF/CRLF、QUOTE_ALL/最小引用和文件首BOM；不会运行真实表格软件或声称覆盖全部产品公式解释。

支持Python3.11/3.12标准库及公开的纯服务profile，合法但超出profile/原生文档读取范围、缺可信上下文或基础设施超时保留typed未评估，不伪造零分。调用实际Python函数/状态与CSV解析，不是HTTP、浏览器或Harness证据；profile不是OS安全沙箱。

python -B -m unittest discover -s tests_public检查原型窄正常控制。python -B regression.py --output results/regression.json实际导入最终三源码，回放6个固定公开安全/正常控制，记录最终SHA/source_digest、矩阵/契约/夹具/回放器SHA、真实response、CSV解析、公共状态和PASS/FAIL。可以诚实FAIL；真实性与功能分开，padding不稀释固定义务。

交付三份实际补丁和：
- /tmp_workspace/results/review.docx：原生可编辑计划审计与范围，含结论、P1..P6接受/调整/否决及理由、旁路入口、最小修改与实际验证边界。必须有原生表格plan_id/decision/reason_code/modules的6个唯一ID行，枚举词汇见plan_items.json（不提供各项答案）；modules用分号列实际允许源码，不强制参考组织。另用普通原生段落记录source_digest=<最终SHA>、regression_sha256=<报告原字节SHA>、real_Harness=false、real_spreadsheet_app=false。原生读取profile不支持隐藏字段、文本框/透明等复杂可视性布局；合法超限/未支持文档typed未评估。
- /tmp_workspace/results/regression.json：h051-regression/v1实际回归与最终源码绑定，不编造未执行结果。

自动规则评估实际授权/CSV行为、六个明确的客观审计决策和原生产物/证据绑定；自由说明的自然语义、文风和视觉布局质量不在自动分内，也没有已执行Judge。机器代码字段不能被说成完整自然语言审校。作者参考会渲染检查，但这不等于所有候选视觉布局已验证。

计划审计中，不满足本题授权、类型或合法功能约束的主张，可用reject（否决原方案）或revise（需改正后采用），风险原因必须准确；不因这两个处理标签的选择单独扣分。accept只用于可以原样采用的方案。自由解释不由机器字段代替。

## Expected Behavior

最小白名单修复多入口越权与类型化CSV风险，保留合法功能/数值，逐项审计坏计划并交付最终源码绑定真实回归。L4设计估计未验证。

## Grading Criteria

- [ ] `business_correctness`: 实际保留授权导出/预览/job/旧接口、数值与顺序；业务内部.8实际正常用例+.2六项显式计划decision/reason_code，非自由DOCX语义评分。
- [ ] `boundary_cases`: 实际拒绝越tenant/owner/column/当前job权限旁路并按列类型处理危险文本、控制字符与合法负数；关闭全部功能不能通过正常双控制。
- [ ] `delivery_integrity`: 保护三个允许源码外输入；原生DOCX及regression.json可解析，实际补丁在白名单。
- [ ] `evidence_binding`: 固定6公开真实输出/CSV解析/状态与最终三源码、矩阵和回放器SHA绑定，DOCX摘要一致；不以填充/自述得分。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': 'f84470975e7822641732f592c9d1acddeaa359d3e52b0bd46a5758e3706aadec', 'trusted_files.json': 'c3ca92c108bd671bea19f3d4acfb2c599fa9ea0c95f72bc8fd679f381901005b'}.items():
        path = root / "gt" / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H051_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/software_engineering/general_hard_software_engineering_task_011_security_regression
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 37个权限/CSV原始源用例由Python Decimal和独立Node集合/BigInt cents双算，在参考前冻结；六项审计来自显式计划与契约，不用候选输出生成GT。
- 源码运行支持三模块纯服务profile；无OS沙箱、HTTP、真实表格产品、浏览器、Harness、Judge或人工专家证明。
- DOCX自动分只核六项明确客观decision/reason_code及原生字段/源码绑定；自由解释自然语义、文风与视觉布局明确未评分，不把结构字段当完整审校。
- 两原生作者参考用当前Documents技能、marker、bundled Python/docx及bundled headless Office实际逐页渲染看图，禁用桌面LO和外部安装；第一轮缺中文字体/标题残线失败保留后修为任务私有HeitiSC字体配置。
- 继承origin.review_basis中的人工复核是模型作者措辞，无人工专家记录或背书。
- 独立安全保护超时、缺可信上下文/不支持profile为typed未评估，不虚构候选零分；900非能力分墙钟门槛。
- root v4补不安全计划reject/revise等价，不擅自规定公共未说明的二者排他边界；源37服务真值、6原风险原因、输入和两参考不变。原v3标签假失分及80freeze保留，当前只重跑受影响正负例，旧38不冒称全当前版本。
