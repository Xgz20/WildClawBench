---
id: general_hard_software_engineering_task_008_sse_state
name: 流式响应中断与重连状态一致性
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

# 流式响应中断与重连状态一致性

## Prompt

修复流式响应中断与重连状态一致性，只修改这三个文件：
- /tmp_workspace/project/stream.py：SSE/增量UTF-8解码；
- /tmp_workspace/project/state.py：当前请求的连续序号、重放去重、正文/推理与终态归并；
- /tmp_workspace/project/render.py：Markdown/推理/完成态一致输出。

先读 /tmp_workspace/protocol.md 的完整离线接口合同。/tmp_workspace/fixtures/events.jsonl 包含乱序、重放、分片、错误及断开/重连steps，所有字节以hex提供，无需网络。/tmp_workspace/project/test_public.py 为保护的基础旧接口测试；/tmp_workspace/tools/replay.py 是实际重放/测试工具；/tmp_workspace/requirements.lock 声明只需Python3.11+标准库，/tmp_workspace/project/__init__.py 同样不可改。

正文和推理必须独立保留，Markdown原样输出。每个字节step和每次事件后的中间状态都须正确，不能只拼对最终文本；任意UTF-8/CRLF跨块、多行data及同块多事件均按合同解码。断开丢半帧却保留会话历史，重连重放不能重复拼接；future序号先缓冲，done有缺口不能提前成功。失败/取消/中断不能显示成功，终态不能被后续帧或重连覆盖。规范化同ID/同seq冲突、外请求隔离及快照独立性以protocol.md为准，内部状态布局不限。

完成后实际运行 python -B tools/replay.py，交付 /tmp_workspace/results/replay.json：保留固定scenario_id的每步decoded、每个事件后的states、step末state/render、最终结果，以及最终三源码/输入SHA和真实公开测试命令、returncode、完整输出。更改最终源码后必须重跑。不得漏场景改变分母、写死观察结果或自述已测。公开基础测试可能在原工程已全绿，不能代替中间状态与重连边界验证。

仅用本题exec映射到/tmp_workspace的材料，GT不提供给候选。只改上述三源码，不改保护测试、工具、夹具、合同和依赖锁，不新增源码；所有报告写results，自动__pycache__/*.pyc可忽略。离线，不安装依赖、不访问真实账号、不发送消息、不调用网络或真实付费接口。结论区分事实、推断、未知，不虚构缺失信息。

## Expected Behavior

仅修三源码，在每个事件/字节前缀维持独立正文/推理和正确状态，重连去重、连续序号、完成/失败/取消均一致；交付绑定最终源码和真实重放的完整报告。

## Grading Criteria

- [ ] `business_correctness`: 固定12场景：正文/推理分离、Markdown、UTF-8/SSE帧、中断、错误、乱序和终态；每场景.5最终状态/渲染+.5固定步前缀准确率，不能只核最终文本。
- [ ] `boundary_cases`: 固定20场景：重放去重、待处理重复、future done、半帧/半UTF-8重连、SSE id、冲突/外请求、错误/成功/取消粘性、非法事件和快照回写；固定前缀分母。
- [ ] `delivery_integrity`: 三源码可读可解析平均(.40)、保护输入和修改范围(.40)、replay报告可解析(.20)；不把单一协议根因扩为全项清零。
- [ ] `evidence_binding`: 最终三源码及events输入SHA(.40)、固定10公开场景与当前源码独立重放一致(.40)、真实公开测试命令/返回码/状态(.20)。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import runpy
    from pathlib import Path
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    helper=root/"gt/grader.py"
    if not helper.is_file() or helper.is_symlink():raise RuntimeError("H048_GT_REQUIRED: grader.py")
    result=runpy.run_path(str(helper))["grade"](workspace_path=str(root),transcript=kwargs.get("transcript"))
    return {"business_correctness":result["business_correctness"],"boundary_cases":result["boundary_cases"],
            "delivery_integrity":result["delivery_integrity"],"evidence_binding":result["evidence_binding"],"overall_score":result["overall_score"]}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/software_engineering/general_hard_software_engineering_task_008_sse_state
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 严格对应蓝图order48，L4为设计估计未做多模型验证；900秒仅为元数据。
- 自动总规则=.55业务+.25边界+.15交付+.05证据；场景12/20、字节/动作前缀899及公开场景10均冻结分母。每场景.5最终+.5逐步前缀，错误/缺输出不缩小分母。
- 源输入/899前缀oracle在reference前由writer派发偏移+关系前缀归并与实际增量UTF-8/SSE+命令式缓冲状态机两条计算路径核验一致；同一作者计算，不宣称独立人类/盲审。
- 首版CRLF派发偏移错误在源先行复核中被发现并保留失败，再于参考前修正；输入字节不变。参考/等价实现不进入GT或规则，不匹配参考源码字符串。
- 候选解码/状态/JSON/运行错误依固定行为机会失分；GT/可信脚本缺失或SHA不符、解释器不可用为typed评测异常，不补能力零分。
- 额外观察元数据忽略，正文/推理原样、bool/int状态类型及前缀有语义；纯渲染输出JSON不等于真实GUI或Harness实测。
- 作者走真实managed prepare/run-rules/normal和独立去runtime archive保管，不运行Harness/Judge/finalize；通用SHA回执仅证明保管。
