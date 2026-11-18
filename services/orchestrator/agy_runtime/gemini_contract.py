"""解析 Gemini 工具与调用方持有的历史，构造独立 Cortex 输入。"""
import base64
import copy
import json
from .contract import InputError, MODEL, text, tools
from .tool_schema import normalize

GEMINI_MODEL=None
BYPASS_SIGNATURE='context_engineering_is_the_way_to_go'
SAFETY_CATEGORIES={'HARM_CATEGORY_HARASSMENT','HARM_CATEGORY_HATE_SPEECH','HARM_CATEGORY_SEXUALLY_EXPLICIT','HARM_CATEGORY_DANGEROUS_CONTENT'}


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
    """分别承载原生字节签名与网关的显式绕过标记。@param value 签名文本。@param native 原生调用。@return 无。"""
    if value is None:return
    value=text(value)
    if value==BYPASS_SIGNATURE:native['thoughtSignature']=value;return
    try:
        if not base64.b64decode(value,validate=True):raise ValueError()
    except (ValueError,TypeError) as exc:raise InputError('invalid_gemini_thought_signature') from exc
    native['thinkingSignature']=value


def native_value(value):
    """构造已定义的原生 content.Value，保留结果对象的 JSON 类型。@param value JSON 值。@return 原生值。"""
    if value is None:return {'nullValue':'NULL_VALUE'}
    if isinstance(value,bool):return {'boolValue':value}
    if isinstance(value,str):return {'stringValue':value}
    if isinstance(value,(int,float)):return {'numberValue':value}
    if isinstance(value,list):return {'listValue':{'values':[native_value(v) for v in value]}}
    if isinstance(value,dict):return {'structValue':{'fields':[{'name':k,'value':native_value(v)} for k,v in value.items()]}}
    raise InputError('invalid_function_response_value')


def native_history(contents):
    """将多 Part 和完整函数结果映射为已定义的原生步骤。@param contents Gemini 内容。@return 原生步骤。"""
    if not isinstance(contents,list) or not contents:raise InputError('invalid_gemini_contents')
    steps=[];pending=[];used=set()
    for i,content in enumerate(contents):
        path='/body/contents/'+str(i);checked_fields(content,{'role','parts'},path)
        role=content.get('role','user');parts=content.get('parts')
        if role not in ['user','model'] or not isinstance(parts,list) or not parts:raise InputError('invalid_gemini_content:'+path)
        response=[];thinking=[];calls=[];thinking_signature=None
        for j,part in enumerate(parts):
            location=path+'/parts/'+str(j);checked_fields(part,{'text','thought','thoughtSignature','functionCall','functionResponse'},location)
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
                name=text(value.get('name'));result=value.get('response')
                if not isinstance(result,dict):raise InputError('invalid_function_response:'+location)
                matches=[call for call in pending if call['name']==name and ('id' not in value or call['id']==value['id'])]
                if len(matches)!=1:raise InputError('ambiguous_or_unknown_function_response:'+location)
                call=matches[0];pending.remove(call)
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
        elif response:
            if pending:raise InputError('missing_function_response:'+path)
            steps.append({'type':'CORTEX_STEP_TYPE_USER_INPUT','status':'CORTEX_STEP_STATUS_DONE','metadata':{},'userInput':{'userResponse':'\n'.join(response)}})
    if pending:raise InputError('missing_function_response')
    if contents[-1].get('role','user')!='user':raise InputError('unsupported_gemini_last_role')
    return steps


def decode_request(raw):
    """校验 Gemini 业务正文并给出原生执行参数。@param raw 控制信封。@return 内部请求。"""
    checked_fields(raw,{'schema_version','type','request_id','model','body'},'')
    if type(raw.get('schema_version')) is not int or raw['schema_version']!=1 or raw.get('type')!='gemini_request':raise InputError('invalid_schema')
    ident=text(raw.get('request_id'))
    if not ident or len(ident)>128:raise InputError('invalid_request_id')
    if raw.get('model')!=GEMINI_MODEL:raise InputError('unsupported_gemini_model')
    body=raw.get('body');checked_fields(body,{'contents','systemInstruction','generationConfig','tools','safetySettings','toolConfig'},'/body')
    changes=[];notices=[];declared=definitions(body,changes);steps=native_history(body.get('contents'));system=[]
    if 'systemInstruction' in body:
        value=body['systemInstruction'];checked_fields(value,{'role','parts'},'/body/systemInstruction')
        if value.get('role','user') not in ['user','system']:raise InputError('unsupported_system_role')
        if not isinstance(value.get('parts'),list) or not value['parts']:raise InputError('invalid_system_parts')
        for part in value['parts']:checked_fields(part,{'text'},'/body/systemInstruction/parts');system.append(text(part.get('text')))
    completion={}
    if 'generationConfig' in body:
        value=body['generationConfig'];checked_fields(value,{'maxOutputTokens','temperature','topP'},'/body/generationConfig')
        for name in ['temperature','topP']:
            if name in value:
                notices.append({'field':'generationConfig.'+name,'policy':'native_default'})
        if 'maxOutputTokens' in value:
            tokens=value['maxOutputTokens']
            if type(tokens) is not int or not 1<=tokens<=2147483647:raise InputError('invalid_gemini_max_output_tokens')
            completion['maxTokens']=tokens
    if 'safetySettings' in body:
        values=body['safetySettings']
        if not isinstance(values,list):raise InputError('invalid_gemini_safety_settings')
        categories=set()
        for value in values:
            checked_fields(value,{'category','threshold'},'/body/safetySettings')
            if value.get('category') in categories or value.get('category') not in SAFETY_CATEGORIES or value.get('threshold') not in ['OFF','BLOCK_NONE']:raise InputError('unsupported_gemini_safety_settings')
            categories.add(value['category'])
        if categories:
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
    return {'request_id':ident,'prompt':'','messages':[],'history_id':None,'system':'\n'.join(system),'model':MODEL,'tools':declared,'max_generations':1,
        'request_format':'gemini','gemini_body':copy.deepcopy(body),'native_completion':completion,'native_steps':steps,'schema_changes':changes,'compatibility_notes':notices}
def continuation_results(previous, calls, incoming):
    """把续轮结果绑定到本 worker 唯一待回填工具轮。@param previous 原始入站正文。@param calls 实际模型调用。@param incoming 新正文。@return 按函数名索引的真实结果。"""
    original=previous['contents'];contents=incoming['contents'];count=len(original)
    def stable(values):
        """保持原始历史、签名、文本和参数身份。@param values Content 列表。@return 独立对象。"""
        values=copy.deepcopy(values)
        return values
    if len(contents)!=count+2 or stable(contents[:count])!=stable(original):raise InputError('gemini_pending_history_mismatch')
    model,user=contents[count:]
    if model.get('role')!='model' or user.get('role','user')!='user':raise InputError('gemini_pending_turn_mismatch')
    expected=[{'name':c['name'],'args':c.get('args',{})} for c in calls]
    observed=[{'name':p['functionCall']['name'],'args':p['functionCall'].get('args',{})} for p in model['parts'] if 'functionCall' in p]
    if expected!=observed or len({c['name'] for c in expected})!=len(expected):raise InputError('gemini_pending_call_mismatch')
    for part, call in zip([p['functionCall'] for p in model['parts'] if 'functionCall' in p], calls):
        if 'id' in part and part['id'] != call.get('id'):raise InputError('gemini_pending_call_mismatch')
    values=[p['functionResponse'] for p in user['parts'] if 'functionResponse' in p]
    names=[v['name'] for v in values]
    if len(names)!=len(set(names)) or set(names)!={c['name'] for c in expected}:raise InputError('gemini_pending_results_mismatch')
    by_name = {call['name']:call for call in calls}
    for value in values:
        if 'id' in value and value['id'] != by_name[value['name']].get('id'):raise InputError('gemini_pending_results_mismatch')
    return {v['name']:copy.deepcopy(v['response']) for v in values}
