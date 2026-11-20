---
id: 05_Software_Engineering_task_010_multiview_state
name: 分页筛选与多视图计数一致性
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

# 分页筛选与多视图计数一致性

## Prompt

请修复审批列表在全部、待审核和已通过视图切换后记录消失、总数不一致、旧响应覆盖新查询以及筛选后页码越界的问题。离线完成，数据均为原创合成内容。先读 /tmp_workspace/contract.md、/tmp_workspace/runtime.json 和 /tmp_workspace/profile.py。L4仅设计预估，900秒为运行元数据，不是能力分墙钟截止。

只允许修改 /tmp_workspace/project/api.py、project/store.ts、project/view.ts。它们分别提供 query_records(records, query, snapshot_version)、createState/reduce/getSnapshot 和 present(snapshot)，接口和完整输出字段遵守contract.md。全部其他输入原路径/字节只读，新文件只写results。不得修改夹具、公开测试、回放器、profile或依赖。不得读私有GT、联网、安装、登录、发消息或调用真实业务接口。

API须先按term筛选全量记录，统计term范围内all/pending/approved，再按状态得到total，按(createdSeq,id)稳定排序后分页；all含rejected。规范化仅转换ASCII大小写/trim ASCII空白；响应分别保留规范化请求query和服务器夹紧的实际page，空结果page/lastPage均1。保持输入不变。

Store中筛选条件规范值改变须重置page1，页面单独改变保留请求页。只有当前opaque token、匹配请求query和不低于已知修订的响应可接受，采用服务器实际page；重复/旧通知、旧失败、同查询的旧刷新响应不得破坏新状态。通知与服务器提交是两件事，未通知未来状态不当成客户端已知。不同Store实例互不污染。缓存或清空均可，但等待、失效、失败、错查询或旧版本时不能展示旧数据，也不能把未知计数伪装为0/空结果。成功空结果才empty=true；完整行/total/tab counts/pageCount必须来自同一可用响应，不是只改文字。

候选在公开支持的纯Python/同步JSON TypeScript函数profile中实际执行。无npm或外部TS模块，仅store/view彼此相对导入及可擦除原生TS语法。合法但超出支持profile或基础设施不可用时保留typed未评估，不编造零分；该VM/profile不宣称OS安全沙箱。

python -B -m unittest discover -s tests_public检查原型窄正常路径；python -B replay.py --output results/scenarios.json执行两个固定公开情境。fixtures/records.json提供初始记录及修订事件，public_scenarios.json注入request/capture/deliver/commit/notify次序。回放器实际执行三份当前源码并记录SHA、冻结Node身份、夹具SHA、请求/响应及每步view。不得伪造输出或写死参考答案；可如实报告失败，报告真实性和业务正确性分开评估。

交付三份实际修复源码，以及 /tmp_workspace/results/scenarios.json（h050-actual-replay/v1）。JSON键/情境行顺序、BOM、SHA大小写可等价；固定情境内步骤顺序和数量有意义，额外padding不稀释既有义务。这里的UI观察仅为文本/状态函数回放，不存在真实DOM、浏览器、网络或Harness交互，不把函数回放自述为真实产品运行。

## Expected Behavior

实际修复分页/筛选/计数及请求竞争、事件失效的跨Python/TypeScript一致性；如实交付可回放绑定证据。L4仅设计预估。

## Grading Criteria

- [ ] `business_correctness`: 独立API过滤/稳定分页/term范围统计、普通Store流转与View完整行和服务器计数；Store使用源真值响应避免后端错误重复扣分。
- [ ] `boundary_cases`: 独立夹页/空集/类型/Unicode、乱序/同查询刷新/版本栅栏/筛选重置/重复旧通知/实例隔离，以及未知展示保护。
- [ ] `delivery_integrity`: 保护三个允许源码外全部输入路径字节，新文件仅results，交付原生可解析scenarios.json。
- [ ] `evidence_binding`: 三份实际源码与冻结引擎/Node/夹具SHA绑定，两个固定公开情境实际请求响应与每步展示一致，允许诚实失败而不强迫参考结果。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': 'df318b923733f56f4bebceaa4c6e7d49f3f8c284832b4f1d6084b0e0be33ab8d', 'trusted_files.json': '49196eb36fa4be8fcc3d034a01186d9e055669f7023eca6e01238656dcb97f5f'}.items():
        path = root / "gt" / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H050_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/05_Software_Engineering/05_Software_Engineering_task_010_multiview_state
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 初始37个单元在参考前由Python和Node原始源计算对齐冻结；当前39个含两个按既有contract补充的边界单元，旧真值未变且独立双算修订回执保留。
- 组合回放为实际函数级文本/状态证据，无DOM/browser/Harness/Judge或人工专家证明。
- 源阶段v1的case ID重名在参考前修为v2，旧冻结回执保留，当前39个ID严格唯一。
- 运行时冻结 bundled Node的路径/版本/可执行SHA，使用既有Python和stdlib，未安装依赖。
- 合法profile未支持、可信上下文缺失或基础设施超时均typed未评估，不虚构候选零分；900和模块保护超时不作为能力分门槛。
