---
id: general_hard_software_engineering_task_007_bounded_performance
name: 匹配性能优化与结果等价验证
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

# 匹配性能优化与结果等价验证

## Prompt

请优化 /tmp_workspace/project/matcher.py 的匹配实现，减少重复全目录扫描，同时保持优先级、全部重复记录和稳定顺序。先阅读 /tmp_workspace/contract.md、/tmp_workspace/instrumentation.py、/tmp_workspace/profile.py 和 /tmp_workspace/runtime.json。所有数据为本题原创合成内容，离线完成，不需要真实账号、安装依赖或多线程。

只允许修改 project/matcher.py；它必须提供 match_records(queries, catalog)。参数是公开契约的只读序列，记录/查询提供 .id 和 .key(kind)，kind为email、phone、name_region。Key已按公开规则规范化，仅支持hash/等值，缺键为None；hash可能碰撞，不能当身份。优先级是email→phone→name_region，只有较高优先级无任何匹配才降级。返回每条原查询的 query_id、matched_by、row_ids；命中同级所有目录记录按原目录顺序保留，重复ID不去重，重复query_id也不能合并或重排。未匹配为unmatched及空列表。list/tuple的JSON等价表示允许。

输入另有 /tmp_workspace/baseline_matcher.py（不可改的原始慢速实现）、/tmp_workspace/fixtures/（三个公开夹具）、/tmp_workspace/benchmark.py 和 /tmp_workspace/tests_public/。除 project/matcher.py 外所有输入原路径/原字节只读；不得改计数器、基准、测试、夹具、协议或依赖，不扫描真实用户目录、不读私有GT。新文件只写results。

本题性能判据是可信侧实际累计的catalog_visits、query_visits、key_probes、key_hashes、key_equalities和id_reads之和。复制序列仍保留受控Key，C层list.index/count等比较也会计入等值次数。对结果等价的工作量用例，上界为32*(n+q)+4*m+128，n/q是输入长度，m是独立真值的输出ID总数。这个宽松线性上界不要求照抄某参考计数；准备/规范化/序列化不计入匹配核心。耗时只作信息，不作跨机器硬阈值，也不能把一次观测外推为CPU/内存或多线程保证。

采用公开纯函数profile真实验证：允许函数/辅助函数、collections/itertools/functools及future annotations、不可变模块常量与函数内局部结构。不得用类/装饰器、全局或nonlocal缓存、可变/动态默认参数、私有属性/反射、动态format字段遍历、IO/网络/进程/解释器接口。合法但超出该支持范围的实现会保留typed未评估，不虚构候选零分；该profile不是OS安全沙箱。不要跨调用缓存受控视图。优先改善索引和重复访问，而不是规避计数协议。

可用 python -B -m unittest discover -s tests_public 运行公开测试；用 python -B benchmark.py --matcher project/matcher.py --output results/benchmark.json 生成真实前后比较。交付：
- /tmp_workspace/project/matcher.py：实际优化源码。
- /tmp_workspace/results/benchmark.json：按公开schema记录原基准和当前源码SHA、协议SHA、三个固定公开用例的fixture和output的SHA及before/after实际六项计数、总工作量、状态和真实等价结论。耗时可保留但不作门槛，不得编造。JSON字段/行重排、BOM、SHA大小写、等价整数表示可接受；增加padding不稀释既有义务。
- /tmp_workspace/results/review.md：自由说明算法取舍、顺序/重复项、空间成本及验证边界，并用一个fenced JSON附algorithm_family（描述性非空文本）、before_source_sha256、after_source_sha256、public_case_ids、work_measure="h047-counted-keys/v1"、wall_time_is_gate=false和threads_required=false。不把静态分析、自述或原基准结果说成真实Harness轨迹。

不得联网、安装、登录、发消息、调用付费或真实业务接口。结论区分实际计数、推断与未知；900是任务运行元数据，不是能力分的墙钟截止。

## Expected Behavior

在可复核受控工作量内实现等价匹配，保持优先级、重复与稳定顺序；如实交付前后源码/输入/输出/计数证据及边界。L3仅设计预估。

## Grading Criteria

- [ ] `business_correctness`: 独立核全部固定源用例的优先级、降级、完整重复记录及目录/查询顺序；工作量用例也必须有语义真值，不能用错误结果规避正确性。
- [ ] `boundary_cases`: 在结果等价的固定规模用例中，以真实受控访问/hash/等值/ID读取之和验证公开线性上界；不信候选自报计数，不以耗时硬门槛评分。
- [ ] `delivery_integrity`: 除允许的matcher源码外保护原始基准、计数器、profile、测试和夹具；报告为原生可解析文本，额外输入写入按保护义务处理。
- [ ] `evidence_binding`: 来源、fixture、前后output SHA与实际六项计数/状态可重放核对；自由报告措辞及真实非等价不被强制改成参考答案。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': '8160cfe9e2eb9186d5ac9cea2a74ef98ade95cdf0dae58657331aedf8275f846', 'trusted_files.json': '70b8de75297d70689e32b0b01fed9b795f3da0ae5ccb7c62e16c453f31153ee0'}.items():
        path = root / "gt" / name
        if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H047_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {"business_correctness": result["business_correctness"], "boundary_cases": result["boundary_cases"],
            "delivery_integrity": result["delivery_integrity"], "evidence_binding": result["evidence_binding"],
            "overall_score": .55*result["business_correctness"] + .25*result["boundary_cases"] + .15*result["delivery_integrity"] + .05*result["evidence_binding"]}
```

## LLM Judge Rubric

## Workspace Path

```
datasets/general-hard/workspace/software_engineering/general_hard_software_engineering_task_007_bounded_performance
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 源先行Python原数据真值与Node独立复算16用例在两优化参考前冻结；上界来自n/q/m公式，未按参考计数收紧。
- 真实子解释器在公开纯函数profile和只读Key协议中执行候选；不是OS安全沙箱，作者仅执行受控自有变体。
- 工作量不等于完整CPU/内存成本；elapsed与900不作能力硬门槛，基础设施超时或合法未支持profile保留typed未评估。
- 语义覆盖全部16用例；非等价的工作量结论为not_assessed/neutral而非性能通过，语义错误仍在业务义务失分。
- 纯automated .55/.25/.15/.05；作者参考和实测控制不代表真实Harness/Judge/人工专家或L3区分度。
- 纯执行profile v2在首轮Worker前补齐公开Key的hash及map/filter/slice等价调用；源真值、原始案例、计数语义与n/q/m上界未改，v1源冻结和原参考回执保留。
