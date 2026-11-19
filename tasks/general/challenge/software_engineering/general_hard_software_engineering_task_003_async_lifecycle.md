---
id: general_hard_software_engineering_task_003_async_lifecycle
name: 异步任务取消与资源生命周期修复
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
dataset_report: {"category": "software_engineering", "category_name": "软件工程与故障修复", "category_order": 4, "checkpoint_capabilities": {"boundary_cases": ["code_generation", "reasoning_planning"], "business_correctness": ["code_generation"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 异步任务取消与资源生命周期修复

## Prompt

请修复 /tmp_workspace/project/worker.py 中并发批处理器的取消与资源生命周期问题，保持公开接口和正常业务语义兼容。先阅读 /tmp_workspace/contract.md；源码已有能完成正常批次的实际实现，不是待填空模板。/tmp_workspace/project/resources.py 是可观测的内存资源和提交provider，/tmp_workspace/tests_public/ 提供正常场景，/tmp_workspace/runtime.json 声明离线Python环境。

保留 BatchTimeoutError（TimeoutError子类）和异步接口 run_batch(items, pool, work, sink, *, concurrency=2, deadline=None)。完整成功的值保持输入顺序；正确调用实际work，不以给定样例结果写死答案。取消、work/provider错误、事件截止均不能伪装成功；失败后应停止并等待本批次其它工作收口。成功取得的不透明lease只能释放一次且必须等待释放完成，未取得的不能释放。异步release期间再次取消也不能遗留资源；终态提交在接受后等待ack时被取消或失败，不得再提交第二个终态。run_batch返回或抛出时，不遗留它持有的工作、截止观察或清理任务。

deadline由调用方asyncio.Event置位表示到期，独立批次不得互相取消。允许合法的调度、状态命名、内部函数和实现差异，不要求固定启动/完成顺序；详细语义与输入校验见公开contract.md。不使用机器相关的毫秒性能阈值。

交付：
- /tmp_workspace/project/worker.py：主要代码修复。
- /tmp_workspace/results/tests.txt：真实验证记录，写实际命令、退出结果、覆盖/未核边界，并包含最终worker.py完整SHA256；不得伪造已运行。
- /tmp_workspace/results/lifecycle.md：原始故障与成功、错误、取消、截止、终态和回收路径说明。

仅可修改project/worker.py，内部结构自由。project/resources.py、project/__init__.py、tests_public/、contract.md、runtime.json保持原字节；测试产生的__pycache__不作业务产物。所有额外报告只写results。使用已预置Python3.11+标准库，可运行 PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests_public -v；不安装依赖、不联网、不调用真实服务/账号、不发消息或真实办理。仅读取本题映射材料，不访问私有GT或评分说明。评分侧会独立执行最终冻结源码并绑定源码/测试/命令/returncode，自述成功不替代验证。

## Expected Behavior

在保持公开异步API和正常业务结果的前提下，修复成功、错误、取消、事件截止、提交与异步清理的生命周期，使每个已取得资源恰一次释放、终态至多一次尝试、兄弟任务及观察/清理工作完整收口。交付真实验证记录和失败路径说明。

## Grading Criteria

- [ ] `business_correctness`: 固定5项公开业务机会：成功顺序/并发/重入、work与取得资源错误的失败传播和收口、外部取消、事件截止、终态提交故障；通过独立不透明provider的实际执行判定。
- [ ] `boundary_cases`: 固定5项边界机会：等待acquire取消、异步清理中重复取消、终态接受后ack取消、取得前抛错、预置截止/空非法输入与批次隔离。边界观察资源/提交/隔离，不重复仅因同一个异常标签失分。
- [ ] `delivery_integrity`: 保护5份输入与修改范围、两份UTF8报告的存在和可读性；保护输入变化只影响对应保护义务，不全局清零或改变业务测试provider。
- [ ] `evidence_binding`: 独立实际执行的最终源码/可信测试/命令/returncode绑定，以及tests.txt的当前源码完整SHA256；不依据自述通过、补丁字符串或固定内部状态。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import json
    import runpy
    from pathlib import Path
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    rule = runpy.run_path(str(root / "gt/grader.py"))
    result = rule["grade"](transcript=kwargs.get("transcript"), workspace_path=str(root))
    print(json.dumps({"source_author_grade_return": result}, ensure_ascii=False))
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/software_engineering/general_hard_software_engineering_task_003_async_lifecycle
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 来源为受控原创内存并发工程，生产原型仅为工作形态改编；不依赖真实服务或外部包。
- L3为设计估计，900为运行元数据，不作为候选能力硬截止；测试/Worker保护独立配置。
- A=.55业务+.25边界+.15交付+.05证据；automated单分制，无语义Judge/hybrid。
- 独立oracle先于参考冻结；受控nonblind ownership-v2仅纠正重复异常标签扣分，公开语义和参考源码不变，旧oracle及失败control均保留。
- source-first原始工程公开正常测试2项通过，独立事件序列可复现7/10故障；不是空函数填补。
- 独立执行只用最终worker.py及可信原始__init__/resources，保护输入变化不会级联污染业务结果。
- 缺可信GT/helper/标准库或独立结果不可用是typed评测异常，不补能力零分；候选源码缺失、导入/断言错误按其实际不满足的业务机会计分。
- 所有结果绑定真实源码/测试/命令/returncode；不以参考补丁字符串、内部状态名或自述通过评分。
- 作者执行和控制不证明全部交错、真实服务、性能或四端Harness可用性；报告只机械验证可读性和源码绑定，不假称其全部语义已自动验证。
