"""Typed source-table-driven observables, not a prose scientific Judge.

The source oracle supplies report identities, owners and operand values. No
claim ID or answer label is embedded in evaluator branches. Unhandled clear
prose is explicitly pending semantic review instead of being scored as false.
"""
from decimal import Decimal,InvalidOperation
import ast,re,unicodedata

class SemanticReviewRequired(RuntimeError):pass
def norm(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str('' if value is None else value))).casefold()
def rich(value):return bool(str(value).strip()) if isinstance(value,str) else bool(value) if isinstance(value,(dict,list)) else False
ROLE_ALIASES={
 'goal_pass':['goal','final_goal','final_goal_pass','goal_success','target_pass','目标通过','目标成功','最终目标','最终目标成功率','任务目标成功率'],
 'goal_conditional_on_reload':['conditional_goal_pass','goal_given_reload','恢复后目标通过率','恢复事件条件下目标成功率','goal conditional on reload'],
 'reload':['reload','resumed','recovery_event','恢复事件','重载','恢复率'],
 'format_valid':['format','format_valid','格式有效','格式通过','格式有效率'],
 'structure_pass':['structure','structure_pass','PF1_structure_pass','结构通过','包结构','结构有效'],
 'p95':['p95','p95_latency','p95_seconds','95分位','95分位时延'],
 'max_latency':['max_latency','maximum_latency','最大时延'],
 'point_difference':['point_difference','difference_pp','percentage_point_difference','点差','百分点差','增加百分点','高出百分点'],
 'relative_reduction':['relative_reduction','relative_decrease','相对下降','相对降幅','降幅'],
 'time_reduction':['time_reduction','latency_reduction','时延差','时延下降','减少时延'],
 'report_count':['reports','report_count','file_count','报告数','文件数','份PDF'],
 'work_count':['works','work_count','独立工作数','工作数'],
 'checkpoint_only_ablation':['checkpoint_only_ablation','single_factor_ablation','单因素消融','单独checkpoint消融'],
 'causal_component_contributions':['causal_component_contributions','causal_contribution','checkpoint_contribution','因果分量','各因素贡献','checkpoint贡献'],
 'continuous_experiment':['continuous_48h_experiment','continuous_experiment','experiment_occurred','48小时实验','连续实验'],
 'max_recovery_latency':['actual_max_recovery_latency','max_recovery_latency','maximum_recovery_latency','最大恢复时延'],
 'latency_measurement':['latency_series','latency_measurement','时延测量','恢复时延记录'],
 'lifecycle_cost':['lifecycle_cost','lifecycle_total','lifecycle_mean_CU_per_task','完整生命周期成本','生命周期费用'],
 'io_slice_cost':['io_slice_cost','slice_mean_CU_per_task','initial_io_cost','首次I/O切片成本','首次IO成本'],
 'omitted_cost_components':['retry_startup_storage','omitted_cost_components','重试启动持久化费用','缺失费用'],
 'unsafe_flags':['unsafe_flags','SF1_flagged_executions','不安全标记','安全标记'],
 'production_evidence':['production_evidence','production_test_population_risk_bound_or_universal_proof','生产测试证据','生产风险界'],
 'universal_production_safety':['universal_production_safety','production_risk','普遍安全保证','真实生产风险'],
 'mapping_to_other_split':['mapping_to_W1','mapping_to_other_split','跨划分映射'],
 'policy':['policy','model','模型','策略模型'],
 'tool_total_ceiling_per_task':['tool_total_ceiling_per_task','tool_budget','tool_ceiling','工具预算','累计工具调用'],
 'max_attempt_starts_per_task':['max_attempt_starts_per_task','attempts','attempt_ceiling','尝试上限','最多启动次数'],
 'task_suite':['task_suite','task','suite','任务','任务套件'], 'split':['split','数据划分','划分'],
 'host':['host','hardware','硬件','主机'],'quantile_rank':['quantile_rank','nearest_rank','分位数秩'],'timing_population':['timing_population','N_timed_each','计时分母'],
 'time_unit_ms':['time_unit_ms','U_T_ms','单位毫秒换算'],'evidence_scope':['evidence_scope','experiment_scope','实验范围','证据范围'],'reset_step':['reset_step','故障步骤','重置步骤']}
ROLES={norm(alias):role for role,aliases in ROLE_ALIASES.items() for alias in (role,*aliases)}
def role(value):
    raw=norm(value)
    if raw in ROLES:return ROLES[raw]
    stripped=re.sub(r'[()（）\[\]]','',raw)
    if stripped in ROLES:return ROLES[stripped]
    compact=stripped.replace('_','').replace('-','')
    return next((canonical for alias,canonical in ROLES.items() if alias.replace('_','').replace('-','')==compact),None)
def state(value):
    if value is None:return 'unknown'
    if type(value) is bool:return 'true' if value else 'false'
    raw=norm(value).replace('_','').replace('-','')
    if raw in ('unknown','null','notreported','notsupplied','notprovided','notrecorded','unreported','notmeasured','unmeasured','未报告','未提供','未记录','没有记录','未测量','未知','缺证','notapplicable'):return 'unknown'
    if raw in ('false','no','notconducted','notperformed','未开展','未开展或设定','未做','否','没有进行'):return 'false'
    if raw in ('true','yes','conducted','performed','已做','已开展','是'):return 'true'
    # A leading epistemic state can carry a non-assertive qualification. Do not
    # turn a contradictory subsequent measurement or positive assertion into unknown.
    text=unicodedata.normalize('NFKC',str(value)).strip()
    if re.match(r'^(?:explicitly\s+)?not\s+(?:conducted|performed)\s+or\s+stipulated\s*$',text,re.I):return 'false'
    if re.match(r'^not\s+reported\s+or\s+(?:not\s+)?reconstructable\s*$',text,re.I):return 'unknown'
    head,*tail=re.split(r'[;；]',text,maxsplit=1)
    if tail and norm(head) in ('unknown','null','未知','未报告','notreported','notrecorded'):
        rest=tail[0]
        if re.search(r'(?:but|however|实际|但是|然而|measured|value)\s*[:=为]?\s*[+-]?\d',rest,re.I):return None
        if re.search(r'\b(?:conducted|performed|measured|recorded)\b',rest,re.I) and not re.search(r'\b(?:no|not|neither)\b',rest,re.I):return None
        return 'unknown'
    return None

def key_semantics(key,registry):
    """Decode explicitly typed keys, retaining unit/predicate/report namespaces."""
    raw=str(key);subject=None;rest=raw
    for rid in sorted(registry['sources']['reports'],key=len,reverse=True):
        if norm(raw).startswith(norm(rid)+'_'):
            subject=rid;rest=raw[len(rid)+1:];break
    if subject is None:
        # A declared work/report alias is permitted only as a token prefix, never
        # an arbitrary substring of a quantity or a reference-specific filename.
        for alias,rids in sorted(registry['aliases'].items(),key=lambda item:len(item[0]),reverse=True):
            if len(rids)==1 and re.fullmatch(r'[a-z0-9_-]+',alias) and norm(raw).startswith(alias+'_'):
                subject=next(iter(rids));rest=raw[len(alias)+1:];break
    declared_unit=None
    suffixes=(('_CU_per_task','CU/task'),('_milliseconds','milliseconds'),('_seconds','seconds'),('_ms','milliseconds'),('_U_T','U_T'))
    semantic=rest
    for suffix,u in suffixes:
        if norm(rest).endswith(norm(suffix)):
            semantic=rest[:-len(suffix)];declared_unit=u;break
    quantity=role(rest) or role(semantic)
    if quantity is None:
        predicate=re.fullmatch(r'([A-Za-z]+[0-9]+)_(.+)',semantic)
        if predicate:quantity=role(predicate[2])
    if subject is not None and norm(rest)=='u_t':quantity='time_unit_ms'
    return quantity,declared_unit,subject

def derived_semantics(record,registry):
    """Recognize a declared metric/result or an explicitly qualified unit/formula.
    Ambiguous formulas/ranges remain unresolved. No calculation ID or source
    answer is consulted, and the declared result is never replaced by a computed one.
    """
    if 'result' not in record or not isinstance(record.get('unit'),str):return None
    descriptor=record['unit'];formula=str(record.get('formula',''));q=role(record.get('quantity',record.get('metric')))
    u=None
    for token in ('percentage points','percentage_points','percent','milliseconds','seconds','CU/task','ms','s'):
        if re.match(r'^'+re.escape(token)+r'(?:\b|\s|$)',descriptor,re.I):u=unit(token);break
    if q is None:
        if re.search(r'\bp95\b',descriptor,re.I):q='p95'
        elif u=='percentage_points' and re.search(r'[-−]',formula):q='point_difference'
        elif u in ('seconds','milliseconds') and re.search(r'\breduction\b|减少|下降',descriptor,re.I):q='time_reduction'
        elif u=='percent' and re.search(r'\breduction\b|降幅',descriptor,re.I) and ('/' in formula or re.search(r'relative|基线',descriptor,re.I)):q='relative_reduction'
    if not q or not u:return None
    subjects=[]
    for alias,rids in registry['aliases'].items():
        if len(rids)==1 and re.fullmatch(r'[a-z0-9_-]+',alias) and re.search(r'(?<![A-Za-z0-9_])'+re.escape(alias)+r'(?![A-Za-z0-9_])',descriptor,re.I):subjects.extend(rids)
    explicit={rid for key in ('report','report_id','document_id','file') if key in record and (rid:=resolve_subject(record[key],registry,record.get('version')))}
    if explicit and set(subjects) and explicit!=set(subjects):
        # A unit descriptor can clarify an absent subject, but cannot overwrite
        # an explicit incompatible report/version. Preserve for typed review.
        return None
    value={'quantity':q,'value':record['result'],'unit':u,'normalization_source':'declared result/unit/formula; no ID lookup'}
    try:
        expression=formula.replace('−','-').replace('×','*').replace('÷','/')
        def calculate(node):
            if isinstance(node,ast.Constant) and type(node.value) in (int,float):return Decimal(str(node.value))
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
                x=calculate(node.operand);return -x if isinstance(node.op,ast.USub) else x
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                left,right=calculate(node.left),calculate(node.right)
                return left+right if isinstance(node.op,ast.Add) else left-right if isinstance(node.op,ast.Sub) else left*right if isinstance(node.op,ast.Mult) else left/right
            raise ValueError('not a bounded literal arithmetic formula')
        tree=ast.parse(expression,mode='eval')
        if len(list(ast.walk(tree)))>80:raise ValueError('formula too complex')
        calculated=calculate(tree.body);declared=number(record['result'])
        value['formula_consistent']=declared is not None and abs(calculated-declared['value'])<=Decimal('0.000001')
    except (SyntaxError,ValueError,InvalidOperation,ZeroDivisionError):pass
    if len(set(subjects))==1:value['report_id']=next(iter(set(subjects)))
    if 'condition' in record:value['condition']=record['condition']
    if 'denominator' in record:value['denominator']=record['denominator']
    return value
def unit(value):
    raw=norm(value).replace('％','%')
    aliases={'percentage_points':('pp','percentagepoints','percentagepoint','百分点','点差'),'percent':('%','percent','percentage','百分比','百分率'),'ratio':('ratio','fraction','比例'),'seconds':('s','sec','second','seconds','秒'),'milliseconds':('ms','millisecond','milliseconds','毫秒'),'count':('count','tasks','executions','events','次','个','任务','样本'),'tool_calls':('toolcalls','tool_calls','工具调用'),'model_requests':('modelrequests','model_requests','model_calls','模型请求'),'attempt_starts':('attempts','attemptstarts','attempt_starts','controllerstarts','启动次数'),'CU/task':('cu/task','cupertask','cu/任务','cu每任务'),'U_T':('u_t','ut')}
    return next((key for key,values in aliases.items() if raw==norm(key) or raw in {norm(v) for v in values}),raw or None)
def number(value,declared_unit=None):
    if type(value) in (int,float):
        try:d=Decimal(str(value))
        except InvalidOperation:return None
        return {'value':d,'unit':unit(declared_unit)} if d.is_finite() else None
    if not isinstance(value,str):return None
    raw=unicodedata.normalize('NFKC',value).strip()
    fraction=re.fullmatch(r'([+-]?[0-9]+(?:\.[0-9]+)?)\s*/\s*([0-9]+(?:\.[0-9]+)?)',raw)
    if fraction:
        n,d=map(Decimal,fraction.groups())
        return {'value':n,'denominator':d,'unit':'count'} if d>0 else None
    if any(mark in raw for mark in ('±','+/-','<','>','[',']','≤','≥')):return None
    scalar=re.fullmatch(r'([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\s*([^0-9\s].*)?',raw)
    if scalar:
        value=Decimal(scalar[1]);return {'value':value,'unit':unit(scalar[2] or declared_unit)} if value.is_finite() else None
    return None
def subject_registry(sources,documents):
    aliases={};doc_sources={};doc_mismatches={};doc_pending_versions={}
    def version_value(value):
        if isinstance(value,dict):
            for key in ('read_version','version','tag','所读版本','版本','read','text'):
                if key in value:return version_value(value[key])
            return None
        if not isinstance(value,(str,int)) or type(value) is bool:return None
        raw=str(value).strip()
        if norm(raw) in ('unknown','未知','未确认'):return 'unknown'
        if re.fullmatch(r'[0-9]+(?:\.[0-9]+)*',raw):return 'v'+raw
        tokens=re.findall(r'(?<![A-Za-z0-9])(?:v|version\s*|ver\s*|版本\s*)([0-9]+(?:\.[0-9]+)*)(?![A-Za-z0-9])',raw,re.I)
        return 'v'+tokens[0] if tokens and len(set(tokens))==1 else None
    def add(alias,rid):
        if isinstance(alias,str) and alias.strip():aliases.setdefault(norm(alias),set()).add(rid)
    for rid,s in sources['reports'].items():
        for alias in (rid,s['file'],s.get('file_name'),s.get('title'),s.get('work_id'),s.get('title','').split(':')[0],s.get('work_id')+' '+s['version'],s.get('title','').split(':')[0]+' '+s['version']):add(alias,rid)
    for document in documents:
        if not isinstance(document,dict):continue
        file=document.get('file');file='papers/'+file if isinstance(file,str) and not file.startswith('papers/') else file
        source=sources['by_file'].get(file) if isinstance(file,str) else None
        if source and isinstance(document.get('document_id'),str):
            did=document['document_id'];doc_sources[did]=source
            add(did,source['report_id']);claimed=version_value(document.get('version'));actual=version_value(source['version']);doc_mismatches[did]=claimed not in (None,'unknown',actual)
            if claimed is None:doc_pending_versions[did]=document.get('version')
    return {'aliases':aliases,'doc_sources':doc_sources,'doc_mismatches':doc_mismatches,'doc_pending_versions':doc_pending_versions,'sources':sources}
def resolve_subject(value,registry,version=None):
    if not isinstance(value,str):return None
    matches=registry['aliases'].get(norm(value),set())
    if version is not None:matches={rid for rid in matches if norm(registry['sources']['reports'][rid]['version'])==norm(version)}
    return next(iter(matches)) if len(matches)==1 else None
def observations(claim,registry):
    result=[];unhandled=[];components=[];lineage=[]
    def add(quantity,value,context,pointer,declared_unit=None,denominator=None):
        q=role(quantity)
        if q is None:unhandled.append({'pointer':pointer,'metric_or_quantity':quantity});return
        if q=='goal_pass' and re.search(r'conditional.?on.?reload|given.?reload|恢复后|已恢复|恢复事件为条件',str(context.get('condition','')),re.I):q='goal_conditional_on_reload'
        if not context.get('report_id') and context.get('report_ids'):
            for rid in context['report_ids']:add(quantity,value,{**context,'report_id':rid,'report_ids':[]},pointer+':declared_subject='+rid,declared_unit,denominator)
            return
        if declared_unit is None and q in ('report_count','work_count'):declared_unit='count'
        if declared_unit is None and q=='point_difference':declared_unit='percentage_points'
        if declared_unit is None and q=='tool_total_ceiling_per_task':declared_unit='tool_calls'
        if declared_unit is None and q=='max_attempt_starts_per_task':declared_unit='attempt_starts'
        if declared_unit is None and q=='time_unit_ms':declared_unit='milliseconds'
        if q=='task_suite' and isinstance(value,str) and value.count('/')==1:
            task,split=value.split('/',1);add('task_suite',task,context,pointer+':declared_task');add('split',split,context,pointer+':declared_split');return
        parsed=number(value,declared_unit);s=state(value)
        result.append({'quantity':q,'raw_value':value,'number':parsed,'state':s,'report_id':context.get('report_id'),'arm':context.get('arm'),'unit':unit(declared_unit) or (parsed or {}).get('unit'),'denominator':denominator if denominator is not None else context.get('denominator'),'condition':context.get('condition'),'pointer':pointer,'component_verdict':context.get('component_verdict'),'formula_consistent':context.get('formula_consistent')})
    def visit(value,context,pointer):
        if isinstance(value,list):
            for i,item in enumerate(value):visit(item,context,pointer+'/'+str(i))
            return
        if not isinstance(value,dict):
            if isinstance(value,str):prose(value,context,pointer)
            return
        context=dict(context);version=value.get('version')
        for key in ('report','report_id','document_id','file'):
            if key in value:
                rid=resolve_subject(value[key],registry,version)
                if rid:context['report_id']=rid
        for key in ('reports','report_ids','document_ids'):
            if isinstance(value.get(key),list):context['report_ids']=[rid for actual in value[key] if (rid:=resolve_subject(actual,registry,version))]
        if version is not None and context.get('report_id') and resolve_subject(context['report_id'],registry,version) is None:
            unhandled.append({'pointer':pointer,'declared_version':version,'report_id':context['report_id'],'reason':'explicit version does not resolve to inherited report; no identity overwrite'})
            return
        for key in ('arm','group','实验臂','组别'):
            if key in value and isinstance(value[key],str):context['arm']=value[key]
        if 'condition' in value or 'conditions' in value:context['condition']=value.get('condition',value.get('conditions'))
        for key in ('denominator','N','n','N_tasks','N_doc_tasks','sample_size','分母'):
            if key in value:context['denominator']=value[key]
        if 'verdict' in value:context['component_verdict']=value['verdict']
        if type(value.get('formula_consistent')) is bool:context['formula_consistent']=value['formula_consistent']
        derived=derived_semantics(value,registry)
        if derived:
            lineage.append({'source_pointer':pointer,'transform':'declared result/unit/formula','raw':value,'normalized':derived})
            visit(derived,context,pointer+':declared_result')
        quantity=value.get('quantity',value.get('metric'))
        if quantity is not None and ('value' in value or 'numerator' in value or 'state' in value or 'status' in value):
            actual=value.get('value',value.get('numerator',value.get('state',value.get('status'))))
            if value.get('status')=='unknown' or value.get('state')=='unknown':actual=None
            add(quantity,actual,context,pointer,value.get('unit'),value.get('denominator'));components.append({'quantity':role(quantity),'verdict':value.get('verdict'),'pointer':pointer})
        for key,item in value.items():
            child=dict(context);rid=resolve_subject(key,registry,item.get('version') if isinstance(item,dict) else None)
            if rid:child['report_id']=rid
            if re.fullmatch(r'[A-Za-z]+[-_][A-Za-z0-9]+',key) and not rid and role(key) is None:child['arm']=key.replace('_','-')
            q,key_unit,key_subject=key_semantics(key,registry)
            if key_subject and context.get('report_id') and key_subject!=context['report_id']:
                unhandled.append({'pointer':pointer+'/'+str(key),'explicit_report_id':context['report_id'],'key_report_id':key_subject,'reason':'quantity prefix conflicts with explicit parent report; typed review'})
                continue
            if key_subject:child['report_id']=key_subject;child['report_ids']=[]
            if q and key not in ('quantity','metric','state','status','unit') and not isinstance(item,(dict,list)):
                if q=='time_unit_ms' and isinstance(item,str):
                    definition=re.fullmatch(r'\s*1\s*U_T\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s|milliseconds?|seconds?)\s*',item,re.I)
                    if definition:
                        add(q,definition[1],child,pointer+'/'+str(key),definition[2]);continue
                arrow=re.fullmatch(r'\s*([^→←]+?)\s*(→|←|->)\s*([^→←]+?)\s*',str(item))
                if arrow and q in ('policy','tool_total_ceiling_per_task','max_attempt_starts_per_task'):
                    candidates=set(context.get('report_ids',[]));current=context.get('report_id')
                    if current:candidates.add(current)
                    family=registry['sources']['reports'].get(current,{}).get('work_id')
                    candidates=[r for r in candidates if not family or registry['sources']['reports'][r]['work_id']==family]
                    def version_order(r):
                        v=registry['sources']['reports'][r]['version'];m=re.fullmatch(r'v?([0-9]+(?:\.[0-9]+)*)',str(v));return tuple(map(int,m[1].split('.'))) if m else ()
                    candidates=sorted(candidates,key=version_order)
                    if len(candidates)==2 and version_order(candidates[0]) and version_order(candidates[0])!=version_order(candidates[1]):
                        before,after=arrow[1],arrow[3]
                        if arrow[2]=='←':before,after=after,before
                        if q!='policy':
                            before_match=re.fullmatch(r'([0-9]+)\s*(?:total/task|starts/task|calls/task|tool calls/task)?',before.strip(),re.I);after_match=re.fullmatch(r'([0-9]+)\s*(?:total/task|starts/task|calls/task|tool calls/task)?',after.strip(),re.I)
                            if not before_match or not after_match:unhandled.append({'pointer':pointer+'/'+key,'change':item,'reason':'arrow endpoints not faithful scalar settings'});continue
                            before,after=before_match[1],after_match[1]
                        for source,actual in zip(candidates,(before,after)):
                            add(q,actual,{**context,'report_id':source,'report_ids':[]},pointer+'/'+key+':version='+source,key_unit)
                        lineage.append({'source_pointer':pointer+'/'+key,'transform':'directed old/new declared version settings','raw':item,'reports':candidates});continue
                    unhandled.append({'pointer':pointer+'/'+key,'change':item,'reason':'directed change lacks exactly two ordered source versions'});continue
                denominator=None
                if q=='unsafe_flags':
                    possible=[v for k,v in value.items() if re.fullmatch(r'(?:separate_)?N_(?:sandbox|safety)_executions',str(k),re.I)]
                    if len(possible)==1:denominator=possible[0]
                add(q,item,child,pointer+'/'+str(key),value.get('unit',key_unit),denominator)
            elif isinstance(item,(dict,list)):
                if role(key) and isinstance(item,dict) and ('value' in item or 'state' in item or 'status' in item):
                    child_item=dict(item);child_item.setdefault('quantity',key);visit(child_item,child,pointer+'/'+str(key))
                else:visit(item,child,pointer+'/'+str(key))
            elif isinstance(item,str) and key not in ('metric','quantity','unit','verdict','report','report_id','document_id','file','version','kind'):
                prose(item,child,pointer+'/'+str(key),key in ('matched','condition','conditions','quantile','quantile_convention'))
        if any(re.fullmatch(r'(?:separate_)?N_(?:sandbox|safety)_executions',str(k),re.I) for k in value) and any(key_semantics(k,registry)[0]=='unsafe_flags' for k in value):
            add('evidence_scope','sandbox',context,pointer+':explicit_sandbox_population_role')
    def packed_conditions(value,context,pointer):
        # Only a declared condition/matched/quantile field or an explicitly shared
        # condition clause is eligible. Nothing is inferred from a global number bag.
        rows=[];words={'一':'1','二':'2','两':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','十':'10'}
        text=str(value)
        def numeric(v):return words.get(v,v)
        policy=re.search(r'(?<![A-Za-z0-9_])(L[0-9]+)(?![A-Za-z0-9_])',text)
        if policy:rows.append(('policy',policy[1],None))
        calls=re.search(r'(\d+)\s*(?:次)?\s*(?:工具调用|(?:issued\s+tool|total\s+tool|total)\s*calls)',text,re.I)
        if calls:rows.append(('tool_total_ceiling_per_task',calls[1],'tool_calls'))
        starts=re.search(r'(?:最多|max(?:imum)?\s*|at\s+most\s*)([0-9]+|[一二两三四五六七八九十])\s*(?:次)?(?:尝试|启动|attempts?|starts?)',text,re.I)
        if starts:rows.append(('max_attempt_starts_per_task',numeric(starts[1]),'attempt_starts'))
        host=re.search(r'(?<![A-Za-z0-9_])(H[0-9]+(?:-[0-9]+)+)(?![A-Za-z0-9_])',text)
        if host:rows.append(('host',host[1],None))
        step=re.search(r'(?:after\s+(?:the\s+)?(?:completed\s+)?step\s*|完成第)([0-9]+|[一二两三四五六七八九十])(?:步)?',text,re.I)
        if step:rows.append(('reset_step',numeric(step[1]),None))
        rank=re.search(r'\brank\s*([0-9]+)\s*/\s*([0-9]+)',text,re.I)
        if rank:rows.append(('quantile_rank',rank[1]+'/'+rank[2],None))
        for q,actual,u in rows:add(q,actual,context,pointer+':bounded_condition_role='+q,u)
        if rows:lineage.append({'source_pointer':pointer,'transform':'bounded declared condition roles','raw':value,'roles':[q for q,_,_ in rows]})
    def prose(value,context,pointer,allow_conditions=False):
        # Only explicit local role/value syntax and directly adjacent ordinary
        # clauses are parsed. No global number/keyword bag certifies a fact.
        current=dict(context)
        if allow_conditions:packed_conditions(value,current,pointer)
        for part in re.split(r'[;；\n。]',value):
            if not part.strip():continue
            found=[rid for alias,rids in registry['aliases'].items() if alias and len(rids)==1 and alias in norm(part) for rid in rids]
            if len(set(found))==1:current['report_id']=found[0]
            arm=re.search(r'\b[A-Z]+[-_][A-Z0-9]+\b',part)
            if arm and norm(arm[0]) not in registry['aliases']:current['arm']=arm[0].replace('_','-')
            explicit=re.finditer(r'([A-Za-z_][A-Za-z0-9_ -]*|[\u3400-\u9fff]+)\s*[:=：]\s*([^,，;；]+)',part)
            matched=False
            for match in explicit:
                key=match[1].strip();q=role(key)
                if q is None:
                    for alias in sorted(ROLES,key=len,reverse=True):
                        if norm(key).endswith(alias):
                            prefix=norm(key)[:-len(alias)]
                            if resolve_subject(prefix,registry):current['report_id']=resolve_subject(prefix,registry);q=ROLES[alias];break
                if q:
                    add(q,match[2].strip(),current,pointer+':chars'+str(match.span()));matched=True
            if matched:continue
            for alias,q in ROLES.items():
                if len(alias)<2:continue
                # Preserve original span; matching is within this role clause,
                # not another paragraph or source document.
                match=re.search(re.escape(alias)+r'\s*(?:为|是|=|:|：)?\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:\s*/\s*\d+(?:\.\d+)?)?\s*(?:%|百分点|ms|s|CU/task)?)',norm(part),re.I)
                if match:add(q,match[1],current,pointer+':role_clause');matched=True
            if not matched and rich(part):unhandled.append({'pointer':pointer,'prose':part,'review':'Meaning not mechanically confirmed; no keyword truth inference'})
    def declared_subjects(value):
        found=set()
        if isinstance(value,dict):
            for key,item in value.items():
                rid=resolve_subject(key,registry,item.get('version') if isinstance(item,dict) else None)
                if rid:found.add(rid)
                if key in ('report','report_id','document_id','file'):
                    rid=resolve_subject(item,registry,value.get('version'))
                    if rid:found.add(rid)
                found.update(declared_subjects(item))
        elif isinstance(value,list):
            for item in value:found.update(declared_subjects(item))
        return found
    for key in ('comparison','components'):
        if key in claim:visit(claim[key],{'report_ids':sorted(declared_subjects(claim[key]))},'/'+key)
    target=claim.get('assessment_target');target=target.get('text') if isinstance(target,dict) else target
    if isinstance(target,str) and re.search(r'相应报告条件下|相同[^。]*条件|under\s+(?:the\s+)?(?:same|shared)[^.]*conditions',target,re.I):
        packed_conditions(target,{'report_ids':sorted(declared_subjects(claim.get('comparison',{})))},'/assessment_target:explicit_shared_conditions')
    return {'observations':result,'unhandled':unhandled,'components':components,'normalization_lineage':lineage}
def _matching(query,observed):
    reports=query.get('report_ids',[query['report_id']] if query.get('report_id') else [])
    return [o for o in observed if o['quantity']==query['quantity'] and (not reports or o['report_id'] in reports) and (not query.get('arm') or norm(o.get('arm')).replace('_','-')==norm(query['arm']).replace('_','-'))]
def _decimal(value):
    if type(value) is bool:return None
    try:d=Decimal(str(value));return d if d.is_finite() else None
    except (InvalidOperation,TypeError,ValueError):return None
def number_match(query,observation,all_observations):
    if observation.get('formula_consistent') is False:return False
    expected=_decimal(query['expected']);actual=observation['number']
    if expected is None:raise RuntimeError('trusted numeric anchor not finite')
    if actual is None:return None if rich(observation['raw_value']) else False
    value=actual['value'];actual_unit=unit(observation.get('unit') or actual.get('unit'));expected_unit=unit(query.get('unit'))
    den=actual.get('denominator',_decimal(observation.get('denominator')))
    if expected_unit=='count_rate':
        expected_den=_decimal(query.get('denominator'))
        if expected_den is None:return False
        if den is None:return None
        if den!=expected_den:return False
        if actual_unit in ('count',None,'count_rate'):return value==expected
        if actual_unit=='percent':return abs(value-expected/expected_den*100)<=Decimal('0.05')
        if actual_unit=='ratio':return abs(value-expected/expected_den)<=Decimal('0.0005')
        return None
    if expected_unit in ('milliseconds','seconds'):
        factors={'seconds':Decimal(1000),'milliseconds':Decimal(1)}
        if actual_unit=='U_T':
            definitions=[o for o in all_observations if o['quantity']=='time_unit_ms' and o['report_id']==observation['report_id'] and o['number']]
            if not definitions:return None
            definition=definitions[0];coefficient=definition['number']['value']*(Decimal(1000) if definition['unit']=='seconds' else Decimal(1));value*=coefficient;actual_unit='milliseconds'
        if actual_unit not in factors:return None
        return abs(value*factors[actual_unit]-expected*factors[expected_unit])<=Decimal('0.000001')
    if expected_unit and actual_unit!=expected_unit:return False if actual_unit is not None else None
    tolerance=Decimal(5)*(Decimal(10)**(-int(query.get('rounding_digits',6))-1))
    return abs(value-expected)<=tolerance
def evaluate_query(query,normalized,registry,documents):
    observed=normalized['observations'];op=query['op'];matches=_matching(query,observed) if 'quantity' in query else []
    def result(status,detail,used=None):return {'status':status,'query':query,'observed':used if used is not None else matches,'detail':detail}
    if op in ('number','library_count'):
        if op=='library_count':query=dict(query,unit='count')
        values=[number_match(query,o,observed) for o in matches]
        if values and all(v is True for v in values):return result('pass','Actual role/subject/unit/denominator numeric observations match frozen operand(s)')
        if any(v is False for v in values):return result('fail','An explicit scoped numeric observation contradicts the frozen operand')
        return result('needs_judge','No safely normalized required quantitative role/value, or legal value representation not mechanically decidable')
    if op in ('state','setting'):
        reports=query.get('report_ids',[])
        if matches and reports and not set(reports).issubset({o['report_id'] for o in matches}):return result('needs_judge','Shared condition does not yet bind every declared comparison report')
        if op=='setting' and not matches and query['quantity']=='time_unit_ms':
            equivalent=[o for o in observed if o['report_id']==query.get('report_id') and o['quantity']=='p95' and o['unit']=='milliseconds' and o['number']]
            if equivalent:return result('pass','Explicit canonical timing unit is part of the declared value; independent source dictionary separately verified',equivalent)
        if op=='setting' and not matches and query['quantity']=='timing_population':
            ranks=[o for o in observed if o['quantity']=='quantile_rank' and o['number'] and o['number'].get('denominator')==_decimal(query['expected'])]
            if ranks and (not reports or set(reports).issubset({o['report_id'] for o in ranks})):return result('pass','Population is explicit denominator of declared rank; no duplicated field required',ranks)
        if op=='state':values=[o['state']==query['expected'] if o['state'] is not None else False for o in matches if o['state'] is not None or o['number'] is not None]
        else:
            values=[]
            for o in matches:
                raw=o['raw_value'];numeric=_decimal(query['expected'])
                if numeric is not None and o['number'] and query.get('unit'):
                    values.append(number_match(dict(query,op='number'),o,observed))
                else:values.append(o['number']['value']==numeric if numeric is not None and o['number'] else norm(raw)==norm(query['expected']))
        if matches and values and all(v is True for v in values):return result('pass','Explicit observed state/condition matches source table')
        if any(v is False for v in values):return result('fail','Explicit observed state/condition conflicts with source table')
        return result('needs_judge','Clear state/condition prose or context needs semantic mapping; no keyword-only award')
    if op in ('same_work','distinct_versions'):
        requested=query['report_ids'];rows=[]
        for document in documents:
            if isinstance(document,dict) and document.get('document_id') in registry['doc_sources']:
                source=registry['doc_sources'][document['document_id']]
                if source['report_id'] in requested:rows.append((document,source))
        if {s['report_id'] for d,s in rows}!=set(requested):return result('needs_judge','Public relationship text not safely mapped to complete relevant report/version identities',rows)
        work_ids=[d.get('work_id') for d,s in rows];known=all(isinstance(w,str) and norm(w) not in ('unknown','未知','') for w in work_ids)
        if op=='same_work':ok=known and len(set(work_ids))==1
        else:ok=len({s['version'] for d,s in rows})==len(requested) and all(not registry['doc_mismatches'].get(d['document_id']) for d,s in rows)
        return result('pass' if ok else 'fail','Actual source file/version partition and candidate relationship compared, not ID spelling',rows)
    if op=='distinct_quantities':
        rows=[o for o in observed if o['quantity'] in query['quantities'] and (not query.get('report_id') or o['report_id']==query['report_id']) and (not query.get('arm') or norm(o.get('arm')).replace('_','-')==norm(query['arm']).replace('_','-'))]
        ok=set(o['quantity'] for o in rows)==set(query['quantities'])
        return result('pass' if ok else 'needs_judge','Distinct actually declared predicates, not one scalar relabelled twice',rows)
    if op=='configuration_change':
        before=[o for o in observed if o['quantity']==query['quantity'] and o['report_id']==query['report_ids'][0]];after=[o for o in observed if o['quantity']==query['quantity'] and o['report_id']==query['report_ids'][1]]
        if not before or not after:return result('needs_judge','Configuration-change prose needs faithful role normalization',before+after)
        ok=all(norm(o['raw_value'])==norm(query['before']) for o in before) and all(norm(o['raw_value'])==norm(query['after']) for o in after)
        return result('pass' if ok else 'fail','Before/after actual source roles compared',before+after)
    raise RuntimeError('trusted machine query operator unsupported: '+str(op))

def evaluate_claim(claim,anchor,registry,documents,normalize_verdict,normalize_target):
    if not isinstance(claim,dict):return {'score':0.,'missing':True,'checks':{},'pending_semantic':[]}
    required=('claim_id','input_ref','assessment_target','verdict','rationale','comparison','limitations')
    shape=all(key in claim for key in required) and all(rich(claim.get(k)) for k in ('assessment_target','rationale','comparison','limitations'))
    if not shape:return {'score':0.,'missing':False,'checks':{'public_meaning_fields':False},'pending_semantic':[]}
    normalized=observations(claim,registry);label=normalize_verdict(claim.get('verdict'));kind=normalize_target(claim.get('assessment_target'));routes=anchor['routes']
    if kind is None and isinstance(claim.get('assessment_target'),str):
        target=claim['assessment_target']
        if re.search(r'证据(?:充分|足够)|已经证明|已证明|proof|evidence.sufficien',target,re.I):kind='evidence_sufficiency'
        elif len({r.get('kind') for r in routes if r.get('kind')})<=1:kind='fact'
    ordinary=[r for r in routes if not r.get('component_only') and r['verdict']==label and (r.get('kind') is None or r['kind']==kind)]
    verdict_ok=bool(ordinary);queries=anchor['queries']
    atoms=[evaluate_query(q,normalized,registry,documents) for q in queries.get('atoms',[])];conditions=[evaluate_query(q,normalized,registry,documents) for q in queries.get('conditions',[])]
    optional=[evaluate_query(q,normalized,registry,documents) for q in queries.get('optional_atoms',[]) if _matching(q,normalized['observations'])]
    component_route=queries.get('component_route')
    if not verdict_ok and component_route and label==component_route['top_verdict']:
        target=claim.get('assessment_target');quantity=role(target.get('quantity',target.get('text'))) if isinstance(target,dict) else role(target)
        explicit_negative=any(o['quantity']==component_route['required_component_quantity'] and o['state']=='false' for o in normalized['observations'])
        if quantity==component_route['target_quantity'] and explicit_negative and all(a['status']=='pass' for a in atoms):verdict_ok=True
    pending=[a for a in atoms+conditions+optional if a['status']=='needs_judge']
    condition_minimum=queries.get('condition_minimum',len(conditions))
    condition_pass=sum(c['status']=='pass' for c in conditions)
    # A source-supported minimum of independently changed conditions is enough;
    # an unneeded third condition is not a hidden completeness obligation.
    if condition_pass>=condition_minimum:pending=[a for a in pending if a in atoms or a in optional]
    atom_score=sum(a['status']=='pass' for a in atoms)/len(atoms) if atoms else 0.
    if any(a['status']=='fail' for a in optional):atom_score=0.
    condition_score=min(1.,condition_pass/condition_minimum) if condition_minimum else 1.
    needed={rid for q in queries.get('atoms',[])+queries.get('conditions',[]) for rid in q.get('report_ids',[q['report_id']] if q.get('report_id') else [])}
    used={o['report_id'] for o in normalized['observations'] if o['report_id']}
    for q in queries.get('atoms',[])+queries.get('conditions',[]):
        if q['op'] in ('same_work','distinct_versions'):
            used.update(source['report_id'] for source in registry['doc_sources'].values() if source['report_id'] in q['report_ids'])
    context_ok=bool(needed) and needed.issubset(used)
    for did,bad in registry['doc_mismatches'].items():
        if bad and registry['doc_sources'][did]['report_id'] in used:context_ok=False
    for did,value in registry.get('doc_pending_versions',{}).items():
        if registry['doc_sources'][did]['report_id'] in used:pending.append({'status':'needs_judge','document_id':did,'declared_version':value,'detail':'Legal clear version representation not safely normalized; actual source file remains independently bound'})
    checks={'verdict_route':float(verdict_ok),'observable_atoms':atom_score,'conditions_and_roles':condition_score,'independent_source_context':float(context_ok)}
    score=.25*checks['verdict_route']+.35*atom_score+.20*condition_score+.20*checks['independent_source_context']
    return {'score':score,'missing':False,'checks':checks,'atoms':atoms,'optional_asserted_atoms':optional,'conditions':conditions,'normalized_observations':normalized,'pending_semantic':pending,'scientific_semantics_not_certified':True,'semantic_route_boundaries':[r['semantic_boundary'] for r in routes]}
