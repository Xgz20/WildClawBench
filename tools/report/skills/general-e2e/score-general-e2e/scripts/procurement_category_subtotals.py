"""Read explicit category-column subtotals and yuan literals without editing cells."""
import hashlib
import procurement_explicit_labels as labels
import procurement_signed_summary as signed

PROFILE='procurement-explicit-category-subtotals-currency/v1'

def marker(contract,contract_sha,dataset):
    if signed.marker(contract,contract_sha,dataset) is None:return None
    return {'profile':PROFILE,'contract_sha256':contract_sha,'source_sha256':labels.SOURCE,
            'predecessor_profile':signed.PROFILE,
            'predecessor_bridge_sha256':hashlib.sha256(signed.BRIDGE.encode()).hexdigest()}

BRIDGE=r'''
_pcs_previous_view=_pl_matrix_view
def _pl_matrix_view(tables,records,metrics,numeric,truth,*args):
    converted,expected,locations,audit=_pcs_previous_view(tables,records,metrics,numeric,truth,*args)
    headers=('异常类别','笔数','金额差额合计(元)','说明')
    categories=('数量差异','金额差异','未入库订单','无对应订单入库')
    for index,(source,view) in enumerate(zip(tables,converted)):
        if source['kind']!='summary' or source['sheet']!=view['sheet']:continue
        replacement={}
        def project(row,column,label,key,value):
            hidden=[]
            if 0 in row.get('hidden_columns',[]):hidden.append(0)
            if column in row.get('hidden_columns',[]):hidden.append(1)
            item={**row,'values':[_PssClaim(label,key),value],'hidden_columns':hidden}
            location=source['sheet']+'!'+get_column_letter(column+1)+str(row['row'])
            locations[(source['sheet'],row['row'],label)]={'value_location':location,
                'extraction_profile':'procurement-explicit-category-subtotals-currency/v1'}
            audit.append({'location':location,'key':key,'original_label':row['values'][0],
                'original_value':row['values'][column],'projected_numeric_token':value,
                'candidate_statement_synthesized':False,'candidate_bytes_rewritten':False,
                'profile':'procurement-explicit-category-subtotals-currency/v1'})
            return item
        for row in source['rows']:
            vals=row['values']
            if len(vals)==2 and vals[0]=='成功匹配笔数(订单↔入库)' and number(vals[1]) is not None:
                replacement[row['row']]=[project(row,1,vals[0],'matched',vals[1])]
            key={'未入库订单金额':'missing_amount','无对应订单入库金额':'orphan_amount'}.get(vals[0] if vals else None)
            if key and 2<=len(vals)<=4 and isinstance(vals[1],str):
                match=re.fullmatch(r'\s*([-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*元\s*',vals[1])
                if match:
                    item=project(row,1,vals[0],key,match[1])
                    # Keep the original notes: embedded counts remain original count claims.
                    item['values'] += vals[2:]
                    item['hidden_columns']=list(row.get('hidden_columns',[]))
                    replacement[row['row']]=[item]
        heads=[i for i,row in enumerate(source['rows']) if tuple(row['values'])==headers]
        if len(heads)==1:
            start=heads[0];head=source['rows'][start];section=source['rows'][start+1:start+6]
            if (len(section)==5 and tuple(r['values'][0] for r in section[:4])==categories
                and [r['row'] for r in section]==list(range(head['row']+1,head['row']+6))
                and section[-1]['values'][0]=='异常合计' and len(section[-1]['values'])==4
                and section[-1]['values'][3]=='金额差异净额；两类未匹配金额需单独核对'
                and not any(r.get('hidden_columns') for r in [head,*section])):
                counts=[number(r['values'][1]) if len(r['values'])>1 else None for r in section[:4]]
                last=section[-1]
                if (all(n is not None and n==n.to_integral_value() for n in counts)
                    and number(last['values'][1]) is not None and number(last['values'][2]) is not None):
                    key='pcs_literal_category_count';expected[key]=sum(counts,Decimal(0))
                    replacement[last['row']]=[
                        project(last,1,'异常合计（分类笔数列合计）',key,last['values'][1]),
                        project(last,2,'异常合计（金额差异净额）','net_amount',last['values'][2])]
        rows=[]
        for row in view['rows']:rows.extend(replacement.get(row['row'],[row]))
        converted[index]={**view,'rows':rows}
    return converted,expected,locations,audit
'''

def effective_source(manifest,original,current,prior):
    frozen=manifest.get('runtime',{}).get('procurement_category_subtotal_profile')
    if frozen is None:return current,prior
    expected=marker({'task_id':manifest['identity']['task_id'],'automated_checks':original},
        manifest['digests']['contract_sha256'],manifest['dataset'])
    if (expected is None or frozen!=expected or (prior or {}).get('correction_id')!=signed.PROFILE
        or (prior or {}).get('original_source_sha256')!=labels.SOURCE
        or hashlib.sha256(current.encode()).hexdigest()!=(prior or {}).get('effective_source_sha256')):
        raise ValueError('PROCUREMENT_CATEGORY_SUBTOTAL_PROFILE_MISMATCH')
    effective=current+BRIDGE
    receipt={'schema_version':'wildclawbench.general-e2e-rule-source-correction/v1','correction_id':PROFILE,
        'task_id':labels.TASK,'contract_sha256':labels.CONTRACT,'original_source_sha256':labels.SOURCE,
        'effective_source_sha256':hashlib.sha256(effective.encode()).hexdigest(),
        'candidate_rewritten':False,'numeric_decisions_assigned':False,'rubric_and_weights_changed':False,
        'prior_correction':prior,
        'reason':'只读取明确订单↔入库匹配标签、元金额文字及连续分类区段的笔数列字面小计与明示金额净额；保留原值、备注中笔数、定位和可见性，不将分类笔数和当独立订单数。原金额比较、上下游归因、分母、检查点及80/20不变，模糊声明继续拒绝。'}
    return effective,receipt
