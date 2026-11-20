---
id: 05_Software_Engineering_task_012_prd_full_delivery
name: 跨模块需求实现与验收追踪
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

# 跨模块需求实现与验收追踪

## Prompt

请按 /tmp_workspace/PRD.md 的依赖顺序完成12项成员管理需求和缺陷修复。必须有真实后端权限、持久化和前端控制器行为，不接受只写计划、假数据或完成声明。先读 /tmp_workspace/contract.md、requirements.json、runtime.json 及 project 源码。所有记录为原创合成内容，离线完成，无真实账号。L4仅设计估计，900秒仅元数据，不作能力分墙钟阈值。

仅允许修改 /tmp_workspace/project/repository.py、service.py、api.py、client.mjs。其他全部输入原路径原字节保护，含 legacy.py、__init__.py、app.py、index.html、夹具、公开测试、回放器、PRD和runtime。新文件只写results。不得联网/安装/访问私有GT/登录/发消息/调用真实业务接口。可在本机127.0.0.1随机端口启动、调用并关闭本题HTTP子进程以实际验证，不连接其他服务。

repository使用实际SQLite连接；v1指旧表结构，原型未写PRAGMA（初始user_version=0），需幂等迁移后user_version=2且不丢旧成员。API与service执行服务器当前actor角色检查；管理员写入、manager仅改active非admin成员的name、viewer只读。create规范化邮箱并对全库唯一，更新/停用用原子版本比较；保护最后active admin。actor+request_key的相同规范命令仅写一次，改payload拒绝，失败可重试；当前actor仍须有权才可重放receipt。成员、审计、receipt同一事务，审计失败要完整回滚。保留GET /health、/legacy-export和无关功能，停用为软删除。

client.mjs提供createController(transport)、render(snapshot)，通过注入的真实HTTP适配层加载/session和/members，提交真实命令并刷新。snapshot不能假数据；失败保留form显示code，成功清空；按角色/行状态控制按钮并转义用户HTML文本。公开支持无外部import的async JS控制器及约定的Python标准库/项目模块；合法但超出profile或基础设施不可用时typed未评估，不伪造零分。这里实际评估HTTP、SQLite和JS/HTML语义，不把函数或HTML检查说成浏览器DOM或Harness证据。

python -B -m unittest discover -s tests_public检查原型窄基础回归；python -B acceptance.py --output results/tests.txt实际在独立目录/非项目cwd启动服务，执行12个固定公开验收和前端控制器，并读回SQLite、关闭服务器。详细协议、错误顺序及公开接口以contract.md为准。不要关闭合法导出/写功能逃避权限或并发检查。

交付四份实际实现源码和：
- /tmp_workspace/results/acceptance.xlsx：原生可编辑12项追踪；B2最终四源码source_digest，B3 tests.txt原字节SHA256；第6行A:E为id/priority/implementation_paths/test_ids/status，第7行起R01..R12唯一记录，含priority、对应owner模块与PUB-Rxx实际PASS/FAIL。可重排行、改表名、加自由说明；固定义务不能用padding稀释，不要求公式。
- /tmp_workspace/results/tests.txt：实际公开回归，含h052-acceptance-run/v1 fenced JSON及最终源码、保护回放器/夹具SHA与每个固定情境实际响应/持久化/JS观察；可如实FAIL，业务与真实性分开。
- /tmp_workspace/results/handoff.md：入口、预置依赖与验证边界，含contract指定source_digest/tests_sha256/entrypoint/real_browser=false/external_services=false的fenced JSON。不要声称未执行的真实Harness/浏览器/Judge/专家验证。

需在干净目录可以启动、跨进程重启保留写入，版本冲突/重复提交/权限拒绝不留下部分状态。自动检查按12项需求固定单位核验，迁移schema版本归R01、正向完整审计归R09；原始全量观察仍用于交付真实性核对。

## Expected Behavior

真实跨API/权限幂等服务/SQLite持久化/JS前端完成12项需求并逐项提供最终源码绑定的原生验收交付；L4仅设计估计。

## Grading Criteria

- [ ] `business_correctness`: 逐项实际HTTP/SQLite/JS实现12项PRD；源码/持久化/会话角色/前端展示与合法操作一致，按独立需求观察范围评分。
- [ ] `boundary_cases`: 独立反例验证权限、最后admin、并发版本/幂等双请求、规范重复、失败重试、原子审计回滚、UI文本/反馈和兼容入口；12个固定需求等权。
- [ ] `delivery_integrity`: 保护允许四源码外所有输入，三产物原生可解析且有可使用的12项表格。
- [ ] `evidence_binding`: 固定12个实际公开响应/SQLite/JS观察与最终四源码/夹具/回放器摘要绑定；xlsx状态、测试文本、交接一致，不以自述或padding获得真实性信用。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': '91a34be3897e16f1d5b9f97dc11065c40d8bc8e6fca0334b2a322f4deaa172c8', 'trusted_files.json': 'd68c069236229883b61587d8f88de73b02bc2f8505e63be619e0dc6742f92138'}.items():
        path = root / "gt" / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H052_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/05_Software_Engineering/05_Software_Engineering_task_012_prd_full_delivery
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 初始24个原数据PRD模型用例由Python与Node独立对齐，在修复参考前冻结；另两个当前actor/目标权限对旧receipt的边界在参考后独立补算，旧24条真值未变；manager active目标授权经root只读审查后按原PRD严格含义修正，v1源码/真值/控制完整保留。
- 两个私有并发单元实际发起双HTTP请求，允许两种独立枚举的线性化；不从线程顺序假定固定胜者。
- 按固定12项需求等权；schema仅R01、完整正向audit仅R09，其他需求拒绝额外审计，不把一次缺失audit重复扣遍所有成功写路径。
- 主参考为同事务服务/closure客户端，等价参考增加SQL CAS、哈希receipt和class客户端；原生xlsx由bundled artifact-tool生成、实际渲染看图，评分不声称视觉布局或公式重算。
- 使用现有Python stdlib和冻结Node，无安装；支持profile/VM不是OS安全沙箱，作者仅执行受控自有变体。
- 实际localhost HTTP/SQLite/JS控制器/HTML语义，不等同真实浏览器DOM、Harness、Judge或人工专家；900不是能力分墙钟门槛。
- 继承origin.review_basis中的人工复核是蓝图模型作者措辞，无人工专家记录，不构成人工背书。
- 原生OOXML读取profile支持1000 ZIP项/解压10MiB，超限合法文件typed未评估；正常12行表格远低于此限。
- 迁移夹具旧结构v1但原型未标记PRAGMA，初始SQLite user_version=0；公开Prompt已明确，最终为2。
