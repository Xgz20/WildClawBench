---
id: general_hard_file_operations_task_002_versioned_archive
name: 版本文件归档与副本去重
category: file_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "file_operations", "category_name": "文件与本地资源管理", "category_order": 3, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 版本文件归档与副本去重

## Prompt

请将本题文件按业务分类和版本状态复制归档，保留完整来源清单，并说明冲突与未知。只复制，不移动、删除、覆盖或重写原始输入；离线完成。

只读输入：/tmp_workspace/incoming/（48个原创合成惰性文件），/tmp_workspace/filing_rules.md（公开分类、版本优先级、去重及异常规范），/tmp_workspace/protected.json（来源编号、原路径、原字节SHA256与规则文件保护摘要）。先完整读取filing_rules.md。文件后缀可能伪装，.pdf/.docx/.exe等名称不证明其真实格式或可执行性；不要运行文件，不需要Office或图像工具。

按实际JSON/CSV/XML/Markdown内容识别元数据，不能用扩展名猜业务分类。业务键按Unicode NFC归一，数字版本比较、审批优先级和带时区发布时间按规则执行。保留所有不同内容，包括superseded、并列conflict和unknown，不能只留当前版。按原始字节SHA256去重归档，一个不同SHA只保留一个普通副本；相同内容的每份来源仍在清单中独立占一行。同名异内容不可覆盖。归档中每个承载文件的直接父目录只容纳同一business_area和selection；目录名称及层级自由，可用英文或中文，不要求固定文件名。

仅在/tmp_workspace/results交付：
1. archive/：分类后原字节副本。不能用symlink、硬链接、重新序列化、重编码或改换行代替真实字节复制。
2. manifest.csv：UTF-8或UTF-8 BOM、逗号分隔RFC4180表，48份来源各一行。列为source_id、source_path、archive_path、sha256、business_area、document_id、version、state、issued_at、selection、duplicate_of、detected_format、reason_code；列/行顺序任意。source_path接受含incoming/的相对路径或/tmp_workspace/绝对路径；archive_path接受相对results的archive/...或/tmp_workspace/results/archive/...。SHA十六进制大小写等价。副本代表任选同SHA的实际来源，其duplicate_of空，其他同SHA行填代表source_id，所有同SHA行指向同一归档文件。文档版本可保留等价v前缀/尾0，发布时间可保留等价时区。未知元数据可填unknown、未知或空，不虚构。
   中文列名依次可用：来源编号、原路径、归档路径、内容哈希、业务分类、文档编号、版本、审批状态、发布时间、版本选择、重复来源代表、识别格式、原因代码；分类/状态/原因代码值沿用规则中的英文枚举。
3. exceptions.md：自然语言说明冲突与未知，附Markdown表kind | source_ids | detail或fenced json数组记录以便复核；中文列名可为异常类型 | 来源编号集合 | 说明。必须覆盖extension_mismatch、name_collision、version_conflict、unknown_item各相关来源；编号集合允许数组或逗号/空格/顿号分隔，同类可合并记录，顺序措辞不限；detail需有真实可用说明，不要求固定模板。完整语义以filing_rules.md为准。

原始48文件和两份控制材料保持原字节与成员不变；所有新交付只放results。不扫描真实用户目录，不读GT或评分说明，不联网、不访问账号、不发送消息、不调用付费接口，不执行输入文件。区分事实和未知，不能把重名当重复内容，不能把副本去重说成已经删除原文件。无需提交脚本/源码。

## Expected Behavior

按公开业务键/审批/数字版本/UTC时间规则，48来源完整映射，原字节去重分类复制，冲突和未知保留且可核；原输入不变。L2为设计预估。

## Grading Criteria

- [ ] `business_correctness`: 在results中按业务分类复制归档，区分同名不同内容与同内容不同名，保留来源和版本依据；原目录不做移动或删除。
- [ ] `boundary_cases`: 逐项识别并正确处理：按扩展名误认内容；重名覆盖；来源清单丢失。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': 'c99beb7d4dfb0d9745d4996ee297a6e63eebad0beaa5484e696600f2debe6810', 'trusted_files.json': 'f56c1ce38eae55a63de01a0b6a666ffbfcfd839c23d3e8c0015bd0394819c110'}.items():
        p = root / "gt" / name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H036_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    r = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {"business_correctness": r["business_correctness"], "boundary_cases": r["boundary_cases"],
            "delivery_integrity": r["delivery_integrity"], "evidence_binding": r["evidence_binding"],
            "overall_score": .55*r["business_correctness"] + .25*r["boundary_cases"] + .15*r["delivery_integrity"] + .05*r["evidence_binding"]}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/file_operations/general_hard_file_operations_task_002_versioned_archive
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 自动评分，内部.55/.25/.15/.05，四组成key分别映射七维；无语义Rubric。
- 输入先行Python oracle；Node只读公开输入独立解析/核算一致后才建参考。全部原创惰性虚构，不复制线上原文或真实用户附件。
- JSON/CSV/XML/Markdown实际字节由内容决定，伪装后缀不引入Office、图片或可执行依赖。
- 不以固定归档目录名、固定代表来源或异常逐字模板评分；完整来源集合、原字节副本、版本选择和真实路径/hash独立核验。
- 作者fixture自动值不是真实模型表现；模型复核非人工专家，未运行Harness/Judge/finalize；L2难度/区分度待实测。
- 缺GT/helper/可信上下文为评测异常，候选漏交/畸形/改输入按对应独立义务失分。900只为元数据。
