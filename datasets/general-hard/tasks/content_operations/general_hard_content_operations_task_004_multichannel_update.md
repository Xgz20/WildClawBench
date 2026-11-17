---
id: general_hard_content_operations_task_004_multichannel_update
name: 产品事实变更后的多渠道内容同步
category: content_operations
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.65
  llm_judge: 0.35
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/website.html
      role: candidate_deliverable
    - path: results/social.docx
      role: candidate_deliverable
    - path: results/email_en.md
      role: candidate_deliverable
    - path: results/change_map.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  office_render: true
  html_render: true
dataset_report: {"category": "content_operations", "category_name": "内容创作与运营", "category_order": 6, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["content_generation"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["verification_delivery"], "llm_judge.decision_grounding": ["content_generation"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 产品事实变更后的多渠道内容同步

## Prompt

请完成以下工作：更新三个渠道内容，处理事实更正和表述冲突，保留各渠道受众与结构，交付中英一致的事实和变更索引，不增加未批准功能承诺。

输入材料：
- /tmp_workspace/source_article.md：产品介绍原稿
- /tmp_workspace/approved_facts.json：版本、价格、限制与日期
- /tmp_workspace/channel_drafts/：官网、小红书和英文邮件旧稿
- /tmp_workspace/changes.jsonl：3次已批准事实更正

交付：
- /tmp_workspace/results/website.html：离线官网内容
- /tmp_workspace/results/social.docx：中文渠道稿
- /tmp_workspace/results/email_en.md：英文邮件草稿
- /tmp_workspace/results/change_map.json：事实到各稿位置

约束：
- 仅读取本题exec映射到/tmp_workspace的材料；GT和评分说明不提供给候选。
- 不访问真实账号、不发送消息、不调用真实付费接口；输入和保护文件保持不变。
- 结论区分事实、推断和未知；不得虚构缺失信息。
- 所有新交付写入/tmp_workspace/results；原输入只读，不删除或覆盖。
- 离线完成，不访问网络。

同时阅读/tmp_workspace/update_brief.md。保留7份原输入字节：source_article.md、approved_facts.json、changes.jsonl、update_brief.md及channel_drafts下website.html/social.md/email_en.md。以批准基线和三次approved更正按整数seq折叠，每次完整替换被更正事实对象；未涉及事实延续。旧稿和较晚草稿时间不覆盖批准链。以2026-10-23为本次事实截点，scheduled不能写成已经上线。按12个F编号，在三渠道各提供可见、可读、可复制的对应事实/限制说明；可合并段落、表格或改写，不强制参考结构或逐句翻译。每个渠道都是完整事实交接机会，一项必要事实缺失只阻断实际受影响渠道，不把无关索引声明扩成全局失败。

官网用离线语义HTML与内联样式，ID若使用须唯一；无远程资源、脚本、外部访问、表单提交，不用截图、隐藏字、极小字体或大JSON替代正文。Word是原生中文社交稿，保留场景、两个具体使用步骤、限制和交流问题，不编造按钮或未批准功能。英文邮件有Subject、面向运营受众的开头、事实与限制、review建议，保持草稿，不发送。正文自然表达、限定和否定意义及渠道质量由35%独立Judge审阅，正确结构JSON不证明正文正确。

change_map.json为object，推荐schema=h060.change-map/v1；mode=draft_only；as_of=2026-10-23；facts为12条fact_id/value/source_ref/locations。value保存该F最终语言无关整对象的全部原字段；有限数字字符串和6%/0.06税率可等价，false必须是false，不得用0或unknown代替。推算如可选含税价可另列derived或在正文明确为测算，不加入批准事实对象。不能补未经批准的功能、地区、认证或收益。

每条locations恰含三条path=website.html/social.docx/email_en.md，相应quote为实际可见正文的精确短引（Unicode及空白归一化，可多事实共用一段）。locator可用kind=quote,occurrence=1起的出现次序（默认1），或kind=paragraph,index=1起的非空原生段落序号（含标题，Word表格可用quote）。允许不同合法结构；复杂合法未实现定位/原生表示由评测端作为异常待复核，不补能力零分。不能让短引只出现在隐藏文字、注释、脚本、代码事实表或JSON中。source_ref：基线用path=approved_facts.json,approval_id,pointer=/facts/Fxx；更正用path=changes.jsonl,change_id,seq,pointer=/changes/Fxx，必须指该F最后有效批准对象，不能仅按物理行号。

changes另列三条change_id/seq/status=applied/fact_ids，JSON排列顺序自由，后续覆盖不等于该次更正没处理。publication给website=not_deployed、social=draft_only、email=not_sent；这些只是状态声明，不能冒充实际执行证据。其余未决项可列unresolved。三渠道事实、时区、价税口径、否定和权限范围应一致；149是每工作区每月未税价，6%税率不应改成每人或年价。历史99/129、1.0/2.0、旧日期和30天试用可以在明确已撤销的审计说明中出现，不能当当前主张；不因旧数字单独出现就断定错误。

自动端只核来源/索引/实际可见关系、显式数字与标识及已覆盖的高风险明确矛盾，不声称解决所有自由语义。完整35%Judge仍需审三稿全部自然含义、跨语言否定范围、未批准承诺及渠道适配。仅读本题材料，不读GT或真实用户目录，不删除/覆盖输入。仅交付规定四文件，无账号、发送、部署、支付、提醒、网络或依赖安装。

## Expected Behavior

按完整批准链更新中英三渠道并关联12事实与36实际正文位置，正确区分当前与撤销历史、未来发布、价税单位、否定/范围和未批准承诺；离线交四产物。L4仅设计估计，35%语义Judge独立。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 更新三个渠道内容，处理事实更正和表述冲突，保留各渠道受众与结构，交付中英一致的事实和变更索引，不增加未批准功能承诺。
- [ ] `boundary_cases`: 逐项识别并正确处理：只更新一个渠道；翻译丢否定；旧价格残留。以独立反例验证，不只检索关键词。
- [ ] `delivery_integrity`: 全部要求的产物可解析/可使用，跨产物关键事实一致；保护文件与输入未改变。
- [ ] `evidence_binding`: 来源/验证记录定位到实际材料、产物或最终候选源码；自述已运行不能代替独立验证。

### Judge group

- [ ] `decision_grounding`: 针对“产品事实变更后的多渠道内容同步”的结论、取舍和未决项是否由本题材料/独立oracle支持。
- [ ] `usable_handoff`: 下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import hashlib, runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    for name, digest in {'grader.py': '8c7f9b48da8413853848c7b07f68919c24bcf8d8e3be6c6371b6292c4a11226c', 'trusted_files.json': '61f46b5693469712167cbc45db20d30468b5cc6dc171ba448396715a78fabf3d'}.items():
        p = root / "gt" / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise RuntimeError("H060_TRUSTED_RULE_MISSING_OR_DRIFT: " + name)
    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](**kwargs)
    return {key: result[key] for key in ("business_correctness", "boundary_cases", "delivery_integrity", "evidence_binding", "overall_score")}
```

## LLM Judge Rubric

### Criterion 1: 多渠道事实与限定语义 (key: decision_grounding, weight: 0.7)

判据：针对“产品事实变更后的多渠道内容同步”的结论、取舍和未决项是否由本题材料/独立oracle支持。 必须阅读三个渠道全部自然正文，逐项复核12事实、英语/中文的否定与量词范围、未来scheduled、未税单位/税率、无绑卡/自动扣款、人工外发确认、管理员本工作区CSV、区域/认证/PDF限制及明确撤销历史值。自动JSON或短引命中不是自然语义证明；任意新承诺、残留冲突和受众适配均须独立判断，不按参考句式。模型作者QA不当本次Judge。

**Score 1.0**: 所有关键结论可定位到支持证据，正确处理本题冲突与限制，无禁止主张。

**Score 0.5**: 主结论成立且无关键矛盾，但遗漏一项非关键解释或定位。

**Score 0.0**: 关键结论被材料反驳、虚构证据，或未完成核心业务判定。

### Criterion 2: 渠道稿与变更交接可用性 (key: usable_handoff, weight: 0.3)

判据：下游能否据交付物复核和继续办理本题业务，而非依赖聊天中的未落盘解释。 必须阅读三个渠道全部自然正文，逐项复核12事实、英语/中文的否定与量词范围、未来scheduled、未税单位/税率、无绑卡/自动扣款、人工外发确认、管理员本工作区CSV、区域/认证/PDF限制及明确撤销历史值。自动JSON或短引命中不是自然语义证明；任意新承诺、残留冲突和受众适配均须独立判断，不按参考句式。模型作者QA不当本次Judge。

**Score 1.0**: 对象、状态/动作、依据和限制均可在规定产物中对应查得，下一步清楚。

**Score 0.5**: 产物可使用但缺一项非关键定位/交接说明，不影响主要办理。

**Score 0.0**: 主要对象/动作无法对应，跨产物矛盾或核心交付不可用。

## Workspace Path

```
datasets/general-hard/workspace/content_operations/general_hard_content_operations_task_004_multichannel_update
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 完整继承order60七公开源文件/四交付、三已批准更正、L4设计估计、纯文本离线/非coding-primary。
- Hybrid .65/.35；自动四项.55/.25/.15/.05；不得用规则组件、正确JSON或模型作者QA代替35%Judge。
- 源先行root Python顺序折叠/Node逐字段maxseq与作者先盲读七exec后对照均在原生参考前冻结；不是人类专家审阅。
- 两自然结构参考、真实HTML浏览器/WordPDF渲染、分离原始字节与派生证据；输入保护只delivery。
- 缺可信GT/Office/HTML/依赖、合法未支持复杂表示为typed评测异常，不补零。
- 无真实发布/发送/账号/付费/提醒/网络安装、候选Harness/model/Judge/finalize；四端仍requires_preflight，难度区分度未实测。
