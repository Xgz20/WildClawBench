---
id: general_hard_file_operations_task_003_nested_archives
name: 嵌套压缩包的受限提取与冲突处理
category: file_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: automated
tags:
  - custom
  - general-hard
dataset_report: {"category": "file_operations", "category_name": "文件与本地资源管理", "category_order": 3, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 嵌套压缩包的受限提取与冲突处理

## Prompt

请按公开受限提取规范处理六个ZIP，只把允许成员提取到results/staging，并提交逐成员审计。所有源归档和规则保持原字节，不移动、删除或覆盖，不执行成员、不联网、不创建链接。

只读输入：/tmp_workspace/archives/下六个ZIP（含UTF-8/GB18030中文编码、嵌套ZIP、同名目录、Unicode/大小写/重复成员名、越界测试条目、ZIP内链接类型、大小/累计预算/深度限制及损坏长度/CRC），和/tmp_workspace/extraction_policy.md。先完整读取规范，再按其固定顶层编号、中央目录原序号、来源链、编码、目标根、mNNNN__命名和__nested__/mNNNN子容器根执行。恶意成员仅是原创惰性测试文本，禁止直接对原始输入extractall。

普通成员上限4096字节、子ZIP上限8192字节、每顶层接受总额12288字节、子容器最大depth=2；按规范先检查名称/路径/类型，再声明值和剩余预算，实际解压受限到上限+1。不能只相信头部声明，也不能让失败中断后续合法成员。嵌套由真实ZIP签名判断，不看扩展名；拒绝子容器本身要审计，但不列不可知内部成员。UTF8标志bit11未置位时本题使用GB18030，原始字节名称仍以raw_name_hex保留。原始危险名称只记录，不当作可写路径。

交付仅限/tmp_workspace/results/：
- staging/：按规范实际安全提取的普通文件和目录，保持层级及来源隔离，拒绝项不落盘；不得执行任何文件或创建symlink/硬链接。
- extract_audit.json：JSON object，含executed=false（表示未执行归档成员内容，安全提取本身仍须实际完成）、input_sha256（6个ZIP和规范的原字节SHA256）、members数组、unvisited_containers数组。每成员字段为member_id、container_id、member_index、top_archive、archive_sha256、raw_name_hex、decoded_name、depth、declared_bytes、compressed_bytes、action、reason_code、target_path、actual_state、actual_bytes、sha256。动作、原因和状态枚举、声明/实际字节口径及固定目标路径均以extraction_policy.md为准；拒绝target_path必须null。路径可用相对results的staging/...或/tmp_workspace/results/staging/...。解码失败的decoded_name=null；未读取/损坏异常未知的字节与哈希用null，不填0。允许正常工具在真实损坏项无法取得实际长度时记录integrity+unknown及实际异常类型；不能把正常成员无理由拒绝或把未知能力冒称成功。unvisited_containers每项member_id/reason_code即可。

允许JSON字段/成员重排、UTF8 BOM、数值等价整数/数字字符串、Unicode NFC/NFD和十六进制大小写。中文键可用：已执行/输入哈希/成员/未展开容器/成员编号/容器编号/成员序号/根归档/容器哈希/原始名称十六进制/解码名称/深度/声明字节/压缩字节/动作/原因代码/目标路径/实际状态/实际字节/内容哈希；枚举值沿用规范英文。无需脚本或源码交付。

只读本题exec映射到/tmp_workspace的材料，不扫描真实用户路径，不读取GT或评分说明，不访问账号、服务或付费接口，不发送消息。所有新输出只放results；输入和目标根外路径不得改动。事实、推断与未知分清，不伪造已解压、已执行或越界文件结果。

## Expected Behavior

源归档只读；按原始中央目录来源链、编码、安全路径与声明/实际字节/累计/深度约束提取并逐项审计；损坏项允许有证据的typed unknown，后续正常项继续。L3为设计预估。

## Grading Criteria

- [ ] `business_correctness`: 仅将允许成员提取到results/staging，保持来源层次，拒绝越界及超限条目，不能执行归档内文件，提交逐成员结果。
- [ ] `boundary_cases`: 逐项识别并正确处理：ZipSlip越界；编码名冲突覆盖；失败时无逐项结果。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': '3a084ab31e272f08718a06b4b49ac4226ce112d501fbf9816bdbff62a48a4451', 'trusted_files.json': 'dab69b1333726e4773371a2a1ad6a2c602239fc5fe5d5a6767d251ffd49b0c2f'}.items():
        p = root / "gt" / name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H037_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    r = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {"business_correctness": r["business_correctness"], "boundary_cases": r["boundary_cases"],
            "delivery_integrity": r["delivery_integrity"], "evidence_binding": r["evidence_binding"],
            "overall_score": .55*r["business_correctness"] + .25*r["boundary_cases"] + .15*r["delivery_integrity"] + .05*r["evidence_binding"]}
```

## LLM Judge Rubric

## Workspace Path

```
datasets/general-hard/workspace/file_operations/general_hard_file_operations_task_003_nested_archives
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 纯automated，内部权重.55/.25/.15/.05，四组成key独立映射，不重复映射overall。
- 源先行已知ZIP成员图oracle；Node不同中央/本地头解析、CRC/GB18030及受限zlib路径独立核原始成员与允许/拒绝集合，参考之前完成。未安装包。
- 所有恶意路径/链接仅ZIP元数据与惰性文本，不创建真实链接或执行载荷；作者参考只在外部h037/reference受限安全写入，未用extractall。
- CRC/声明损坏可在两个源绑定成员上合法记录unknown/null，与actual_size低界观察等价；不是对正常项宽泛接受未知。
- 作者Workerfixture、源模型复核不证明真实Harness效果或人工专家审核；不运行Judge/finalize，L3难度/区分度待实测，900仅元数据。
- 完整输入/GT文件清单与SHA交接给root；若ZIP后缀被Git忽略，保持原素材，root只按预期allowlist处理。
