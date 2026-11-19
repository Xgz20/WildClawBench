---
id: general_hard_file_operations_task_006_visual_file_mapping
name: 截图目录结构与实际文件对应
category: file_operations
timeout_seconds: 900
modality: multimodal
attachment_size_limit_mb: 5
difficulty: L4
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "file_operations", "category_name": "文件与本地资源管理", "category_order": 3, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 截图目录结构与实际文件对应

## Prompt

请完成以下工作：理解截图中的父子层级、选中项和同名对象，仅把指定对象复制到results；列明视觉证据，不进行删除或系统级UI操作。

输入材料：
- /tmp_workspace/screenshots/：3张文件管理器截图，含树状缩进、选中状态和相似名称
- /tmp_workspace/source_tree/：对应的30个合成文件
- /tmp_workspace/copy_request.md：根据截图选择的业务说明

交付：
- /tmp_workspace/results/selected_files/：正确对象的副本
- /tmp_workspace/results/mapping.json：截图区域、实际路径和选择依据

约束：
- 仅读取本题exec映射到/tmp_workspace的材料；GT和评分说明不提供给候选。
- 不访问真实账号、不发送消息、不调用真实付费接口；输入和保护文件保持不变。
- 结论区分事实、推断和未知；不得虚构缺失信息。
- 所有新交付写入/tmp_workspace/results；原输入只读，不删除或覆盖。
- 离线完成，不访问网络。
- 必须读取所给原始图片并说明图像区域与判断关系；输入不提供答案型OCR文本或隐藏答案。

# 交付结构

mapping.json为UTF-8 JSON object，含selections数组和source_images数组。source_images逐图记scene_id、image_path和原PNG的sha256；selections逐条含scene_id、source_path（含source_tree的相对路径或/tmp_workspace绝对路径）、sha256、target_path（相对results的selected_files/...或/tmp_workspace/results绝对路径）、visual_evidence对象。visual_evidence至少包含active_panel、selected_row和ancestor_chain三个证据角色，每个角色以bbox或polygon表达图像局部，ancestor_chain允许多个区域；各区域用原像素坐标或声明coordinate_space=normalized的0–1坐标，说明图像ID、可见对象和选择关系。

原始图为1800×1100；矩形用[x0,y0,x1,y1]，多边形用[[x,y],...]，坐标必须在图内并定位实际区域。可自定区域ID并建立可解析表；允许合理中文字段、UTF-8 BOM、字段/行重排和绝对映射路径。未知不得伪造，无法定位时说明范围和原因，不能对不确定对象全选。

所有35个输入保持原字节和成员；selected_files只保存正确普通副本，不创建链接或运行内容。格式与坐标本身不证明实际看图，正式运行需结合实际轨迹；本题不提供OCR文本、活动面板索引或选中路径答案。

## Expected Behavior

理解截图中的父子层级、选中项和同名对象，仅把指定对象复制到results；列明视觉证据，不进行删除或系统级UI操作。 Original PNG observations must recover complete ancestors, distinguish the blue-frame active list, selected fill and cursor-only rows; copy each original byte object once and bind every scene mapping.

## Grading Criteria

- [ ] `business_correctness`: 对象副本与场景路径映射分别按集合precision/recall的F1等权计分；额外与重复交付只在本项计入，SHA十六进制大小写等价。(weight 0.55)
- [ ] `boundary_cases`: 三类局部视觉角色（活动面板、选中行、完整祖先链）的覆盖均值；同一选择的重复矛盾几何按最保守声明，不取最佳；无额外集合精度扣分。(weight 0.25)
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。 (weight 0.15)
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。 (weight 0.05)

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib,runpy
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("H040_DECODER_UNAVAILABLE:Pillow") from exc
    root=Path(kwargs.get("workspace_path") or "/tmp_workspace")
    helper=root/"gt/check_visual_mapping.py"
    if not helper.is_file() or hashlib.sha256(helper.read_bytes()).hexdigest()!="a5af7b92e4de64e499cf398dbd747778db5091234c684705ddb25630e666f5ea":
        raise RuntimeError("H040_TRUSTED_HELPER_MISSING_OR_CHANGED")
    result=runpy.run_path(str(helper))["grade"](root)
    return {
        "business_correctness":result["business_correctness"],
        "boundary_cases":result["boundary_cases"],
        "delivery_integrity":result["delivery_integrity"],
        "evidence_binding":result["evidence_binding"],
        "overall_score":result["overall_score"],
    }
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/file_operations/general_hard_file_operations_task_006_visual_file_mapping
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- Non-blind source-first GT reconciles two frozen independent model annotations; all author/reviewer work is model work, not human expert validation.
- Only endpoint artifact/integrity/role geometry is mechanically checked; actual image viewing and transient input writes require execution trajectory review.
- Difficulty L4 is a design estimate, unvalidated by real multi-model/multi-Harness runs.
- Runtime uses locked preexisting Pillow decoder; missing GT/decoder and valid unsupported geometry retain typed infrastructure errors. No network, install, Office, Harness, Judge or finalize used.
- Root review v2 reproduced full-directory and mapping enumeration at old A=.875; new contract uses set F1 and conservative duplicate geometry. Old author controls are retained and not relabeled as v2 runs.
