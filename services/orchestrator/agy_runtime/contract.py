"""版本化私有协议及受限消息历史实体。"""
import base64
import copy
import json
import re
import uuid

CAPABILITIES = {
    'protocol': 'agy-native-stdio', 'schema_version': 1, 'model': None,
    'request': 'gemini_request', 'max_generations': 1,
    'cancel_identity': ['request_id', 'request_seq', 'generation'],
    'gemini_json_protocol': 1,
    'gemini': {'model': None, 'input': ['contents.text_parts', 'contents.functionCall',
        'contents.functionResponse', 'systemInstruction.text_parts', 'generationConfig.maxOutputTokens',
        'tools.functionDeclarations'], 'compatibility_parameters': {'temperature': 'native_default', 'topP': 'native_default'},
        'response': 'single_part_gemini_json', 'raw_json_response': False,
        'caller_owned_history': True, 'tool_results_require_same_worker': True}
}


class InputError(ValueError):
    """表示模型发送前发现的输入合同错误。"""


def fields(value, allowed):
    """核对对象字段。@param value 输入对象。@param allowed 字段集合。@return 无返回值。"""
    if not isinstance(value,dict) or set(value)-set(allowed):raise InputError('unsupported_fields')


def text(value):
    """读取已声明文本。@param value 输入值。@return 文本。"""
    if not isinstance(value,str):raise InputError('invalid_text')
    return value


def decode_gemini_bytes(value: str) -> tuple[bytes, str]:
    """解码 Gemini 字节字段。@param value Base64 或 Base64URL 文本。@return 原字节及标准 Base64 表示。"""
    if not isinstance(value, str) or not value:
        raise ValueError('Gemini 字节字段需要非空 Base64')
    try:
        return base64.b64decode(value, validate=True), value
    except ValueError:
        # 两种字母表分别校验，避免把混用字符或损坏的填充误当成兼容数据。
        if not re.fullmatch(r'(?:[A-Za-z0-9+/]+|[A-Za-z0-9_-]+)={0,2}', value):
            raise
        padded = value if value.endswith('=') else value + '=' * (-len(value) % 4)
        raw = base64.b64decode(padded, altchars=b'-_', validate=True)
        return raw, base64.b64encode(raw).decode('ascii')


def signature(value):
    """检查签名字节的可逆表示。@param value Base64文本。@return 原文本。"""
    text(value)
    try:raw=base64.b64decode(value,validate=True)
    except Exception as exc:raise InputError('invalid_signature') from exc
    if not raw:raise InputError('missing_signature')
    return value


def history_steps(messages, *, native_model):
    """把受限历史映射为原生步骤。@param messages 历史消息。@param native_model 本轮执行ID。@return 原生步骤。"""
    if not isinstance(messages,list):raise InputError('invalid_history')
    steps=[];pending={};finished=set()
    for msg in messages:
        if not isinstance(msg,dict):raise InputError('invalid_history_message')
        role=msg.get('role');step={'status':'CORTEX_STEP_STATUS_DONE'}
        if role=='user':
            fields(msg,{'role','text'})
            if set(pending)!=finished:raise InputError('missing_tool_result')
            step.update(type='CORTEX_STEP_TYPE_USER_INPUT',metadata={},userInput={'userResponse':text(msg.get('text'))})
        elif role=='assistant':
            fields(msg,{'role','text','thinking','thinking_signature','tool_calls'})
            if set(pending)!=finished:raise InputError('missing_tool_result')
            calls=msg.get('tool_calls',[])
            if not isinstance(calls,list):raise InputError('invalid_tool_calls')
            response=text(msg.get('text',''));thinking=text(msg.get('thinking',''))
            if calls and (response or thinking):raise InputError('mixed_thinking_tools_unsupported')
            planner={'stopReason':'STOP_REASON_STOP_PATTERN'}
            if calls:
                encoded=[]
                for call in calls:
                    fields(call,{'id','name','arguments','thinking_signature'})
                    ident=text(call.get('id'));name=text(call.get('name'));args=call.get('arguments')
                    if not ident or not name or ident in pending or not isinstance(args,dict):raise InputError('invalid_tool_identity')
                    native={'id':ident,'name':name,'argumentsJson':json.dumps(args,ensure_ascii=False,separators=(',',':')),'thinkingSignature':signature(call.get('thinking_signature'))}
                    pending[ident]=native;encoded.append(native)
                planner['toolCalls']=encoded
            else:
                planner.update(response=response,modifiedResponse=response)
                if thinking:planner.update(thinking=thinking,thinkingSignature=signature(msg.get('thinking_signature')))
                elif 'thinking_signature' in msg:raise InputError('signature_without_thinking')
            step.update(type='CORTEX_STEP_TYPE_PLANNER_RESPONSE',metadata={'source':'CORTEX_STEP_SOURCE_MODEL','generatorModel':native_model},plannerResponse=planner)
        elif role=='tool':
            fields(msg,{'role','tool_call_id','text'});ident=text(msg.get('tool_call_id'))
            if ident not in pending or ident in finished:raise InputError('unknown_tool_result')
            call=pending[ident];finished.add(ident)
            step.update(type='CORTEX_STEP_TYPE_GENERIC',metadata={'toolCall':copy.deepcopy(call)},
                generic={'args':json.loads(call['argumentsJson']),'result':{'result':text(msg.get('text'))}})
        else:raise InputError('unsupported_history_role')
        steps.append(step)
    if set(pending)!=finished:raise InputError('missing_tool_result')
    return steps


def request(value, *, fixed_model: tuple[str, str | int] | None = None):
    """校验私有请求实体。@param value 原始JSON对象。@param fixed_model 独立内核的固定映射。@return 规范化对象。"""
    if isinstance(value,dict) and value.get('type')=='gemini_request':
        from .gemini_contract import decode_request
        return decode_request(value, fixed_model=fixed_model)
    fields(value,{'schema_version','type','request_id','prompt','history','history_id','model','system','tools','max_generations'})
    if type(value.get('schema_version')) is not int or value.get('schema_version')!=1 or value.get('type')!='request':raise InputError('invalid_schema')
    ident=text(value.get('request_id'))
    if not ident or len(ident)>128:raise InputError('invalid_request_id')
    prompt=text(value.get('prompt'))
    if fixed_model is None:raise InputError('unsupported_model')
    native_model = fixed_model[1]
    if value.get('model',native_model)!=native_model:raise InputError('unsupported_model')
    if 'history' in value and 'history_id' in value:raise InputError('conflicting_history')
    messages=value.get('history',[]);history_steps(messages,native_model=native_model)
    history_id=value.get('history_id')
    if history_id is not None:
        try:
            if str(uuid.UUID(history_id))!=history_id:raise ValueError()
        except Exception as exc:raise InputError('invalid_history_id') from exc
    if 'system' in value:text(value['system'])
    changes=[];definitions=tools(value.get('tools',[]),changes)
    generations=value.get('max_generations',2 if definitions else 1)
    if type(generations) is not int or not 1<=generations<=32:raise InputError('invalid_max_generations')
    return {'schema_changes':changes,'tools':definitions,'max_generations':generations,'request_id':ident,'prompt':prompt,'messages':copy.deepcopy(messages),'history_id':history_id,
        'system':value.get('system'),'model':native_model}


def tools(value, changes=None):
    """校验工具实体并记录等价 schema 改写。@param value 定义数组。@param changes 改写账本。@return 独立工具列表。"""
    if not isinstance(value,list):raise InputError('invalid_tools')
    seen=set()
    for item in value:
        fields(item,{'name','description','input_schema'})
        name=text(item.get('name'));text(item.get('description',''));schema=item.get('input_schema')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',name) or name in seen:raise InputError('invalid_tool_name')
        seen.add(name)
        if not isinstance(schema,dict) or schema.get('type')!='object' or not isinstance(schema.get('properties',{}),dict):raise InputError('unsupported_tool_schema')
        if 'toolSummary' in schema.get('properties',{}):raise InputError('reserved_tool_summary')
    from .tool_schema import normalize
    result=copy.deepcopy(value)
    for i,item in enumerate(result):item['input_schema']=normalize(item['input_schema'],'/tools/'+str(i)+'/input_schema',changes)
    return result
