---
id: general_hard_file_operations_task_005_split_bundle_restore
name: 分包恢复与本地工作台完整性交接
category: file_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: automated
tags:
  - custom
  - general-hard
  - general-challenge
dataset_report: {"category": "file_operations", "category_name": "文件与本地资源管理", "category_order": 3, "checkpoint_capabilities": {"boundary_cases": ["reasoning_planning"], "business_correctness": ["data_processing"], "delivery_integrity": ["verification_delivery"], "evidence_binding": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-challenge"}
---

# 分包恢复与本地工作台完整性交接

## Prompt

请识别同版分包，按发行清单在新目录恢复完整离线资料工作台，保留现有笔记，核验原字节、相对资源与本地可用性；不要重新生成应用、资料或缺片。

只读输入：/tmp_workspace/parts/有3个同版ZIP和1个旧版干扰ZIP；/tmp_workspace/release_manifest.json给出发行ID/版本、当前分包整体SHA、PART_INFO、payload_prefix、每成员原字节大小/SHA、来源、单层根、笔记冲突策略及本地功能样例；/tmp_workspace/existing_notes/是必须保留的原创虚构用户笔记。输入保持原字节，不移动、删除或覆盖。按真实元数据与SHA判断，不按文件名猜同版；同版重复路径只有字节相等才合并，否则阻止并报告。不要执行不明归档代码或联网安装。

只在/tmp_workspace/results交付：
1. restored/：完整原生离线目录。剥离每个当前分包各自声明的payload_prefix，index.html直接位于restored根，不能多套Workbench等包装目录。所有发行成员原字节恢复，大小写/Unicode路径严格依清单。原existing_notes/<path>映射为user_notes/<path>并保留原路径/大小写/原字节；用NFC+casefold检测与发行成员的冲突，用户优先，发行原成员旁存distribution_templates/<发行原路径>，两份都不能丢。不能整体覆盖用户笔记，也不能把旧版资料补入新版本。
2. restore_audit.json：JSON object，含release_id、version、selected_parts（part_id/path/sha256）、excluded_parts（path/release_id/reason）、members（release_path/target_path/sha256/bytes/part_ids）、notes（source_path/target_path/sha256/bytes）、conflicts（release_path/retained_user_path/release_saved_as/kind）、resource_checks、input_sha256。conflicts.kind为exact_path或casefold_path。part_ids为实际合法来源分包的非空集合，相同发行重复成员任选一个或保留多个真实来源都可。目标路径相对restored根，也接受/tmp_workspace/results/restored/绝对路径；输入路径相对/tmp_workspace，或其等价绝对路径。
   resource_checks按实际恢复内容列source/kind/raw_ref/target/fragment/status=resolved；source与target相对restored根。可每边一行，也可按source分组、links数组列子边，status可放父组。kind为描述性类型（href/src/css_url/markdown/catalog_href等），关系绑定以真实source/target/片段为准，不按说明措辞评分。HTML href/src、CSS url/import、Markdown和catalog（base=root）均要核验，资源按精确大小写存在且HTML片段有效。所有输入原字节SHA放input_sha256。
3. handoff.md：写清精确入口、选版/排除、单层根/相对资源、笔记冲突去向与实际核验范围。入口可双击restored/index.html，以file URL离线打开；原发行内嵌目录与受控经典JS不需服务器、账号、fetch/CDN或外部依赖。以Markdown两列表或fenced JSON附摘要release_id、entrypoint=index.html、release_member_count、note_count、restored_file_count、resource_edge_count。正文措辞自由。

本题要求恢复原字节和相对资源图，不要求候选重新写前端。可静态核原字节/资源图并如实写浏览器not_run/unknown；若实际打开本地页面再验证筛选/空状态/清空/导航，应依据真实工具结果，不把静态检查说成应用已启动。已恢复原发行脚本与数据且资源图全部一致，才有离线功能一致性的依据。不得执行自行合成的缺片或任意未知归档脚本。所有源代码/素材均是本题受控原创内容，不需访问真实服务。

允许JSON字段/成员重排、BOM、Unicode NFC/NFD、SHA大小写、整数等价和版本v前缀。中文键可用发行编号/版本/选用分包/排除分包/成员/笔记/冲突/资源核验/输入哈希、分包编号/路径/内容哈希/发行路径/目标路径/字节数/来源分包/原路径/保留用户路径/发行旁存路径/类型/来源/原引用/目标/片段/状态/链接；摘要可用入口/发行成员数/笔记数/恢复文件数/资源关系数。所有真正的原字节与必要固定相对路径不因输出表示等价而改变。

仅读本题exec映射输入，不读GT或评分说明，不扫描真实用户目录，不联网、不访问账号、不发送消息或调用付费接口；所有新交付只放results。源输入保持原字节，结论区分实际核验、推断与未知。无需脚本/源码之外的重新开发成果。

## Expected Behavior

同版分包与原始成员按SHA/版本/前缀恢复到单层离线工作台，现有笔记原路径原字节优先并旁存冲突模板；实际相对资源图和静态功能一致性可复核，浏览器未运行不伪称启动。L4预估。

## Grading Criteria

- [ ] `business_correctness`: 识别同版分包，按清单在新目录恢复可离线使用的工作台，保留用户笔记，验证相对链接和资源，不能重新生成或整体覆盖内容。
- [ ] `boundary_cases`: 逐项识别并正确处理：混合不同版本；多嵌套一层致链接失效；覆盖用户笔记。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': '381d52b15bdbde08549ad78ad61b2013d5bc8dbb787f5eee25d96195f344ff76', 'trusted_files.json': 'f8206c5a5dae621c20d321ca537220ce6df71936bb5b2ad6cdb8a34822b4ff43'}.items():
        p = root / "gt" / name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H039_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    r = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {"business_correctness": r["business_correctness"], "boundary_cases": r["boundary_cases"],
            "delivery_integrity": r["delivery_integrity"], "evidence_binding": r["evidence_binding"],
            "overall_score": .55*r["business_correctness"] + .25*r["boundary_cases"] + .15*r["delivery_integrity"] + .05*r["evidence_binding"]}
```

## LLM Judge Rubric

## Workspace Path

```
workspace/general/challenge/file_operations/general_hard_file_operations_task_005_split_bundle_restore
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 纯automated .55/.25/.15/.05，原生恢复工作而非前端开发主任务；不执行改写候选脚本，不设Office/HTML runtime绕过。
- 源先行原始发布/笔记SHA与资源图oracle，Node原ZIP/CRC/prefix/同版和独立图/数据逻辑核验，参考之前一致。
- 作者仅对已认证自有原始参考做真实本地file URL Playwright+既存headless shell验收7项，无服务/安装/下载/外部请求；这不是候选Harness运行。
- 恢复原字节+固定相对拓扑支撑原发行可用性一致；候选是否真实打开页面必须依据实际轨迹，不能由静态通过宣称已启动。
- 同版重复路径可用任一真实相同来源，不绑参考源码/格式/手写说明；缺GT/helper为评测异常，不当候选0。
- 模型作者和独立计算不是人类专家；无真实Harness/Judge/finalize，L4/区分度待实测，900仅元数据。
- 私有规则v2修复错位原字节和虚构审计目标漏检；基础产物本身已错时规范目标为not_assessed，不冒充绑定通过或重复扣分。v1快照/失败与v2真实Worker控制分开保留。
