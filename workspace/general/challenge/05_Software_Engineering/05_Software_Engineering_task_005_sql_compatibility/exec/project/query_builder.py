"""Legacy SQL generator. The basic customer query still works."""
SCHEMA={'customer':{'id':'number','name':'text','group':'text','region':'text','joined_at':'text','credit':'number'},
        'order':{'id':'number','customer_id':'number','group':'text','amount':'number','note':'text','created_at':'text','select':'text'}}

def build_query(spec):
    table=spec['table']
    if table not in SCHEMA or any(c not in SCHEMA[table] for c in spec['columns']):
        raise ValueError('unknown identifier')
    def predicate(node):
        if node is None: return '1',[]
        for kind,separator in [('all',' AND '),('any',' OR ')]:
            if kind in node:
                fragments=[];params=[]
                for child in node[kind]:
                    part,values=predicate(child);fragments.append(part);params=values+params
                return separator.join(fragments),params
        column=node['column'];op=node['op'];value=node.get('value')
        if column not in SCHEMA[table]: raise ValueError('unknown column')
        if op in ['is_null','is_not_null']:
            return column+(' IS NULL' if op=='is_null' else ' IS NOT NULL'),[]
        if op in ['in','not_in']:
            if not value: return column+(' IN (NULL)' if op=='in' else ' NOT IN (NULL)'),[]
            return column+(' IN (' if op=='in' else ' NOT IN (')+','.join('?' for _ in value)+')',list(value)
        operators={'eq':'=','ne':'!=','gt':'>','gte':'>=','lt':'<','lte':'<='}
        return column+' '+operators[op]+' ?',[value]
    where,params=predicate(spec.get('where'))
    sql='SELECT '+', '.join(spec['columns'])+' FROM '+table+' WHERE '+where
    if spec.get('order_by'):
        sql+=' ORDER BY '+', '.join(o['column']+' '+o.get('direction','asc') for o in spec['order_by'])
    return sql,params
