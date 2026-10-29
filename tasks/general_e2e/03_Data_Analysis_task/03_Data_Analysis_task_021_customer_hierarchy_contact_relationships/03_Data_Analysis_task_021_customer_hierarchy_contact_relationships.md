---
id: 03_Data_Analysis_task_021_customer_hierarchy_contact_relationships
name: Corporate Customer Hierarchies and Contact Relationships
category: data-analysis
timeout_seconds: 7200
modality: pure-text
difficulty: L4
grading_type: hybrid
grading_weights:
  automated: 0.8
  llm_judge: 0.2
tags:
  - custom
  - general_e2e
  - business
judge_evidence:
  required:
    - path: 评分证据/客户质量与分析.json
      role: grader_generated_evidence
---

## Prompt

帮我整理集团客户资料，交付客户主表、集团层级与联系人关系，说明循环、断链和资料冲突对客户管理的影响。资料和采用的《整理口径与交付.md》在 `/tmp_workspace/`，整理结果保存为 `/tmp_workspace/results/客户整理.xlsx`，质量分析和核对记录保存为 `/tmp_workspace/results/质量分析与验收.md`。

## Expected Behavior

按公开标识、有效日期和字段优先级生成客户及联系人关系；遍历六个业务sheet及授权表，处理多区块、合并单元格、宽表联系人、重复导出和隐藏有效记录。保留逐字段来源以及缺失、不适用、明确空值、待确认，完成本题专项结果及质量统计。依据实际检查说明范围、关系、合并与结论的可确认程度，不用结果正确代替主动核对。

## Grading Criteria

评分版本customer-20261015-v1。公开依据仅Prompt采用的《整理口径与交付.md》及三个公开工作簿。每自动点均设两个有独立交付价值的核验域：两域全量正确为1，仅一域全量正确为0.5，均不完整为0。集合采用多重集合比较，遗漏、额外行或重复均不算该域完整；不采用隐藏准确率阈值。所有正式检查点只有0、0.5、1三档。

| 检查点 | 分值 | 公开依据与核验域 |
|---|---:|---|
| C1_identity 客户身份与源记录归属 | 10 | 公开口径§1—2、§4；两个核验域：客户ID集合；全量物理源行的记录ID—客户ID映射 |
| C2_relations 联系人与客户关系 | 22 | 公开口径§3联系人与§4；两个核验域：联系人ID及姓名；客户—联系人—角色关系集合 |
| C3_merge 字段合并与专项结论 | 18 | 公开口径§3字段与§1专项、§4；两个核验域：客户全量字段；本题专项结果及依据集合 |
| C4_pending 待确认与非当前隔离 | 8 | 公开口径§2—3、§4待确认；两个核验域：待确认清单；全部源行的处置状态 |
| C5_lineage 跨表覆盖与逐字段来源 | 12 | 公开口径§1范围、§3来源与§4；两个核验域：全量物理行及位置；全部业务字段、联系人姓名和关系的取值状态及来源集合 |
| C6_quality 重复缺失冲突质量指标 | 10 | 公开口径§4质量指标；两个核验域：质量指标分子分母；质量指标比率 |
| C1_actual 实际身份与范围 | 5 | §1—2、§4；真实轨迹＋产物 |
| C6_analysis 质量分析与治理建议 | 5 | §4分析说明；产物＋回答 |
| C7_validation 实际验收覆盖 | 10 | §4实际核对；真实轨迹＋产物 |

自动组overall_score=Σ(分值×档位)/80；Judge组=Σ(分值×档位)/20；题目满分100。允许行列重排、附加列、数值与等价数字文本、集合成员重排；表头名称是公开下游接口。取值语义不变但无法被当前规则识别的表达或无缓存公式须人工复核，不直接断定业务错误。GT缺失/损坏抛评测异常。正确率诊断不代替预定档位。字段值与来源项存在上游影响，能力归因须说明，不能据一次上游身份错误推断所有下游能力缺失。

缺实际轨迹或重要正文采集不全时对应Judge项标不可判定，不填0、不删除重归一、不合成正式总分。原框架数字协议无法表示null时停止汇总并外置记录状态。作者参考工作簿和合成验收不能充作真实Agent得分。C4—C6业务点不强行映射能力。

## Automated Checks

```python
KEYS = {'客户主表': ['客户ID', '客户名称', '地区', '负责人', '客户等级', '上级客户ID', '服务额度'], '联系人': ['联系人ID', '姓名'], '客户联系人关系': ['客户ID', '联系人ID', '角色'], '来源去向': ['记录ID', '源位置', '客户ID', '处置'], '字段来源': ['客户ID', '字段', '取值', '状态', '来源'], '待确认': ['对象', '字段', '原因'], '质量统计': ['地区', '指标', '分子', '分母', '比率'], '专项结果': ['客户ID', '结论', '依据']}
WEIGHTS = {'C1_identity': 10, 'C2_relations': 22, 'C3_merge': 18, 'C4_pending': 8, 'C5_lineage': 12, 'C6_quality': 10}
from pathlib import Path
from collections import Counter
import json, math
import openpyxl

# KEYS and WEIGHTS are inserted into each self-contained task.
def norm(v,field=''):
 if v is None:return ''
 if isinstance(v,bool):return str(v)
 if field in ['来源','依据']:
  return ';'.join(sorted(set(x.strip() for x in str(v).split(';') if x.strip())))
 if isinstance(v,(int,float)):
  if not math.isfinite(v):return str(v)
  return str(int(v)) if float(v).is_integer() else str(round(float(v),4))
 s=str(v).strip()
 if field in ['服务额度','分子','分母','比率','结论']:
  try:return norm(float(s))
  except ValueError:pass
 return s

def grade(transcript:list,workspace_path:str)->dict:
 root=Path(workspace_path)
 reference=json.loads((root/'gt'/'标准答案.json').read_text(encoding='utf-8'))
 for s in KEYS:
  if not isinstance(reference.get(s),list) or not reference[s]:raise ValueError('Missing/corrupt oracle: '+s)
  if any(not set(KEYS[s])<=set(r) for r in reference[s]):raise ValueError('Corrupt oracle schema: '+s)
 candidate={s:[] for s in KEYS};errors=[]
 p=root/'results'/'客户整理.xlsx'
 if p.exists():
  try:
   wb=openpyxl.load_workbook(p,data_only=True)
   for s,columns in KEYS.items():
    if s not in wb:continue
    rows=list(wb[s].values)
    header=next((i for i,r in enumerate(rows) if set(columns)<=set(r)),None)
    if header is None:continue
    hh=rows[header]
    for row in rows[header+1:]:
     if any(v is not None for v in row):candidate[s].append({c:row[hh.index(c)] if hh.index(c)<len(row) else None for c in columns})
  except (OSError,ValueError,KeyError,zipfile.BadZipFile) as e:
   errors.append(type(e).__name__+': '+str(e));candidate={s:[] for s in KEYS}
 def eq(s,fields,predicate=None):
  def project(data):return Counter(tuple(norm(r.get(c),c) for c in fields) for r in data if predicate is None or predicate(r))
  return project(reference[s])==project(candidate[s])
 def band(a,b):return 1.0 if a and b else 0.5 if a or b else 0.0
 scores={}
 scores['C1_identity']=band(eq('客户主表',['客户ID']),eq('来源去向',['记录ID','客户ID']))
 scores['C2_relations']=band(eq('联系人',KEYS['联系人']),eq('客户联系人关系',KEYS['客户联系人关系']))
 scores['C3_merge']=band(eq('客户主表',KEYS['客户主表']),eq('专项结果',KEYS['专项结果']))
 scores['C4_pending']=band(eq('待确认',KEYS['待确认']),eq('来源去向',['记录ID','处置']))
 scores['C5_lineage']=band(eq('来源去向',['记录ID','源位置']),eq('字段来源',KEYS['字段来源']))
 scores['C6_quality']=band(eq('质量统计',['地区','指标','分子','分母']),eq('质量统计',['地区','指标','比率']))
 scores['overall_score']=sum(scores[key]*weight for key,weight in WEIGHTS.items())/80
 scores['diagnostics']={'errors':errors,'table_counts':{s:{'expected':len(reference[s]),'actual':len(candidate[s])} for s in KEYS},'status':'artifact_only_no_agent_verification_claim'}
 report=root/'results'/'质量分析与验收.md'
 evidence={'rule_scores':scores,'quality':candidate['质量统计'],'special_distribution':dict(Counter(norm(r.get('结论')) for r in candidate['专项结果'])),
  'report':report.read_text(encoding='utf-8') if report.exists() else None,
  'pending_sample':candidate['待确认'][:30],'pending_sample_complete':len(candidate['待确认'])<=30,
  'evidence_scope':'Full quality table and full report; pending sample only. Consult original workbook for case claims; actual processing and verification require real transcript.'}
 (root/'评分证据').mkdir(exist_ok=True)
 (root/'评分证据'/'客户质量与分析.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
 return scores

import zipfile

```

## LLM Judge Rubric

### Criterion 1: 实际身份绑定与范围 (key: C1_actual, weight: 5)

**Score 1.0**: 真实处理轨迹与产物表明六个业务sheet（含隐藏表和补充区块）及授权表均被处理，客户对象按ID或授权映射绑定，同名不同ID未混用；没有对源资料的写操作。
**Score 0.5**: 充分轨迹下，身份绑定正确但公开sheet或区块覆盖不完整，或范围完整但存在对象误用；没有对源资料的写操作。
**Score 0.0**: 充分证据下身份绑定和范围均未满足，或确有改写源资料行为。

依据公开§1—2、§4。对象身份与范围均须结合真实调用和结果；源哈希相同不能证明全过程只读。缺轨迹或缺读取结果为不可判定，不推断0或1。

### Criterion 2: 质量分析与治理建议 (key: C6_analysis, weight: 5)

**Score 1.0**: 分析正确说明三地区重复、关键字段缺失、字段冲突分布和专项结论的业务影响，至少一项优先治理建议可回查对应记录或字段，未知原因及读取限制如实保留。
**Score 0.5**: 已有正确且可回查的分布分析或专项影响分析，但另一部分缺失、建议无具体依据或未交代材料中存在的限制；没有捏造确定性原因。
**Score 0.0**: 没有可验证的正确分析，或把缺标识客户强行归并、将未知写成确认零或捏造确定性原因作为治理结论。

依据公开§4。接受同等有据的分组和建议。自动统计错误时仍可依据真实源数据判定文本，不要求复述参考措辞；自动证据文件只附部分待确认样例，具体记录须回查完整工作簿，正文未采集完整为不可判定。

### Criterion 3: 实际验收覆盖 (key: C7_validation, weight: 10)

**Score 1.0**: 真实操作和核对记录共同支持对跨sheet覆盖、对象关联、字段合并、关系完整性、质量结论五类均作了有效核对，并准确记录未解决问题及影响范围；接受任何足以支持判断的工具或人工核对方式。
**Score 0.5**: 有证据支持其中至少一类有效核对，但不足五类，且未把未检范围宣称已通过。
**Score 0.0**: 充分完整轨迹证明五类均未有效核对，或仅凭文件写入成功、代码文本、未经执行的断言宣称已全部通过。

依据公开§4。产物正确、作者测试和评测方打开文件均不证明Agent自检。采集缺失与确认未做必须分开，缺必要轨迹为不可判定。发现问题并准确保留可算有效核对，不要求所有业务结果正确才有验收分。

## Workspace Path

workspace/general_e2e/03_Data_Analysis_task/03_Data_Analysis_task_021_customer_hierarchy_contact_relationships

## Skills

## Env

## Warmup
