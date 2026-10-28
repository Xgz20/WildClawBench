---
id: general_hard_file_operations_task_001_cleanup_plan
name: 目录占用审计与可确认清理计划
category: file_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/cleanup_plan.json
      role: candidate_deliverable
    - path: results/report.md
      role: candidate_deliverable
dataset_report: {"category": "file_operations", "category_name": "文件与本地资源管理", "category_order": 3, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["data_processing"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["data_processing"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 目录占用审计与可确认清理计划

## Prompt

请只盘点本题 sandbox_tree，生成可交给用户选择和确认的清理计划。不得删除、移动、改写输入或执行计划；离线完成，不打开或跟随任何外部引用。

只读输入：
- /tmp_workspace/sandbox_tree/：80 个原创合成文件，包含缓存、业务记录、活动锁、同名和 Unicode 文件，以及标准 InternetShortcut（.url）/Apple webloc（.webloc）外部快捷方式。这些快捷方式是普通引用文件，不是文件系统 symlink；仅盘点引用文件本身，目标内容和占用未知。
- /tmp_workspace/protection_rules.json：允许扫描/清理范围、按优先级执行的分类规则和计划状态。
- /tmp_workspace/usage_snapshot.json：固定合成占用账本，含 file_id、路径、内容 SHA、fixture_bytes、业务角色、age_days、可再生性、active 锁、block_ids 和共享块 holders/external_pin。

只在 sandbox_tree 下枚举文件；两份根级 JSON 是明确允许读取的控制材料，不再扫描其它目录。按路径组件判断范围，cache2 不属于 cache。按 snapshot 的 active 锁保护锁文件及 target_file_id，不检查真实机器进程。按规则优先级将每个文件分成 cleanable（可清理）、needs_confirmation（需确认）、must_keep（必须保留），逐项写理由。cleanable 仅代表资格，不代表用户已选择或允许执行；全部仍处于待用户确认状态。

占用使用快照账本，不能拿小样本字节、本机 stat/du 或目录表面大小代替。每个 block_id 只计一次；某个给定文件集合只有在其包含某块全部 holders 且 external_pin=false 时才可能释放该块。未被选中的其它持有者和外部 pin 会阻止释放。bytes=null 是未知，不能填0。allocated_known_bytes 只加该文件关联的已知块；allocation_complete 表示关联块是否全部已知。freeable_if_alone_bytes 是仅该文件一个对象被未来清理时的可释放量，存在未知关联块则 null；它不是清理建议。总体 known_allocated_union_bytes 对全树已知块去重，unknown_block_count 单列，完整总占用如有未知就保持未知。cleanable_set_freeable_bytes 按你列为 cleanable 的全集计算潜在释放，未知可释放块则 null；这个假设全集不等于当前选择集，不得将逐项单独值简单相加。当前选择集必须为空，实际释放为0。

交付且仅交付 /tmp_workspace/results/ 下的两个原生文本文件：
1. cleanup_plan.json：可解析 JSON object。顶层包含 snapshot_id、input_sha256（两份控制 JSON 的原字节 SHA256）、confirmation="pending"、executed=false、selected_file_ids=[]、summary、files。
   summary 包含 file_count、known_allocated_union_bytes、unknown_block_count、cleanable_set_freeable_bytes、confirmation="pending"、executed=false。
   files 为80条逐文件对象：file_id、path（含 sandbox_tree 的相对路径，也可 /tmp_workspace/绝对路径）、sha256、decision、allocated_known_bytes、allocation_complete、freeable_if_alone_bytes、reason、evidence。evidence 用 usage_file_id 定位 usage_snapshot.json 的唯一 file_id，rule_id 定位 protection_rules.json 的唯一规则。每个外部快捷方式另写 follow_target=false、target_allocated_bytes=null。路径+编号+内容哈希共同定位身份，同名不能合并；NFC/NFD Unicode 等价可接受，不能折叠不同目录或不同编号。
2. report.md：面向用户说明占用口径、三类风险、共享块与未知量、活动锁/保护边界、外部快捷方式处理和下一步确认流程。将上述 summary 六项作为可核对的 Markdown 两列表（指标/值），或一个 fenced json 汇总对象；与 JSON 保持一致。其余正文自然表述，不以聊天代替交付。

JSON 键支持英文规范名或直译中文：文件编号/路径/内容哈希/分类/已知占用字节/占用完整/单文件可释放字节/理由/依据/快照文件编号/规则编号；顶层可用快照编号/输入哈希/确认状态/已执行/已选文件编号/汇总/文件或逐文件计划；汇总可用文件数/去重已知占用字节/未知块数/候选全集可释放字节；快捷方式可用跟随目标/目标占用字节。分类也接受可清理/需确认/必须保留，pending可写待确认。UTF-8 BOM、字段/行重排、数值等价的整数或数字字符串均可；未知用null，布尔用true/false。无需提交脚本或源码。

保留全部82个输入文件原字节，不增加或删除输入树成员；所有新交付只写 results。不访问真实用户路径、账号或服务，不联网、不发送消息、不调用付费接口。只根据本题材料判断，事实、推断与未知分清；不可虚构已扫描目标、已确认、已删除、已释放的结果。

## Expected Behavior

逐文件盘点80个合成文件并保留82输入；优先规则分类、独立共享块可释放量、未知与身份边界清楚，待确认无执行。L2为设计预估，模型难度与区分度未实测。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 只扫描给定目录，分类可清理、需确认和必须保留项目，生成逐文件计划；不得删除、移动或自动执行计划。
- [ ] `boundary_cases`: 逐项识别并正确处理：跟随外链；把目录大小当可释放空间；未经确认删除。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 针对“目录占用审计与可确认清理计划”的结论、取舍和未决项是否由本题材料/独立oracle支持。 核对报告与本题文件、优先级、共享块/未知量；不能因固定格式或措辞不同扣分。真实执行/外部访问只能结合实际轨迹判断，作者参考不证明模型行为。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 核对报告与本题文件、优先级、共享块/未知量；不能因固定格式或措辞不同扣分。真实执行/外部访问只能结合实际轨迹判断，作者参考不证明模型行为。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    trusted = {'grader.py': '830cea94f269f6d2851b5b163e167251ff7b4cdb4557c915757468c9a733d67e', 'trusted_files.json': '53ef8d853a05f0323d5cde2278ca10bf58fe955d566b651a0697cc5834deaa6c'}
    for name, digest in trusted.items():
        p = root / "gt" / name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H035_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {"business_correctness": result["business_correctness"], "boundary_cases": result["boundary_cases"],
            "delivery_integrity": result["delivery_integrity"], "evidence_binding": result["evidence_binding"],
            "overall_score": .55 * result["business_correctness"] + .25 * result["boundary_cases"]
                           + .15 * result["delivery_integrity"] + .05 * result["evidence_binding"]}
```

## LLM Judge Rubric

### Criterion 1: 决策依据 (key: decision_grounding, weight: 0.7)

判据：针对“目录占用审计与可确认清理计划”的结论、取舍和未决项是否由本题材料/独立oracle支持。 核对报告与本题文件、优先级、共享块/未知量；不能因固定格式或措辞不同扣分。真实执行/外部访问只能结合实际轨迹判断，作者参考不证明模型行为。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 交接可用性 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 核对报告与本题文件、优先级、共享块/未知量；不能因固定格式或措辞不同扣分。真实执行/外部访问只能结合实际轨迹判断，作者参考不证明模型行为。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
datasets/general-hard/workspace/file_operations/general_hard_file_operations_task_001_cleanup_plan
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 外层自动.75/语义.25；自动内部business .55 / boundary .25 / delivery .15 / evidence .05；不得把作者自动规则值宣称hybrid或真实模型成绩。
- 源先行Python oracle，Node从公开输入独立核算后才制作原生JSON/Markdown两参考。外部快捷方式不是真实symlink，不联网或跟随。
- 固定合成分配块不冒充宿主磁盘事实；全部素材原创、受控虚构，无线上原文或真实附件。
- 缺GT/helper/可信上下文为评测异常；候选漏交/改输入/伪执行按各自独立义务失分，不全局清零；瞬时动作需轨迹补证。
- 900仅任务元数据；四Harness、正式Judge、难度/区分度均未验证。
