"""把 Gemini 工具参数映射到原生 JSON Schema，并保留约束改写账本。"""
import copy
from .contract import InputError

TOKEN_PATTERN='^[A-Za-z0-9_=-]{1,4096}$'


def _normalize_array_items(schema, path, changes):
    items = schema.get('items')
    tuple_key = 'prefixItems' if isinstance(schema.get('prefixItems'), list) else 'items'
    members = schema.get(tuple_key)
    # AGY 会省略裸空对象；单分支空 schema 保持任意 JSON 值，并让原生模型收到 items 字段。
    unrestricted = {'anyOf': [{}]}
    if not isinstance(members, list):
        if isinstance(items, dict) and items:
            schema['items'] = normalize(items, path + '/items', changes)
        elif items is None or isinstance(items, bool) or items == {}:
            if items is False:
                schema['maxItems'] = 0
            schema['items'] = unrestricted
            changes.append({'path': path + '/items', 'action': 'array_items_as_schema'})
        return

    schema.pop(tuple_key)
    tail_key = 'additionalItems' if tuple_key == 'items' else 'items'
    tail = schema.pop(tail_key, None)
    options = []
    limit = len(members)
    maximum = schema.get('maxItems')
    # Gemini 的 int64 字段也可用十进制字符串表示，闭合元组应保留这类更严格的上限。
    if isinstance(maximum, str) and len(maximum) <= 19 and maximum.isascii() and maximum.isdecimal():
        maximum = int(maximum)
    reachable = members[:maximum] if type(maximum) is int and maximum >= 0 else members
    for index, member in enumerate(reachable):
        if member is False:
            # 第一个不可能匹配的位置之后，数组也不能再有元素。
            limit, tail = index, False
            break
        option = {} if member is True else normalize(member, path + f'/{tuple_key}/{index}', changes)
        if option not in options:
            options.append(option)

    if tail is False:
        schema['maxItems'] = min(maximum, limit) if type(maximum) is int else limit
    elif type(maximum) is not int or maximum > limit:
        option = {} if tail is None or tail is True else normalize(tail, path + '/' + tail_key, changes)
        if option not in options:
            options.append(option)

    # 原生 items 只能使用一个 schema；联合保留所有元素类型，闭合元组用原上限限制长度。
    if not options or {} in options:
        schema['items'] = unrestricted
    else:
        schema['items'] = options[0] if len(options) == 1 else {'anyOf': options}
    changes.append({'path': path + '/' + tuple_key, 'action': 'tuple_as_array_items'})


def normalize(schema, path='', changes=None):
    """规范化类型及 AGY 不支持的工具约束。@param schema 参数 schema。@param path JSON 路径。@param changes 变更账本。@return 独立 schema。"""
    if changes is None:changes=[]
    if not isinstance(schema,dict):raise InputError('invalid_tool_schema:'+path)
    result=copy.deepcopy(schema)
    kind=result.get('type')
    if isinstance(kind,str) and kind.lower() in ['object','array','string','number','integer','boolean','null']:
        result['type']=kind.lower()
        if kind!=result['type']:changes.append({'path':path+'/type','action':'gemini_type_to_json_schema'})
    constant = result.get('const')
    if isinstance(constant, str):
        if 'enum' in result and (not isinstance(result['enum'], list) or constant not in result['enum']):
            raise InputError('invalid_tool_schema:' + path + '/const')
        result['enum'] = [result.pop('const')]
        result.setdefault('type', 'string')
        changes.append({'path': path + '/const', 'action': 'string_const_as_enum'})
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
    is_array = result.get('type') == 'array'
    for key in ['items','additionalProperties','contains','not','if','then','else','propertyNames']:
        if is_array and key == 'items':continue
        if isinstance(result.get(key),dict):result[key]=normalize(result[key],path+'/'+key,changes)
    for key in ['anyOf','oneOf','allOf','prefixItems']:
        if is_array and key == 'prefixItems':continue
        if isinstance(result.get(key),list):result[key]=[normalize(v,path+'/'+key+'/'+str(i),changes) for i,v in enumerate(result[key])]
    for key in ['$defs','definitions','patternProperties','dependentSchemas']:
        if isinstance(result.get(key),dict):result[key]={k:normalize(v,path+'/'+key+'/'+k,changes) for k,v in result[key].items()}
    if is_array:
        _normalize_array_items(result, path, changes)
    return result
