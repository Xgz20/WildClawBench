"""Legacy configuration loader. Positive values still work for the old API."""
import copy

ALIASES={'timeout_ms':('network','timeout_seconds'),'retry_count':('network','retries'),
         'cache_enabled':('cache','enabled'),'workers':('pipeline','workers'),'output_dir':('output','directory')}

def migrate_config(config):
    value=dict(config or {})
    if value.get('config_version')==2:
        value={key:item for key,item in value.items() if key in {'network','cache','pipeline','output','config_version'}}
    for old,(section,key) in ALIASES.items():
        item=value.pop(old,None)
        if item:
            group=value.setdefault(section,{})
            if not group.get(key):group[key]=item/1000 if old=='timeout_ms' else item
    value['config_version']=2
    return value

def merge_configs(defaults,project=None,user=None,*,with_audit=False):
    result={}
    # Historical order put project last and treated every falsy value as absent.
    for layer in [defaults,user,project]:
        for key,value in migrate_config(layer).items():
            if value:result[key]=value
    if with_audit:return {'config':result,'sources':{},'migrations':[]}
    return result
