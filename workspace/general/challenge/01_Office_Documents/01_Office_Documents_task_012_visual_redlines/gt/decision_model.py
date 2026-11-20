"""Synthetic A1-A5 paper-state rules. Pixels must be independently observed first."""
from itertools import product
def decide(observed):
    cancelled=observed['proposal_cancelled'];choice=observed['selection'];a=observed['confirmation_a'];b=observed['confirmation_b']
    if cancelled is True:return 'withdrawn'
    if cancelled is None:return 'uncertain'
    if choice=='reject':return 'rejected'
    if choice in {'blank','conflict'}:return 'pending'
    if choice!='adopt':return 'uncertain'
    if a is False or b is False:return 'pending'
    if a is None or b is None:return 'uncertain'
    if not observed['proposal_readable']:return 'uncertain'
    condition=observed['condition_kind']
    if condition=='none':return 'confirmed'
    if condition=='unreadable' or observed['condition_met'] is None:return 'uncertain'
    return 'confirmed' if observed['condition_met'] else 'conditional'

def completion_oracle(observed):
    """Independent completion-set formulation, retaining unknown text/condition identities."""
    cancelled=[observed['proposal_cancelled']] if observed['proposal_cancelled'] is not None else [False,True]
    choices=[observed['selection']] if observed['selection']!='unreadable' else ['adopt','reject','blank','conflict']
    roles=lambda v:[v] if v is not None else [False,True]
    content=['visible'] if observed['proposal_readable'] else ['latent-value-1','latent-value-2']
    kind=observed['condition_kind']
    if kind=='none':conditions=[(None,True)]
    elif kind=='readable':conditions=[('visible-condition',v) for v in roles(observed['condition_met'])]
    else:conditions=[(text,met) for text in ['latent-condition-1','latent-condition-2'] for met in [False,True]]
    outcomes=set()
    for cancel,choice,a,b,text,(condition,met) in product(cancelled,choices,roles(observed['confirmation_a']),roles(observed['confirmation_b']),content,conditions):
        if cancel:result=('withdrawn',None,None)
        elif choice=='reject':result=('rejected',None,None)
        elif choice in {'blank','conflict'} or not(a and b):result=('pending',None,None)
        elif condition is None or met:result=('confirmed',text,condition)
        else:result=('conditional',text,condition)
        outcomes.add(result)
    return next(iter(outcomes))[0] if len(outcomes)==1 else 'uncertain'

def from_intent(row):
    condition=row['condition']
    return {'proposal_cancelled':row['proposal_cancelled'],'selection':row['selection'],
        'confirmation_a':row['confirmation_a'],'confirmation_b':row['confirmation_b'],
        'proposal_readable':not('proposed_amount' in row['unreadable_fields']),
        'condition_kind':'none' if condition is None else 'unreadable' if condition=='UNREADABLE_CONDITION' else 'readable',
        'condition_met':row['condition_met']}

def truth_table_validation():
    count=0
    for cancel,choice,a,b,readable,condition,met in product([False,True,None],['adopt','reject','blank','conflict','unreadable'],
            [False,True,None],[False,True,None],[False,True],['none','readable','unreadable'],[False,True,None]):
        observed={'proposal_cancelled':cancel,'selection':choice,'confirmation_a':a,'confirmation_b':b,'proposal_readable':readable,'condition_kind':condition,'condition_met':met}
        one,two=decide(observed),completion_oracle(observed)
        assert one==two,(observed,one,two);count+=1
    return count
