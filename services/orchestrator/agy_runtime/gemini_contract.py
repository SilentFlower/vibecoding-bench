"""解析 Gemini 工具与调用方持有的历史，构造独立 Cortex 输入。"""
import copy
import json
import math
import re
from collections import Counter
from .contract import InputError, decode_gemini_bytes, text, tools
from .tool_schema import normalize
from .input_media import gif_budget, media_part
from .models import valid_model_mapping
from .system_prompt import default_policy, prepare_system

BYPASS_SIGNATURE='context_engineering_is_the_way_to_go'
SAFETY_CATEGORIES={'HARM_CATEGORY_HARASSMENT','HARM_CATEGORY_HATE_SPEECH','HARM_CATEGORY_SEXUALLY_EXPLICIT','HARM_CATEGORY_DANGEROUS_CONTENT'}
LEGACY_TOOL_ID = re.compile(r'call_[0-9]+')
LEGACY_SHORT_ID = re.compile(r'[0-9A-Za-z]{8}')
LEGACY_UUID_ID = re.compile(r'call_[0-9a-f]{32}')


def checked_fields(value, allowed, path):
    """核对当前支持的 JSON 字段。@param value 对象。@param allowed 字段集合。@param path 路径。@return 无。"""
    if not isinstance(value,dict):raise InputError('invalid_gemini_object:'+path)
    unknown=sorted(set(value)-set(allowed))
    if unknown:raise InputError('unsupported_gemini_field:'+path+'/'+unknown[0])


def encode(value):
    """生成稳定的参数 JSON。@param value 对象。@return JSON 文本。"""
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def definitions(body, changes):
    """读取普通函数声明。@param body Gemini 请求。@param changes schema 账本。@return 工具定义。"""
    result=[];groups=body.get('tools',[])
    if not isinstance(groups,list):raise InputError('invalid_gemini_tools')
    for i,group in enumerate(groups):
        path='/body/tools/'+str(i);checked_fields(group,{'functionDeclarations'},path)
        values=group.get('functionDeclarations',[])
        if not isinstance(values,list):raise InputError('invalid_function_declarations:'+path)
        for j,value in enumerate(values):
            location=path+'/functionDeclarations/'+str(j)
            checked_fields(value,{'name','description','parameters','parametersJsonSchema'},location)
            if 'parameters' in value and 'parametersJsonSchema' in value:raise InputError('conflicting_function_schema:'+location)
            schema=value.get('parametersJsonSchema',value.get('parameters',{'type':'object','properties':{}}))
            if schema=={}:
                schema={'type':'object','properties':{}}
                changes.append({'path':location+'/parameters','action':'empty_function_parameters_as_object'})
            if (value.get('name')=='web_search' and isinstance(schema,dict)
                    and set(schema)<={'type','properties','additionalProperties','description'}
                    and str(schema.get('type','object')).lower()=='object'
                    and schema.get('properties',{})=={} and schema.get('additionalProperties',True) is True):
                # AGY 在 MCP 调用前拒绝未声明的 query。仅补全可接纳任意属性的旧版声明。
                schema={**schema,'type':'object','properties':{'query':{'type':'string'}}}
                changes.append({'path':location+'/parameters/properties/query','action':'legacy_web_search_query'})
            result.append({'name':value.get('name'),'description':value.get('description',''),'input_schema':normalize(schema,location+'/parameters',changes)})
    return tools(result)


def call_signature(value, native):
    """保留签名字节并统一原生序列化格式。@param value 签名文本。@param native 原生调用。@return 无。"""
    if value is None:return
    value=text(value)
    if value==BYPASS_SIGNATURE:native['thoughtSignature']=value;return
    try:
        _, encoded = decode_gemini_bytes(value)
    except (ValueError,TypeError) as exc:raise InputError('invalid_gemini_thought_signature') from exc
    native['thinkingSignature']=encoded


def native_value(value):
    """构造已定义的原生 content.Value，保留结果对象的 JSON 类型。@param value JSON 值。@return 原生值。"""
    if value is None:return {'nullValue':'NULL_VALUE'}
    if isinstance(value,bool):return {'boolValue':value}
    if isinstance(value,str):return {'stringValue':value}
    if isinstance(value,(int,float)):return {'numberValue':value}
    if isinstance(value,list):return {'listValue':{'values':[native_value(v) for v in value]}}
    if isinstance(value,dict):return {'structValue':{'fields':[{'name':k,'value':native_value(v)} for k,v in value.items()]}}
    raise InputError('invalid_function_response_value')


def _turn_parts(content, field):
    if isinstance(content, dict) and isinstance(content.get('parts'), list):
        return [(index, part[field]) for index, part in enumerate(content['parts'])
                if isinstance(part, dict) and isinstance(part.get(field), dict)]
    return []


def _legacy_tool_history(contents, tool_names):
    calls = [_turn_parts(content, 'functionCall') for content in contents]
    results = [_turn_parts(content, 'functionResponse') for content in contents]
    names = set(tool_names)
    names.update(call['name'] for group in calls for _, call in group if isinstance(call.get('name'), str))
    ids = {part['id'] for groups in (calls, results) for group in groups for _, part in group
           if isinstance(part.get('id'), str)}
    aliases = Counter(result['name'] for group in results for _, result in group if isinstance(result.get('name'), str))
    normalized = list(contents)
    legacy_history = False
    for index in range(len(contents) - 1):
        if len(calls[index]) != 1 or len(results[index + 1]) != 1:
            continue
        left, right = contents[index:index + 2]
        if left.get('role') != 'model' or right.get('role', 'user') != 'user':
            continue
        call_index, call = calls[index][0]
        result_index, result = results[index + 1][0]
        alias = result.get('name')
        if ('id' in call or 'id' in result or not isinstance(alias, str)
                or alias in names or alias in ids or aliases[alias] != 1):
            continue
        short = LEGACY_SHORT_ID.fullmatch(alias)
        anchored = (LEGACY_TOOL_ID.fullmatch(alias) or LEGACY_UUID_ID.fullmatch(alias)
                    or short and any(character.isdigit() for character in alias))
        # 纯字母短码也可能是真实函数名，只有此前已识别出同一请求的旧式回填才恢复。
        if not anchored and not (short and legacy_history):
            continue
        legacy_history |= bool(anchored)
        # 只有观测到的一对一旧格式能恢复；公开入站和活跃工具轮的原始身份继续保留。
        for offset, part_index, field, value in (
            (index, call_index, 'functionCall', {**call, 'id': alias}),
            (index + 1, result_index, 'functionResponse', {**result, 'id': alias, 'name': call.get('name')}),
        ):
            parts = list(contents[offset]['parts'])
            parts[part_index] = {**parts[part_index], field: value}
            normalized[offset] = {**contents[offset], 'parts': parts}
    return normalized


def _ordered_tool_results(calls, values):
    """按原调用顺序配对一轮结果。@param calls 实际调用。@param values 客户端结果。@return 排好序的结果或空。"""
    if len(values) != len(calls):
        return None
    results = [None] * len(calls)
    deferred = []
    # 先保留可由 ID 核对的位置，再处理可能早于它到达的无 ID 结果。
    for value in values:
        if not isinstance(value, dict):
            return None
        name, result = value.get('name'), value.get('response')
        if not isinstance(name, str) or not name or not isinstance(result, dict):
            return None
        has_name = any(call['name'] == name for call in calls)
        if 'id' in value:
            identifier = value['id']
            if not isinstance(identifier, str) or not identifier:
                return None
        elif has_name:
            deferred.append((name, result))
            continue
        else:
            identifier = name
        matches = [index for index, call in enumerate(calls)
            if (not has_name or call['name'] == name) and call.get('id') == identifier]
        if len(matches) != 1 or results[matches[0]] is not None:
            return None
        results[matches[0]] = result
    # 不同工具的完成次序可变化，同名组内用原顺序补齐尚未认领的位置。
    for name, result in deferred:
        index = next((index for index, call in enumerate(calls)
            if results[index] is None and call['name'] == name), None)
        if index is None:
            return None
        results[index] = result
    return results


def native_history(contents, tool_names=(), gif=None, *, native_model):
    """映射多 Part 和完整函数结果。@param contents Gemini 内容。@param tool_names 工具名。@param gif GIF 预算。@param native_model 本轮执行ID。@return 原生步骤。"""
    if not isinstance(contents,list) or not contents:raise InputError('invalid_gemini_contents')
    contents = _legacy_tool_history(contents, tool_names)
    steps=[];pending=[];used=set();tool_results=[]
    for i,content in enumerate(contents):
        path='/body/contents/'+str(i);checked_fields(content,{'role','parts'},path)
        role=content.get('role','user');parts=content.get('parts')
        if role not in ['user','model'] or not isinstance(parts,list) or not parts:raise InputError('invalid_gemini_content:'+path)
        response=[];thinking=[];calls=[];thinking_signature=None;media=[]
        for j,part in enumerate(parts):
            location=path+'/parts/'+str(j);checked_fields(part,{'text','thought','thoughtSignature','functionCall','functionResponse','inlineData','inline_data'},location)
            if (not part and role == 'model' and j == 0 and len(parts) == 2
                    and isinstance(parts[1], dict) and 'functionCall' in parts[1]):
                # 保留 Part 原位，避免合成调用 ID 和校验错误路径中的索引左移。
                continue
            image = media_part(part, location, role, gif)
            if image is not None:
                media.extend(image)
                continue
            if type(part.get('thought',False)) is not bool:raise InputError('invalid_gemini_thought:'+location)
            kinds=set(part)&{'text','functionCall','functionResponse'}
            if len(kinds)!=1:raise InputError('invalid_gemini_part:'+location)
            if 'text' in part:
                value=text(part['text'])
                if role=='user' and part.get('thought'):raise InputError('invalid_user_thought:'+location)
                (thinking if part.get('thought') else response).append(value)
                if part.get('thought') and 'thoughtSignature' in part:thinking_signature=part['thoughtSignature']
            elif 'functionCall' in part:
                if role!='model' or pending:raise InputError('invalid_gemini_function_call_order:'+location)
                call=part['functionCall'];checked_fields(call,{'name','args','id'},location+'/functionCall')
                name=text(call.get('name'));args=call.get('args',{})
                ident=text(call.get('id','gemini-history-'+str(i)+'-'+str(j)))
                if not name or not ident or ident in used or not isinstance(args,dict):raise InputError('invalid_gemini_function_call:'+location)
                used.add(ident);native={'id':ident,'name':name,'argumentsJson':encode(args)};call_signature(part.get('thoughtSignature'),native);calls.append(native)
            else:
                if role!='user' or response:raise InputError('invalid_gemini_function_response_order:'+location)
                value=part['functionResponse'];checked_fields(value,{'name','response','id'},location+'/functionResponse')
                text(value.get('name'));result=value.get('response')
                if not isinstance(result,dict):raise InputError('invalid_function_response:'+location)
                if not pending or len(tool_results) == len(pending):
                    raise InputError('ambiguous_or_unknown_function_response:'+location)
                tool_results.append(value)
        if pending and len(tool_results) == len(pending):
            # 一个历史工具轮可跨多条用户内容，收齐才能保留较晚出现的显式 ID。
            ordered = _ordered_tool_results(pending, tool_results)
            if ordered is None:
                raise InputError('ambiguous_or_unknown_function_response:'+path)
            for call, result in zip(pending, ordered):
                # 结果使用原生 ResultValue，避免把 Gemini 对象再次包成 output 文本。
                args = json.loads(call['argumentsJson'])
                native_args = {key: value if isinstance(value, str) else encode(value) for key, value in args.items()}
                steps.append({'type': 'CORTEX_STEP_TYPE_GENERIC', 'status': 'CORTEX_STEP_STATUS_DONE',
                    'metadata': {'toolCall': copy.deepcopy(call)},
                    'generic': {'args': native_args, 'result': {'resultValue': native_value(result)}}})
            pending = []
            tool_results.clear()
        if role=='model':
            if pending:raise InputError('missing_function_response:'+path)
            planner={'response':'\n'.join(response),'modifiedResponse':'\n'.join(response),'stopReason':'STOP_REASON_STOP_PATTERN'}
            if thinking:
                planner['thinking']='\n'.join(thinking)
                native={};call_signature(thinking_signature,native)
                if 'thinkingSignature' in native:planner['thinkingSignature']=native['thinkingSignature']
                elif 'thoughtSignature' in native:planner['signature']=native['thoughtSignature']
            if calls:
                planner['toolCalls'] = calls
                pending = calls
            steps.append({'type':'CORTEX_STEP_TYPE_PLANNER_RESPONSE','status':'CORTEX_STEP_STATUS_DONE','metadata':{'source':'CORTEX_STEP_SOURCE_MODEL','generatorModel':native_model},'plannerResponse':planner})
        elif response or media:
            if pending:raise InputError('missing_function_response:'+path)
            user_input = {'userResponse':'\n'.join(response)}
            if media:user_input['media'] = media
            steps.append({'type':'CORTEX_STEP_TYPE_USER_INPUT','status':'CORTEX_STEP_STATUS_DONE','metadata':{},'userInput':user_input})
    if pending:raise InputError('missing_function_response')
    if contents[-1].get('role','user')!='user':raise InputError('unsupported_gemini_last_role')
    return steps


def decode_request(raw, *, fixed_model: tuple[str, str | int] | None = None):
    """校验 Gemini 业务输入。@param raw 私有信封。@param fixed_model 独立内核的固定映射。@return 本轮原生执行参数。"""
    checked_fields(raw,{'schema_version','type','request_id','model','native_model','body','system_prompt_policy','gif_frames','disable_safety_filtering','full_egress','execution_deadline'},'')
    if type(raw.get('schema_version')) is not int or raw['schema_version']!=1 or raw.get('type')!='gemini_request':raise InputError('invalid_schema')
    ident=text(raw.get('request_id'))
    if not ident or len(ident)>128:raise InputError('invalid_request_id')
    execution_deadline=raw.get('execution_deadline')
    if execution_deadline is not None and (type(execution_deadline) not in (float,int) or not math.isfinite(execution_deadline)
            or execution_deadline<=0):raise InputError('invalid_request_deadline')
    if fixed_model is None:
        native_model = raw.get('native_model')
        if not valid_model_mapping(raw.get('model'), native_model):
            raise InputError('invalid_model_mapping')
    else:
        public_model, native_model = fixed_model
        if raw.get('model') != public_model or 'native_model' in raw:
            raise InputError('unsupported_gemini_model')
    body=raw.get('body');checked_fields(body,{'contents','systemInstruction','generationConfig','tools','safetySettings','toolConfig'},'/body')
    enabled=raw.get('gif_frames',False)
    if type(enabled) is not bool:raise InputError('invalid_media_policy')
    native_safety=raw.get('disable_safety_filtering',False)
    if type(native_safety) is not bool:raise InputError('invalid_safety_policy')
    full_egress=raw.get('full_egress',False)
    if type(full_egress) is not bool:raise InputError('invalid_capture_policy')
    changes=[];notices=[];declared=definitions(body,changes)
    system=[]
    if 'systemInstruction' in body:
        value=body['systemInstruction'];checked_fields(value,{'role','parts'},'/body/systemInstruction')
        if value.get('role','user') not in ['user','system']:raise InputError('unsupported_system_role')
        if not isinstance(value.get('parts'),list) or not value['parts']:raise InputError('invalid_system_parts')
        for part in value['parts']:checked_fields(part,{'text'},'/body/systemInstruction/parts');system.append(text(part.get('text')))
    policy = raw.get('system_prompt_policy', default_policy())
    submitted, contents, report = prepare_system('\n'.join(system), body.get('contents'), policy)
    steps = native_history(
        contents, (tool['name'] for tool in declared), gif_budget(body, enabled), native_model=native_model,
    )
    completion={}
    if 'generationConfig' in body:
        value=body['generationConfig'];checked_fields(value,{'maxOutputTokens','temperature','topP','responseModalities'},'/body/generationConfig')
        if value.get('responseModalities',[]) not in ([],['TEXT']):
            raise InputError('unsupported_gemini_output_modality:/body/generationConfig/responseModalities')
        for name in ['temperature','topP']:
            if name in value:
                notices.append({'field':'generationConfig.'+name,'policy':'native_default'})
        if 'maxOutputTokens' in value:
            tokens=value['maxOutputTokens']
            if type(tokens) is not int or not 1<=tokens<=2147483647:raise InputError('invalid_gemini_max_output_tokens')
            completion['maxTokens']=tokens
    safety_egress_rules=[]
    if native_safety:
        completion['disableSafetyFiltering']=True
        notices.append({'field':'safetySettings','policy':'account_native_safety','native_field':'disableSafetyFiltering'})
    if 'safetySettings' in body:
        values=body['safetySettings']
        if not isinstance(values,list):raise InputError('invalid_gemini_safety_settings')
        categories=set();thresholds=set()
        for value in values:
            checked_fields(value,{'category','threshold'},'/body/safetySettings')
            category,threshold=value.get('category'),value.get('threshold')
            if not isinstance(category,str) or category not in SAFETY_CATEGORIES or category in categories or threshold not in (
                    'OFF','BLOCK_NONE','BLOCK_LOW_AND_ABOVE','BLOCK_MEDIUM_AND_ABOVE','BLOCK_ONLY_HIGH','HARM_BLOCK_THRESHOLD_UNSPECIFIED'):
                raise InputError('unsupported_gemini_safety_settings')
            categories.add(category);thresholds.add(threshold)
        if not native_safety and thresholds-{'OFF','BLOCK_NONE'}:
            # 原生布尔开关表达不了逐类阈值，保留全部规则到同次原生请求的出站边界。
            safety_egress_rules=copy.deepcopy(values)
            notices.append({'field':'safetySettings','policy':'native_safety_egress','requested_categories':sorted(categories)})
        elif not native_safety and categories:
            if categories!=SAFETY_CATEGORIES:raise InputError('unsupported_partial_safety_settings')
            completion['disableSafetyFiltering']=True
            notices.append({'field':'safetySettings','policy':'native_completion_mapping','native_field':'disableSafetyFiltering','native_wire_categories':['HARM_CATEGORY_DANGEROUS_CONTENT'],'requested_categories':sorted(categories)})
    if 'toolConfig' in body:
        cfg=body['toolConfig'];checked_fields(cfg,{'functionCallingConfig'},'/body/toolConfig')
        fn=cfg.get('functionCallingConfig',{});checked_fields(fn,{'mode'},'/body/toolConfig/functionCallingConfig')
        if fn.get('mode','AUTO')=='NONE':declared=[]
        elif fn.get('mode','AUTO')!='AUTO':raise InputError('unsupported_gemini_tool_mode')
    if declared:
        # 现有 new-api 会丢弃历史函数 ID；请求单工具生成可避免同名并发结果错配。
        completion['disableParallelToolCalls']=True
        notices.append({'field':'parallel_tool_calls','policy':'native_disable_requested;ordered_same_name_results','reason':'new-api removes function IDs'})
    return {'request_id':ident,'prompt':'','messages':[],'history_id':None,'system':submitted,'system_prompt_policy':report,'model':native_model,'tools':declared,'max_generations':1,
        'request_format':'gemini','gemini_body':copy.deepcopy(body),'native_completion':completion,'native_steps':steps,'schema_changes':changes,'compatibility_notes':notices,
        'safety_egress_rules':safety_egress_rules,'full_egress':full_egress,'execution_deadline':execution_deadline}
def continuation_results(previous, calls, incoming):
    """把续轮结果绑定到本 worker 唯一待回填工具轮。@param previous 原始入站正文。@param calls 实际模型调用。@param incoming 新正文。@return 按原调用顺序排列的真实结果。"""
    original=previous['contents'];contents=incoming['contents'];count=len(original)
    if len(contents)<count+2 or contents[:count]!=original:raise InputError('gemini_pending_history_mismatch')
    model,*users=contents[count:]
    if model.get('role')!='model' or any(user.get('role','user')!='user' for user in users):
        raise InputError('gemini_pending_turn_mismatch')
    expected=[{'name':c['name'],'args':c.get('args',{})} for c in calls]
    observed=[{'name':p['functionCall']['name'],'args':p['functionCall'].get('args',{})} for p in model['parts'] if 'functionCall' in p]
    if expected!=observed:raise InputError('gemini_pending_call_mismatch')
    for part, call in zip([p['functionCall'] for p in model['parts'] if 'functionCall' in p], calls):
        if 'id' in part and part['id'] != call.get('id'):raise InputError('gemini_pending_call_mismatch')
    # 拒绝坏图后才能领取原工具轮，避免输入修正时发现结果已被消费。
    values=[];seen_text=False
    for user_index,user in enumerate(users,count+1):
        for index, part in enumerate(user['parts']):
            if not isinstance(part,dict):raise InputError('gemini_pending_turn_mismatch')
            media_part(part, f'/body/contents/{user_index}/parts/{index}', 'user')
            if 'functionResponse' in part:
                if seen_text:raise InputError('gemini_pending_results_mismatch')
                values.append(part['functionResponse'])
            seen_text |= 'text' in part
    ordered = _ordered_tool_results(calls, values)
    if ordered is None:
        raise InputError('gemini_pending_results_mismatch')
    return copy.deepcopy(ordered)
