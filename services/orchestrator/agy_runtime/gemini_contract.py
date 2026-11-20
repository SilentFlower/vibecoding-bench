"""解析 Gemini 工具与调用方持有的历史，构造独立 Cortex 输入。"""
import copy
import json
import re
from collections import Counter
from .contract import InputError, MODEL, decode_gemini_bytes, text, tools
from .tool_schema import normalize
from .input_media import gif_budget, media_part
from .system_prompt import decode_policy, default_policy, transform_system

GEMINI_MODEL=None
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


def _matching_call(calls, value):
    name = value.get('name')
    if not isinstance(name, str) or not name:
        return None
    identifier = value.get('id')
    named = [call for call in calls if call['name'] == name]
    if 'id' in value and (not isinstance(identifier, str) or not identifier):
        return None
    if identifier is None and not named and any(call.get('id') == name for call in calls):
        identifier = name
    if identifier is not None:
        matches = [call for call in (named or calls) if call.get('id') == identifier]
    else:
        matches = named
    return matches[0] if len(matches) == 1 else None


def native_history(contents, tool_names=(), gif=None):
    """将多 Part 和完整函数结果映射为原生步骤。@param contents Gemini 内容。@param tool_names 已声明工具名称。@param gif 可选 GIF 转换预算。@return 原生步骤。"""
    if not isinstance(contents,list) or not contents:raise InputError('invalid_gemini_contents')
    contents = _legacy_tool_history(contents, tool_names)
    steps=[];pending=[];used=set()
    for i,content in enumerate(contents):
        path='/body/contents/'+str(i);checked_fields(content,{'role','parts'},path)
        role=content.get('role','user');parts=content.get('parts')
        if role not in ['user','model'] or not isinstance(parts,list) or not parts:raise InputError('invalid_gemini_content:'+path)
        response=[];thinking=[];calls=[];thinking_signature=None;media=[]
        for j,part in enumerate(parts):
            location=path+'/parts/'+str(j);checked_fields(part,{'text','thought','thoughtSignature','functionCall','functionResponse','inlineData','inline_data'},location)
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
                # 保留本轮完整名称集合，避免第二个结果借其他工具名认领剩余调用。
                call = _matching_call(planner['toolCalls'], value) if pending else None
                if call is None or call not in pending:raise InputError('ambiguous_or_unknown_function_response:'+location)
                pending.remove(call)
                # 结果使用原生 ResultValue，避免把 Gemini 对象再次包成 output 文本。
                args=json.loads(call['argumentsJson']);native_args={k:v if isinstance(v,str) else encode(v) for k,v in args.items()}
                steps.append({'type':'CORTEX_STEP_TYPE_GENERIC','status':'CORTEX_STEP_STATUS_DONE','metadata':{'toolCall':copy.deepcopy(call)},'generic':{'args':native_args,'result':{'resultValue':native_value(result)}}})
        if role=='model':
            if pending:raise InputError('missing_function_response:'+path)
            planner={'response':'\n'.join(response),'modifiedResponse':'\n'.join(response),'stopReason':'STOP_REASON_STOP_PATTERN'}
            if thinking:
                planner['thinking']='\n'.join(thinking)
                native={};call_signature(thinking_signature,native)
                if 'thinkingSignature' in native:planner['thinkingSignature']=native['thinkingSignature']
                elif 'thoughtSignature' in native:planner['signature']=native['thoughtSignature']
            if calls:planner['toolCalls']=calls;pending=copy.deepcopy(calls)
            steps.append({'type':'CORTEX_STEP_TYPE_PLANNER_RESPONSE','status':'CORTEX_STEP_STATUS_DONE','metadata':{'source':'CORTEX_STEP_SOURCE_MODEL','generatorModel':MODEL},'plannerResponse':planner})
        elif response or media:
            if pending:raise InputError('missing_function_response:'+path)
            user_input = {'userResponse':'\n'.join(response)}
            if media:user_input['media'] = media
            steps.append({'type':'CORTEX_STEP_TYPE_USER_INPUT','status':'CORTEX_STEP_STATUS_DONE','metadata':{},'userInput':user_input})
    if pending:raise InputError('missing_function_response')
    if contents[-1].get('role','user')!='user':raise InputError('unsupported_gemini_last_role')
    return steps


def decode_request(raw):
    """校验 Gemini 业务正文并给出原生执行参数。@param raw 控制信封。@return 内部请求。"""
    checked_fields(raw,{'schema_version','type','request_id','model','body','system_prompt_policy','gif_frames','disable_safety_filtering','full_egress'},'')
    if type(raw.get('schema_version')) is not int or raw['schema_version']!=1 or raw.get('type')!='gemini_request':raise InputError('invalid_schema')
    ident=text(raw.get('request_id'))
    if not ident or len(ident)>128:raise InputError('invalid_request_id')
    if raw.get('model')!=GEMINI_MODEL:raise InputError('unsupported_gemini_model')
    body=raw.get('body');checked_fields(body,{'contents','systemInstruction','generationConfig','tools','safetySettings','toolConfig'},'/body')
    enabled=raw.get('gif_frames',False)
    if type(enabled) is not bool:raise InputError('invalid_media_policy')
    native_safety=raw.get('disable_safety_filtering',False)
    if type(native_safety) is not bool:raise InputError('invalid_safety_policy')
    full_egress=raw.get('full_egress',False)
    if type(full_egress) is not bool:raise InputError('invalid_capture_policy')
    changes=[];notices=[];declared=definitions(body,changes)
    steps=native_history(body.get('contents'), (tool['name'] for tool in declared), gif_budget(body,enabled));system=[]
    if 'systemInstruction' in body:
        value=body['systemInstruction'];checked_fields(value,{'role','parts'},'/body/systemInstruction')
        if value.get('role','user') not in ['user','system']:raise InputError('unsupported_system_role')
        if not isinstance(value.get('parts'),list) or not value['parts']:raise InputError('invalid_system_parts')
        for part in value['parts']:checked_fields(part,{'text'},'/body/systemInstruction/parts');system.append(text(part.get('text')))
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
        notices.append({'field':'parallel_tool_calls','policy':'native_disable_requested;duplicate_names_rejected','reason':'new-api removes function IDs'})
    policy=decode_policy(raw.get('system_prompt_policy',default_policy()))
    submitted,report=transform_system('\n'.join(system),policy)
    return {'request_id':ident,'prompt':'','messages':[],'history_id':None,'system':submitted,'system_prompt_policy':report,'model':MODEL,'tools':declared,'max_generations':1,
        'request_format':'gemini','gemini_body':copy.deepcopy(body),'native_completion':completion,'native_steps':steps,'schema_changes':changes,'compatibility_notes':notices,
        'safety_egress_rules':safety_egress_rules,'full_egress':full_egress}
def continuation_results(previous, calls, incoming):
    """把续轮结果绑定到本 worker 唯一待回填工具轮。@param previous 原始入站正文。@param calls 实际模型调用。@param incoming 新正文。@return 按函数名索引的真实结果。"""
    original=previous['contents'];contents=incoming['contents'];count=len(original)
    if len(contents)!=count+2 or contents[:count]!=original:raise InputError('gemini_pending_history_mismatch')
    model,user=contents[count:]
    if model.get('role')!='model' or user.get('role','user')!='user':raise InputError('gemini_pending_turn_mismatch')
    expected=[{'name':c['name'],'args':c.get('args',{})} for c in calls]
    observed=[{'name':p['functionCall']['name'],'args':p['functionCall'].get('args',{})} for p in model['parts'] if 'functionCall' in p]
    if expected!=observed or len({c['name'] for c in expected})!=len(expected):raise InputError('gemini_pending_call_mismatch')
    for part, call in zip([p['functionCall'] for p in model['parts'] if 'functionCall' in p], calls):
        if 'id' in part and part['id'] != call.get('id'):raise InputError('gemini_pending_call_mismatch')
    # 拒绝坏图后才能领取原工具轮，避免输入修正时发现结果已被消费。
    for index, part in enumerate(user['parts']):
        if isinstance(part, dict):
            media_part(part, f'/body/contents/{count + 1}/parts/{index}', 'user')
    values=[p['functionResponse'] for p in user['parts'] if 'functionResponse' in p]
    results = {}
    for value in values:
        call = _matching_call(calls, value)
        if call is None or call['name'] in results or not isinstance(value.get('response'), dict):
            raise InputError('gemini_pending_results_mismatch')
        results[call['name']] = copy.deepcopy(value['response'])
    if len(results)!=len(calls):raise InputError('gemini_pending_results_mismatch')
    return results
