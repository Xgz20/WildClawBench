---
id: general_hard_research_verification_task_003_open_product_event_research
name: 开放搜索：AI搜索产品变更与来源独立性
category: research_verification
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.4
  llm_judge: 0.6
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/event_matrix.xlsx
      role: candidate_deliverable
    - path: results/source_ledger.json
      role: candidate_deliverable
    - path: results/brief.docx
      role: candidate_deliverable
scoring_runtime:
  office: true
  research_sources: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.citation_resolution": ["retrieval_verification"], "automated.protected_delivery": ["verification_delivery"], "automated.record_contract": ["verification_delivery"], "automated.time_and_scope": ["retrieval_verification"], "llm_judge.bounded_conclusions": ["reasoning_planning"], "llm_judge.coverage_and_independence": ["retrieval_verification", "reasoning_planning"], "llm_judge.factual_support": ["retrieval_verification"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 开放搜索：AI搜索产品变更与来源独立性

## Prompt

请为信息检索团队研究2026年9月的AI搜索产品变更，自主发现并筛选4项重要事件，至少覆盖3个不同产品，含国内和海外提供方。不要把旧闻转载、同功能不同阶段或单纯模型发布凑成新事件；提供方归属不能由可用国家、Global字样或域名后缀推断。

只读本地三输入：/tmp_workspace/research_window.json、/tmp_workspace/buyer_brief.md、/tmp_workspace/event_contract.json。窗口为Asia/Shanghai的[2026-09-01T00:00:00+08:00, 2026-10-01T00:00:00+08:00)。不提供候选产品、答案URL或首条Query；可自主组合公共搜索、站内导航、浏览和fetch，不限定工具名或搜索引擎排序。

按event_contract.json交付到/tmp_workspace/results，单份不超过5MiB：
1. event_matrix.xlsx：原生可见、可编辑、自包含的4事件表，覆盖产品/提供方归属、事件与变更组、功能、发布与所选状态发生时间、后续计划、阶段、可用范围、重要性和证据关联。允许清楚中文别名、行列重排、分表/合表及转置，逻辑对象须可识别，不用隐藏区域、图片或单格巨大JSON代替核心表格。静态数值接受；若用公式须可实际重算，无宏/外链数据。
2. source_ledger.json：按公共契约记录实际发现、阅读、引用、日期证据、claims、来源谱系和简报关联。sources内保留source_id/url/access_status/accessed_at/title及citations，每条短引带唯一citation_id、真实locator；引用正文一份即可，同claim可用supports_fields关联多类字段/目标，不强造互不相同的23句。日期可源内嵌套，允许复用。记录真正遇到的未纳入候选及理由（如有），不虚构过程。
3. brief.docx：原生可编辑简报，2项有证据的跨事件观察和1项面向本团队的行动建议，关联事件/claim，写清人群、范围、下一步验证、可比性和未知，不做无依据效果排名。

分清来源发表/修改日期、所评估状态的发生时间和另外公布的后续可用时间。允许窗口内“宣布未来功能”的宣布事件，但不能称已经正式上线。自然月、日期、timestamp、interval及unknown按原精度记录；时区未知不伪造时分/UTC边界，未声明阶段可用not_stated，缺失不等于0或不适用，后续计划可以空列表。标题、URL年份、HTTP/抓取时间与文件创建时间不能单独证明历史事件日期。

优先实际一手资料并寻找独立交叉支持；允许诚实单源。转载或同提供方多页不自动成为独立证据。摘要仅支持其明确事实，不冒充已读全文；实际不可读、冲突和未知如实说明。参考池非穷尽，其它符合范围并有证据的事件同样有效。本次抓取可能晚于研究窗口，应明确历史依据与限制，不声称有当时网页存档，不把后续GA回填到窗口，也不将发布宣传当已实测效果。

三输入保持原字节，不删除或覆盖；所有新交付写入results，不以聊天代交。只读取本地输入及实际发现的公开材料，不访问GT或评分说明；不登录真实账号、不发消息、不调用真实业务或付费API、不购买开通服务。无需实际试用产品或理解图片/截图；产品提及图搜图不构成本题视觉输入。完成前核对三产物事实和引用一致。

## Expected Behavior

自主发现4实质搜索产品变更、至少3实际产品及国内海外提供方，保留时间/阶段/范围/单源边界；原生三交付可追溯。L3为设计预估。

## Grading Criteria

### Automated group

- [ ] `record_contract`: 交付可解析、4固定事件槽及必要逻辑字段/ID关联完整，简报2项观察与1项行动可见、原生可编辑；不按Sheet坐标或模板、字数评分。
- [ ] `time_and_scope`: 每个固定事件槽核独立真实日期token/元数据绑定、原精度及时区归一、左闭右开窗口算术及范围引用关联；内部.30/.30/.20/.20。真实事件资格、日期角色和阶段含义由Judge另核，不将候选自填日期当独立依据。
- [ ] `citation_resolution`: 4×5事件主张类别、2观察和1行动共23个固定引用槽，核ID图、独立来源字节绑定、真实locator处短引及访问声明结构。允许同claim覆盖多字段/目标，不强造23句；引文存在不等于语义支持。
- [ ] `protected_delivery`: 三输入SHA不变，XLSX/JSON/DOCX可打开、核心原生内容可见可编辑。保护输入修改仅使本项为0，不重复扣其它相同项。

### Judge group

- [ ] `factual_support`: 每计数项真实产品变更、历史时间关联、阶段/可用性/归属及关键用户影响；两趋势/一建议的事实前提。逐主张读实际独立正文，引用存在不等于支持。已诚实unknown不算捏造，但不能替代事件入窗证据。 必须读取实际三交付与评分侧独立来源正文/元数据；缺必要供证为评测异常或unresolved，不补候选零分。
- [ ] `coverage_and_independence`: 实际4个实质变更组、至少3实际产品、国内与海外运营归属；产品身份、同功能多阶段去重、筛选和转载谱系。允许准确披露单源，不强制每项双源。池外同标准，不按参考名单。 必须读取实际三交付与评分侧独立来源正文/元数据；缺必要供证为评测异常或unresolved，不补候选零分。
- [ ] `bounded_conclusions`: 完整DOCX两项跨事件观察和一项面向信息检索团队的行动；逐条事实前提、可比性、适用范围、下一步验证与未知。不同有证据的结论可满分，不把宣传或公告写成实测效果。 必须读取实际三交付与评分侧独立来源正文/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

## Automated Checks

```python
def grade(**kwargs) -> dict:
    from pathlib import Path
    import runpy
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    scores = runpy.run_path(str(root / "gt/grader.py"))["grade"](
        transcript=kwargs.get("transcript") or [], workspace_path=str(root)
    )
    return {
        "record_contract": scores["record_contract"],
        "time_and_scope": scores["time_and_scope"],
        "citation_resolution": scores["citation_resolution"],
        "protected_delivery": scores["protected_delivery"],
        "overall_score": (0.20 * scores["record_contract"] + 0.25 * scores["time_and_scope"]
                          + 0.40 * scores["citation_resolution"] + 0.15 * scores["protected_delivery"]),
    }
```

## LLM Judge Rubric

### Criterion 1: 事实与历史状态支持 (key: factual_support, weight: 0.5)

判据：每计数项真实产品变更、历史时间关联、阶段/可用性/归属及关键用户影响；两趋势/一建议的事实前提。逐主张读实际独立正文，引用存在不等于支持。已诚实unknown不算捏造，但不能替代事件入窗证据。 必须读取实际三交付与评分侧独立来源正文/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

**Score 1.0**: 关键事实与时空口径均被真实证据支持，无捏造或阶段升级。

**Score 0.5**: 主结论成立，存在非关键事实或支撑缺口。

**Score 0.0**: 核心事实/时间/阶段与证据矛盾、虚构来源或未完成核心核验。

### Criterion 2: 有效覆盖与来源独立性 (key: coverage_and_independence, weight: 0.3)

判据：实际4个实质变更组、至少3实际产品、国内与海外运营归属；产品身份、同功能多阶段去重、筛选和转载谱系。允许准确披露单源，不强制每项双源。池外同标准，不按参考名单。 必须读取实际三交付与评分侧独立来源正文/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

**Score 1.0**: 核心覆盖真实合格，重复和谱系处理准确，单源限制诚实。

**Score 0.5**: 主范围满足，漏一个非关键分支且未凑数。

**Score 0.0**: 核心覆盖不足或用旧闻、同组阶段、非搜索事项、转载冒充有效覆盖。

### Criterion 3: 有界观察与行动建议 (key: bounded_conclusions, weight: 0.2)

判据：完整DOCX两项跨事件观察和一项面向信息检索团队的行动；逐条事实前提、可比性、适用范围、下一步验证与未知。不同有证据的结论可满分，不把宣传或公告写成实测效果。 必须读取实际三交付与评分侧独立来源正文/元数据；缺必要供证为评测异常或unresolved，不补候选零分。

**Score 1.0**: 观察和行动有可追溯依据、适用条件与限制，不作无依据效果外推。

**Score 0.5**: 主建议有依据，漏一项非关键条件或验证。

**Score 0.0**: 主要建议/趋势与证据矛盾、无依据排名或保证。

## Workspace Path

```
datasets/general-hard/workspace/research_verification/general_hard_research_verification_task_003_open_product_event_research
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 源先行事实oracle；两名模型初始独立发现及第二阶段给定URL重取交叉复核分别留痕，模型复核非人工专家。参考池非穷尽，自动规则不匹配固定产品/URL答案。
- 自动内部.20/.25/.40/.15，外层自动.40/语义.60；time内部.30/.30/.20/.20。日期token/引文机械通过不证明真实事件资格、阶段、谱系独立性或建议成立，必须由真实Judge核验。
- score0.25.0/core0.15.2或兼容冻结入口；prepare后独立collect公开来源，显式reuse时保留原GET回执、时刻和自包含谱系，不冒称重新访问。缺GT、来源包/锁/投影或Office依赖为评测异常，不补能力零分。
- 公开HTML/PDF/文本及安全router MDContent可有等价证据路径；无动态解码或图片理解要求。商业来源全文只留取证区/实际来源运行包，GT仅必要短引/事实/哈希定位。
- 作者原生参考、控制测试和独立ZIP规则验收不是Harness做题或正式语义Judge，不产生hybrid总分；900仅任务元数据，难度/区分度待12题实测校准。
