---
id: 05_Software_Engineering_task_001_delimiter_validation
name: 导入校验的错误分流与跨格式兼容
category: software_engineering
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "software_engineering", "category_name": "软件工程与故障修复", "category_order": 4, "checkpoint_capabilities": {"boundary_cases": ["code_generation"], "business_correctness": ["code_generation"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 导入校验的错误分流与跨格式兼容

## Prompt

选课导入CLI有分隔符校验和错误分流缺陷，请依据本地契约修复，同时保留合法旧输入的输出行为。

先读 /tmp_workspace/contract.md。源码为 /tmp_workspace/project/importer.py，公开回归测试为 /tmp_workspace/project/test_public.py，已有样本位于 /tmp_workspace/fixtures/（包含UTF-8/BOM/CRLF及需逐字保留的内容）。文件列分隔和课程字段内分隔是两层语法，不能混在一起处理；遇到多项错误须按契约阶段、记录顺序和字段优先级返回正确错误码，不能吞错返回空成功。

只允许修改 /tmp_workspace/project/importer.py。不得修改公开测试、样本或contract.md，不新增其它项目文件，不联网、不安装依赖。Python 3.11+标准库已可用；修复方式不限，不能按样本名或测试环境写死答案。

交付最终源码，以及 /tmp_workspace/results/test_report.json 和 /tmp_workspace/results/compatibility.md。按contract.md运行公开测试并保存stdout/stderr日志，报告绑定最终源码SHA与真实运行结果；测试失败也要如实记录，不把旧源码记录当作修复后记录。兼容说明使用“修复”“兼容”“验证范围”三个二级标题，说明错误优先级、原文保留、CSV/TSV行为及实际验证范围。允许Python自动生成__pycache__，其它新文件只写results。

## Expected Behavior

按contract.md的明确阶段和记录序号解析CSV/TSV及课程字段。合法输入保持原文与输出结构，非法输入返回正确首个业务错误；保护文件不改。独立运行最终候选源码核对49个表驱动样例和7个原始公开测试，核验交付结构及源码绑定。

## Grading Criteria

- [ ] `business_correctness`: 修复分隔符校验和错误消息分流，合法旧输入结果不变，错误输入按最早业务错误分类，禁止修改公开测试或输入样本。
- [ ] `boundary_cases`: 逐项识别并正确处理：吞掉错误默认成功；改测试迎合；修一个格式破坏旧格式。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs):
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    result = runpy.run_path(str(root / "gt" / "grader.py"))["grade"](root)
    return {
        "business_correctness": result["business_correctness"],
        "boundary_cases": result["boundary_cases"],
        "delivery_integrity": result["delivery_integrity"],
        "evidence_binding": result["evidence_binding"],
        "overall_score": result["overall_score"],
    }
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/05_Software_Engineering/05_Software_Engineering_task_001_delimiter_validation
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- H041；难度L2为预估。输入、源码、样本和测试均为本次独立合成，不含线上原文或用户附件。
- 自动权重：business_correctness 0.55、boundary_cases 0.25、delivery_integrity 0.15、evidence_binding 0.05。业务项按分隔符拒绝修复/跨格式拒绝修复/阶段及记录分流分别0.35/0.25/0.4汇总；边界按合法CSV/合法TSV/Unicode去重/其它错误回归分别0.25/0.25/0.2/0.3汇总，各族内等权。保护文件被改时边界、交付及证据项归零。
- 来源与能力沿用general-hard蓝图，具体输入契约以本题contract.md为准。仅本地作者控制通过，尚未进行四端、容器Worker和难度区分度实测。
- 完整可复算作者控制见私有gt/validate_authoring.py与gt/authoring_validation.json；测试记录证明源码、日志与独立复跑结果一致，不构成原启动时刻的加密证明。
