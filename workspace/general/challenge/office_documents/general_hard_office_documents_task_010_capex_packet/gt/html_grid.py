"""Expand passive HTML table spans and preserve physical and tbody row indexes."""
import re

def table_grid(table,render):
    def rows(node,section=None):
        if isinstance(node,str) or (node['tag']=='table' and node is not table):return
        if node['tag'] in {'thead','tbody','tfoot'}:section=node['tag']
        if node['tag']=='tr':yield section,node;return
        for child in node['children']:yield from rows(child,section)
    raw=list(rows(table))
    if len(raw)>2000:raise ValueError('HTML table row limit')
    spans={};output=[];body_rows={};body_index=0
    def extent(value,remaining,zero=False):
        literal=str(value or '1').strip()
        if not re.fullmatch(r'[0-9]{1,4}',literal):return 1
        number=int(literal)
        if number==0:return remaining if zero else 1
        if number>256:raise ValueError('HTML table span limit')
        return number
    for i,(section,row) in enumerate(raw,1):
        physical={};next_spans={}
        for col,(value,left) in spans.items():
            physical[col]=value
            if left>1:next_spans[col]=(value,left-1)
        cells=[c for c in row['children'] if isinstance(c,dict) and c['tag'] in {'td','th'}]
        header=section=='thead' or bool(cells and all(c['tag']=='th' for c in cells))
        if not header:body_index+=1;body_rows[i]=body_index
        col=0;visible=bool(render(row).strip())
        for cell in cells:
            while col in physical:col+=1
            width=extent(cell['attrs'].get('colspan'),256);height=extent(cell['attrs'].get('rowspan'),len(raw)-i+1,True)
            for offset in range(width):
                target=col+offset
                if target in physical or target>=256:raise ValueError('overlapping HTML table grid')
                value=render(cell).strip() if visible and offset==0 else ''
                physical[target]=value
                if height>1:next_spans[target]=(value,height-1)
            col+=width
        output.append([physical.get(c,'') for c in range(max(physical,default=-1)+1)])
        spans=next_spans
    return {'rows':output,'body_rows':body_rows}
