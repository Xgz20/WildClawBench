"""Independent comparison/date/scope model; never reads final labels/artifacts."""
from datetime import date
import re


def norm(value): return re.sub(r'\s+','',str(value))


def classify(raw):
    cutoff=date.fromisoformat(raw['cutoff'])
    certificates={row['id']:row for row in raw['certificates']}
    result=[]
    for row in raw['requirements']:
        proof=row.get('certificate_id')
        cert_state='不要求'
        if proof:
            cert=certificates[proof]
            if cutoff < date.fromisoformat(cert['start']): cert_state='未生效'
            elif cutoff > date.fromisoformat(cert['end']): cert_state='过期'
            elif norm(cert['holder'])!=norm(raw['holder']) or norm(cert['scope'])!=norm(row['certificate_scope']): cert_state='范围不符'
            else: cert_state='有效'
            # Only a currently applicable proof confirms compliance. An old or
            # wrong-scope certificate does not prove that no other proof exists.
            coverage='已覆盖' if cert_state=='有效' else '待核实'
            tests=[cert_state=='有效']
        else:
            tests=[]
            for predicate in row['predicates']:
                actual=row['values'].get(predicate['field'])
                if actual is None: tests.append(None)
                elif predicate['op']=='eq': tests.append(actual==predicate['value'])
                elif predicate['op']=='ge': tests.append(actual>=predicate['value'])
                elif predicate['op']=='le': tests.append(actual<=predicate['value'])
                else: raise ValueError('unsupported author predicate')
            if not tests or None in tests: coverage='待核实'
            elif all(tests): coverage='已覆盖'
            elif any(tests): coverage='部分覆盖'
            else: coverage='不满足'
        if row['draft_id'] is None: draft='缺失'
        elif cert_state=='过期': draft='证书过期'
        elif row['claims_fully_met'] and coverage!='已覆盖': draft='过度承诺'
        elif coverage=='部分覆盖': draft='部分覆盖'
        else: draft='已覆盖'
        result.append({'req_id':row['req_id'],'mandatory':'是' if row['mandatory'] else '否','draft_status':draft,
            'coverage':coverage,'certificate_status':cert_state,'predicate_results':tests})
    return result
