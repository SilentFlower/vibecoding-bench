"""将原生 Gemini 源帧投影为现有 new-api 可消费的单 Part 流。"""
import base64
import copy
import json
from uuid import uuid4


RESULT_FINISH_REASONS = ('STOP', 'MAX_TOKENS')


def _token_count(value):
    return type(value) is int and 0 <= value < 2**64


class Frames:
    """保存本请求的输出归属和函数调用摘要。"""

    def __init__(self):
        """创建独立帧状态。@return 无。"""
        self.calls=[];self.sequence=0;self.terminal=False;self.finish_reason=None
        self.call_ids=set()
        self.source_error=False;self.usage_complete=False;self.visible_text=False
        self.max_tokens_usage_complete = False
        self.thought_or_media = False

    def recovery_blocker(self):
        """报告源帧阻止保留结果的首个条件。@return 受控代码，完整普通结果返回空。"""
        if self.source_error:return 'source_error'
        if self.calls:return 'tool_pending'
        if self.finish_reason not in RESULT_FINISH_REASONS:return 'missing_stop'
        truncated = self.finish_reason == 'MAX_TOKENS'
        if not (self.visible_text or truncated and self.thought_or_media):return 'missing_text'
        if not (self.max_tokens_usage_complete if truncated else self.usage_complete):return 'missing_usage'
        return None

    def project(self, event):
        """拆分候选 Part，保留终态和用量。@param event 原生源事件。@return 兼容事件数组。"""
        raw=base64.b64decode(event['data_base64'],validate=True)
        if event.get('source')=='codeassist_scanner_block':
            # OAuth的Scanner逻辑块包含SSE前缀及response信封，原始块仍由桥接归档保存。
            data=b'\n'.join(line[5:].lstrip(b' ') for line in raw.splitlines() if line.startswith(b'data:'))
            if not data:return []
            envelope=json.loads(data)
            body=envelope.get('response',envelope if 'error' in envelope else None)
            if not isinstance(body,dict):raise RuntimeError('invalid_native_gemini_envelope')
            event=copy.deepcopy(event)
            normalized=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
            event.update(data_base64=base64.b64encode(normalized).decode(),bytes=len(normalized),source_format='gemini_json')
        else:
            body=json.loads(raw)
        self.source_error |= 'error' in body
        usage=body.get('usageMetadata')
        if isinstance(usage,dict):
            base_usage = all(_token_count(usage.get(key)) for key in ('promptTokenCount', 'totalTokenCount'))
            self.usage_complete = base_usage and _token_count(usage.get('candidatesTokenCount'))
            thoughts = usage.get('thoughtsTokenCount')
            # 达到上限时，原生可能只报告已发生的思考用量。保留字段实际缺省，兼容性只用于恢复判断。
            thinking_usage = base_usage and 'candidatesTokenCount' not in usage and _token_count(thoughts) and thoughts > 0
            self.max_tokens_usage_complete = (self.usage_complete or thinking_usage) and (
                'thoughtsTokenCount' not in usage or _token_count(thoughts))
        candidates=body.get('candidates',[])
        # 官方控制RPC和通道EOF都可能在截断后正常返回，业务成功还须有源终态。
        feedback=body.get('promptFeedback',{})
        block=feedback.get('blockReason') if isinstance(feedback,dict) else None
        if isinstance(block,str) and block not in ['','BLOCK_REASON_UNSPECIFIED']:
            self.terminal=True;self.source_error=True
        if len(candidates)>1:raise RuntimeError('unsupported_gemini_candidate_count')
        if not candidates:return [copy.deepcopy(event)]
        candidate=candidates[0];parts=candidate.get('content',{}).get('parts',[])
        reason=candidate.get('finishReason')
        if isinstance(reason,str) and reason not in ['','FINISH_REASON_UNSPECIFIED']:
            self.finish_reason=reason;self.terminal=True
        if not isinstance(parts,list):raise RuntimeError('invalid_native_gemini_parts')
        for part in parts:
            text = part.get('text')
            if isinstance(text, str) and text:
                if part.get('thought') is True:
                    self.thought_or_media = True
                else:
                    self.visible_text = True
            inline = part.get('inlineData', part.get('inline_data'))
            if isinstance(inline, dict):
                mime = inline.get('mimeType', inline.get('mime_type'))
                data = inline.get('data')
                self.thought_or_media |= isinstance(mime, str) and bool(mime) and isinstance(data, str) and bool(data)
        calls=[p['functionCall'] for p in parts if 'functionCall' in p]
        assigned_id=False
        for call in calls:
            identifier=call.get('id')
            if identifier is None or identifier=='':
                identifier='call_'+uuid4().hex
                call['id']=identifier
                assigned_id=True
            if not isinstance(identifier,str) or identifier in self.call_ids:
                raise RuntimeError('ambiguous_parallel_function_calls')
            self.call_ids.add(identifier)
        self.calls.extend(copy.deepcopy(calls))
        if len(parts)<2:
            if assigned_id:
                raw=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
                event={**event,'data_base64':base64.b64encode(raw).decode(),'bytes':len(raw)}
            return [copy.deepcopy(event)]
        projected=[]
        for index,part in enumerate(parts):
            value=copy.deepcopy(body);target=value['candidates'][0];target['content']['parts']=[copy.deepcopy(part)]
            if index<len(parts)-1:target.pop('finishReason',None);value.pop('usageMetadata',None)
            raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode();frame=copy.deepcopy(event)
            self.sequence+=1;frame.update(data_base64=base64.b64encode(raw).decode(),bytes=len(raw),compatibility_part_index=index,compatibility_frame=self.sequence)
            projected.append(frame)
        return projected
