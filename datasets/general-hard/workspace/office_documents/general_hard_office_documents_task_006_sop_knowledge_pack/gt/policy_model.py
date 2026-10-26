"""Case transitions from source policy; never reads declared labels or outputs."""
def decide(case,authority,numeric):
    approval='FC' if case['amount_cny']>=numeric['approval_threshold'] else 'OPS'
    valid=case['approved_by']==approval and case['approval_written'] and case['approval_after_inspection']
    conditions={
      'joint_hold':case['safety_risk'] and case['privacy_risk'],'safety_hold':case['safety_risk'],'privacy_hold':case['privacy_risk'],
      'link_existing':bool(case['linked_case_id']),'withdrawal_review':case['withdrawal_requested'],
      'request_documents':not case['documents_complete'],'await_receipt':not case['received'],'await_inspection':not case['inspected'],
      'request_approval':not valid,'bank_review':case['account_changed'] and not case['current_account_verified'],'ready_finance':True}
    route=next(key for key in authority['routing_priority'] if conditions[key])
    owners={'joint_hold':'OPS','safety_hold':'QA','privacy_hold':'PR','link_existing':'CS','withdrawal_review':'FC',
            'request_documents':'CS','await_receipt':'WH','await_inspection':'QA','request_approval':approval,'bank_review':'FC','ready_finance':'FE'}
    clearances={'joint_hold':['QA','PR'],'safety_hold':['QA'],'privacy_hold':['PR'],'withdrawal_review':['FC'],'bank_review':['FC']}.get(route,[])
    if route=='link_existing':clock='reuse_existing'
    elif case['clock_started']:clock='paused' if route in {'joint_hold','safety_hold','privacy_hold','withdrawal_review','bank_review'} else 'running'
    else:clock='not_started'
    edge_list=[[('REQUEST_'+('FIN' if approval=='FC' else 'OPS')+'_APPROVAL') if node=='REQUEST_APPROVAL' else node for node in edge]
               for edge in authority['FLOW']['dependencies'][route]]
    required=sorted({node for edge in edge_list for node in edge})
    forbid={'OPS_PAY','DELETE_AUDIT','CLAIM_PAID'}
    if route in {'request_documents','await_receipt','await_inspection','request_approval','bank_review'}:forbid.add('PAY_BEFORE_GATE')
    if route=='request_documents':forbid.add('REJECT_FOR_MISSING')
    if route in {'joint_hold','safety_hold','privacy_hold'}:forbid.update(['RELEASE_WITHOUT_CLEARANCE','RESET_CLOCK'])
    if route=='link_existing':forbid.update(['NEW_CASE','RESET_CLOCK'])
    if route=='withdrawal_review':forbid.update(['CLOSE_WITHOUT_FIN','RESET_CLOCK'])
    if route=='bank_review':forbid.update(['SWITCH_BANK_UNVERIFIED','RESET_CLOCK'])
    return {'incident_id':case['incident_id'],'route':route,'next_owner':owners[route],'approval_owner':approval,'execution_owner':'FE',
            'ack_hours':numeric['ack_hours'],'inspection_workdays':numeric['inspection_workdays'],'payment_workdays':numeric['payment_workdays'],
            'clock_state':clock,'clearance_roles':clearances,'required_steps':required,'required_edges':edge_list,'forbidden_steps':sorted(forbid)}
