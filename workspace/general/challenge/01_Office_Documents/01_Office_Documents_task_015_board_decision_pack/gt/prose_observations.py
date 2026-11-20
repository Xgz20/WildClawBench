"""Staged reader extension; install only after the current immutable control run is terminal."""
def prose_history(paragraphs,contract,io):
    from collections import defaultdict
    import re
    result=defaultdict(lambda:defaultdict(list))
    aliases=contract['channel_aliases']
    for p in paragraphs:
        text=io['clean'](p.get('text',''))
        # Clearly labeled record prose, not a quote or a refuted interview assertion.
        prefix=text[:50]
        if not re.search(r'20(?:25|26)\s*年?\s*(?:Q3|第三季度)',prefix,re.I):continue
        years=set(re.findall(r'20(?:25|26)',prefix))
        if len(years)!=1:continue
        choices=[key for key,names in aliases.items() if any((re.search(r'\b'+re.escape(a)+r'\b',prefix,re.I) if a.isascii() else a in prefix) for a in names)]
        if len(choices)!=1:continue
        if not (re.match(r'^20(?:25|26)',text) or any(text.startswith(a) for a in aliases[choices[0]])):continue
        identity=next(iter(years))+'/'+choices[0]
        for field in ['revenue_cny','gross_profit_cny','gross_margin','receipts_cny','receipts_revenue_ratio']:
            names='|'.join(re.escape(n) for n in sorted(contract['field_aliases'][field],key=len,reverse=True))
            pattern=r'(?:'+names+r')\s*(?:为|是|:|：|=)?\s*([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:万元|元|CNY|%)?)'
            for value in re.findall(pattern,text,re.I):
                result[identity][field].append({'value':value,'observed':io['scalar'](value,field,contract=contract),'field':field,'locator':p['locator'],'type':'prose'})
    return {k:dict(v) for k,v in result.items()}
