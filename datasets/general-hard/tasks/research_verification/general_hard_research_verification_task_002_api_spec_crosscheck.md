---
id: general_hard_research_verification_task_002_api_spec_crosscheck
name: 公开接口连接与鉴权规格核对
category: research_verification
timeout_seconds: 900
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L3
grading_type: hybrid
grading_weights:
  automated: 0.75
  llm_judge: 0.25
tags:
  - custom
  - general-hard
judge_evidence:
  required:
    - path: results/api_contract.xlsx
      role: candidate_deliverable
    - path: results/integration_revised.md
      role: candidate_deliverable
    - path: results/sources.json
      role: candidate_deliverable
scoring_runtime:
  office: true
  research_sources: true
dataset_report: {"category": "research_verification", "category_name": "研究检索与证据核验", "category_order": 2, "checkpoint_capabilities": {"automated.boundary_cases": ["reasoning_planning"], "automated.business_correctness": ["retrieval_verification"], "automated.delivery_integrity": ["verification_delivery"], "automated.evidence_binding": ["retrieval_verification"], "llm_judge.decision_grounding": ["retrieval_verification"], "llm_judge.usable_handoff": ["verification_delivery"]}, "schema_version": "wildclawbench.dataset-report-contract/v1", "series_id": "general-hard"}
---

# 公开接口连接与鉴权规格核对

## Prompt

请为接入同事核对给定的实时语音转写标准版官方文档，整理连接、鉴权、音频、结束与响应、错误处理和授权边界，并修正旧接入说明。

只读本地三份输入：/tmp_workspace/client_requirements.md、/tmp_workspace/legacy_integration.md、/tmp_workspace/official_entry.json。按需求文件的10个主题、38个typed事实字段、三组合成签名输入及等价表达契约完成。官方入口为https://www.xfyun.cn/doc/asr/rtasr/API.html，可以直接fetch或浏览，不强制搜索；仅读取同https://www.xfyun.cn/doc/asr/rtasr/公开文档子树及渲染必要静态资源。不要把其他产品、SDK、博客或搜索摘要当该接口规范。official_entry.json的capture_id、取得时间与SHA只绑定题目取证，不是官方版本或发布日期。执行前按其规范化正文身份核对来源；正文变化属于评测输入漂移，应记录异常，不填猜测答案。

三份交付均写入/tmp_workspace/results，单份不超过5MiB：
1. api_contract.xlsx：可见、可编辑、自包含的原生XLSX，覆盖38个field_id及3个合成签名向量md5_hex、signa_base64、signa_urlencoded。标量/record/record_set形状按需求文件，允许清楚JSON小record、子列/子行或10个topic对象展开；Sheet名、坐标、行列次序、分表合表、清楚中文别名和辅助列不限。核心结果不能藏于一格巨大JSON、隐藏区域或图片。静态正确表可接受，不要求Excel实现密码算法；若用公式则须可实际重算，不含宏或外部数据连接。未知用null、空单元格加明确未知状态或清楚未知标记，不等于0；空签名分隔符与未知不同。保持参数大小写、bool/整数类型及Base64字节含义；明确单位的等价换算接受。
2. integration_revised.md：逐项覆盖旧稿L01—L12，写问题、实际修订、相关field_id和citation_id，给同事可使用的接入核查说明。区分文档规定、建议、示例推导、工程解释、自定客户端策略与未知；保留文档内部差异，列后续确认。编号存在不代替解释正确。
3. sources.json：顶层sources和limitations，可有searches/navigation但不强制。每源source_id、url、access_status、accessed_at、title、citations；access_status按需求契约记录实际状态。每citation唯一ID、实际locator对象及必要短quote，HTML定位实际标题/锚点/逻辑表格行；表格/说明引用ID可回查。记录未读、仅摘要、单源、冲突及不可确认，多个URL不自动等于独立规范来源。quote存在和URL可达都不自动证明主张受支持，不能用自己写的快照自证。

只交付说明、表格和来源账本，不编写或运行真实转写客户端，不访问真实账号、不发送消息、不调用真实业务/付费API、不使用真实凭据。三组合成appid/ts/api_key无真实授权，仅按固定输入离线核算，不改ts为当前时间，不向服务发送签名URL。不得把官方示例密钥复制为配置，不声称专家认证或真实服务验收。

三份输入保持原字节，不删除或覆盖；所有新交付在results内。不要访问GT和评分说明，完成前核对跨产物事实/引用一致。只需可提取文本的网页及本地文件读写，不要求图像理解。

## Expected Behavior

直接读取明确官方入口即可，核实标准版38事实及合成签名，修正12项旧稿，保留建议/未知/冲突，引用可回查；L3仅设计预估。

## Grading Criteria

### Automated group

- [ ] `business_correctness`: 38事实字段中27核心字段逐leaf核对固定分母，并独立核3合成签名向量；以字段均值和向量均值.7/.3聚合。保持大小写、bool/整数、空串/未知、集合与顺序、单位等价边界。
- [ ] `boundary_cases`: 11独立边界字段核正式版本/日期与时窗未知、密钥用途、建议强度、理论总时长、默认行为/控制值、10110冲突、重试与checkSum；不与核心字段重复计分。
- [ ] `delivery_integrity`: 保护输入SHA不变，三交付可解析，原生表可见可编辑、对象唯一与结构完整；核L01-L12及跨产物field/citation关联。实质修订语义由Judge判断；输入改动只将本项置0。
- [ ] `evidence_binding`: 真实独立来源包绑定candidate ledger与交付，短引能定位官方正文/逻辑表格行并核指定主文档身份；缺引用/错源按候选失分，只有独立取得指定主URL且正文变化才记输入漂移。quote存在不等支持主张。

### Judge group

- [ ] `decision_grounding`: 实际读取三份交付、评分侧独立取得的官方主文章及必要上下文。逐条核L01-L12实质修订，尤其appid大小写、签名字节层次、秒级ts但窗口未规定、音频binary与结束binary、响应text/data内JSON字符串、40ms/1280B建议、15s空闲而非总时长、默认行为与数值默认的区别、10110表/示例/FAQ冲突、16003明文重试而次数/退避/恢复未知，以及checkSum只见FAQ、白名单约5分钟与文档日期未知。区分规定、建议、示例推导、工程解释、client_policy、未知，不把标题短引证明否定结论或只看域名/URL；审阅额外prose真实性、时间/单源限制和未做真实服务测试。 缺GT或评分侧必要独立证据为评测异常/unresolved，不能补成候选能力零分。
- [ ] `usable_handoff`: 实际核L01-L12的问题、修订、field与citation对应和同事可执行的后续确认；不以编号齐全代替语义完整。工作簿、说明和来源账本的关键事实一致，授权/文档未知项有明确后续，三组合成签名的固定旧ts仅离线数学输入，不冒称当前授权/服务器接受。不因Sheet布局/中文等价表达扣分。 缺GT或评分侧必要独立证据为评测异常/unresolved，不能补成候选能力零分。

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
        "business_correctness": scores["business_correctness"],
        "boundary_cases": scores["boundary_cases"],
        "delivery_integrity": scores["delivery_integrity"],
        "evidence_binding": scores["evidence_binding"],
        "overall_score": (0.55 * scores["business_correctness"] + 0.25 * scores["boundary_cases"]
                          + 0.15 * scores["delivery_integrity"] + 0.05 * scores["evidence_binding"]),
    }
```

## LLM Judge Rubric

### Criterion 1: 规范事实与冲突边界 (key: decision_grounding, weight: 0.7)

判据：实际读取三份交付、评分侧独立取得的官方主文章及必要上下文。逐条核L01-L12实质修订，尤其appid大小写、签名字节层次、秒级ts但窗口未规定、音频binary与结束binary、响应text/data内JSON字符串、40ms/1280B建议、15s空闲而非总时长、默认行为与数值默认的区别、10110表/示例/FAQ冲突、16003明文重试而次数/退避/恢复未知，以及checkSum只见FAQ、白名单约5分钟与文档日期未知。区分规定、建议、示例推导、工程解释、client_policy、未知，不把标题短引证明否定结论或只看域名/URL；审阅额外prose真实性、时间/单源限制和未做真实服务测试。 缺GT或评分侧必要独立证据为评测异常/unresolved，不能补成候选能力零分。

**Score 1.0**: 关键结论有明确来源支撑，冲突与未知边界清楚，无重大矛盾或虚构保证。

**Score 0.5**: 主结论成立且无关键错误，一处非关键解释或定位遗漏。

**Score 0.0**: 核心解释矛盾、虚构证据或保证，或主要核对未完成。

### Criterion 2: 修订与接入交接 (key: usable_handoff, weight: 0.3)

判据：实际核L01-L12的问题、修订、field与citation对应和同事可执行的后续确认；不以编号齐全代替语义完整。工作簿、说明和来源账本的关键事实一致，授权/文档未知项有明确后续，三组合成签名的固定旧ts仅离线数学输入，不冒称当前授权/服务器接受。不因Sheet布局/中文等价表达扣分。 缺GT或评分侧必要独立证据为评测异常/unresolved，不能补成候选能力零分。

**Score 1.0**: 三份交付可独立用于后续接入核查，修订与后续动作可追踪且一致。

**Score 0.5**: 总体可用，一处非关键交接或定位遗漏。

**Score 0.0**: 核心修订不可用、关键对象或依据未关联，或存在重大跨文件矛盾。

## Workspace Path

```
datasets/general-hard/workspace/research_verification/general_hard_research_verification_task_002_api_spec_crosscheck
```

## Skills

## Env

## Warmup

## Additional Notes

- 此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。
- 两名隔离模型各实际获取官方HTML并独立核验，source-first GT先于参考；签名另由Python/Node两个本地路径逐字核算。均模型复核，非人工专家。
- 自动内部.55/.25/.15/.05，外层自动.75/语义.25，语义.7/.3；38字段逐leaf后字段均值，不按大record叶数支配总分。原生布局/单位/中文/集合顺序等价接受，appid和Base64大小写、JSON布尔与整数不得混淆。
- 直接fetch足够，不因未调用web-search扣分。实际取得指定主URL后规范化main正文变化才为输入漂移；候选缺引/错源仍按契约失分。评分规则离线，不调用模型。
- 评分需score0.24.0/core0.15.2或兼容冻结入口；prepare后collect-research-sources独立取得真实来源，规则和语义共享只读来源包/锁。GT只含必要短引与事实/哈希定位，商业官方全文留取证区及实际运行包，不复制进Git。
- 缺GT/独立供证/Office或投影损坏为评测异常，不补能力零分；自动规则通过不证明修订prose正确。未做真实Harness或正式Judge，未产生混合总分，900仅元数据。
