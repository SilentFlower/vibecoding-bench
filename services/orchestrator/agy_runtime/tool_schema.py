"""把 Gemini 工具参数映射到原生 JSON Schema，并保留约束改写账本。"""
import copy
from .contract import InputError

TOKEN_PATTERN='^[A-Za-z0-9_=-]{1,4096}$'


def normalize(schema, path='', changes=None):
    """规范化类型并等价拆分已知不兼容约束。@param schema 参数 schema。@param path JSON 路径。@param changes 变更账本。@return 独立 schema。"""
    if changes is None:changes=[]
    if not isinstance(schema,dict):raise InputError('invalid_tool_schema:'+path)
    result=copy.deepcopy(schema)
    kind=result.get('type')
    if isinstance(kind,str) and kind.lower() in ['object','array','string','number','integer','boolean','null']:
        result['type']=kind.lower()
        if kind!=result['type']:changes.append({'path':path+'/type','action':'gemini_type_to_json_schema'})
    if result.get('pattern')==TOKEN_PATTERN:
        # Go RE2 限制单个量词的计数；长度约束与字符约束分开后保持交集语义。
        result['pattern']='^[A-Za-z0-9_=-]+$'
        result['minLength']=max(result.get('minLength',0),1)
        result['maxLength']=min(result.get('maxLength',4096),4096)
        changes.append({'path':path+'/pattern','action':'equivalent_pattern_and_length','minLength':result['minLength'],'maxLength':result['maxLength']})
    pattern=result.get('pattern')
    for count in [1,2]:
        escape='\\'*count
        guard='(?!'+escape+'.'+escape+'.?(?:'+escape+'/|$))'
        characters='[A-Za-z0-9_'+escape+'-.~:@+]'
        single='^'+guard+characters+'{1,200}$'
        collection='^'+guard+characters+'{1,200}(?:'+escape+'/'+guard+characters+'{1,200}){0,14}$'
        if pattern not in [single,collection]:continue
        # RE2 不支持负向前瞻；JSON Schema 的合取与 not 保留相同排除条件。
        exclusion='^'+escape+'.'+escape+'.?(?:'+escape+'/|$)'
        result['pattern']=pattern.replace(guard,'')
        rules=[]
        if pattern==collection:
            result['pattern']=result['pattern'].replace('{0,14}','*')
            exclusion='(?:^|'+escape+'/)'+escape+'.'+escape+'.?(?:'+escape+'/|$)'
            rules.append({'not':{'pattern':'(?:'+escape+'/[^/]*){15}'}})
        rules.append({'not':{'pattern':exclusion}})
        result.setdefault('allOf',[]).extend(rules)
        changes.append({'path':path+'/pattern','action':'lookahead_as_schema_not','segment_limit':15 if pattern==collection else 1})
        break
    props=result.get('properties')
    if props is not None:
        if not isinstance(props,dict):raise InputError('invalid_schema_properties:'+path)
        result['properties']={k:normalize(v,path+'/properties/'+k,changes) for k,v in props.items()}
    for key in ['items','additionalProperties','contains','not','if','then','else','propertyNames']:
        if isinstance(result.get(key),dict):result[key]=normalize(result[key],path+'/'+key,changes)
    for key in ['anyOf','oneOf','allOf','prefixItems']:
        if isinstance(result.get(key),list):result[key]=[normalize(v,path+'/'+key+'/'+str(i),changes) for i,v in enumerate(result[key])]
    for key in ['$defs','definitions','patternProperties','dependentSchemas']:
        if isinstance(result.get(key),dict):result[key]={k:normalize(v,path+'/'+key+'/'+k,changes) for k,v in result[key].items()}
    return result
