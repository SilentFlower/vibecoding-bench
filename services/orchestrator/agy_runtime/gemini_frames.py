"""将原生 Gemini 源帧投影为现有 new-api 可消费的单 Part 流。"""
import base64
import copy
import json


class Frames:
    """保存本请求的输出归属和函数调用摘要。"""

    def __init__(self):
        """创建独立帧状态。@return 无。"""
        self.calls=[];self.sequence=0;self.terminal=False

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
        candidates=body.get('candidates',[])
        # 官方控制RPC和通道EOF都可能在截断后正常返回，业务成功还须有源终态。
        feedback=body.get('promptFeedback',{})
        block=feedback.get('blockReason') if isinstance(feedback,dict) else None
        self.terminal=self.terminal or isinstance(block,str) and block not in ['','BLOCK_REASON_UNSPECIFIED']
        if len(candidates)>1:raise RuntimeError('unsupported_gemini_candidate_count')
        if not candidates:return [copy.deepcopy(event)]
        candidate=candidates[0];parts=candidate.get('content',{}).get('parts',[])
        reason=candidate.get('finishReason')
        self.terminal=self.terminal or isinstance(reason,str) and reason not in ['','FINISH_REASON_UNSPECIFIED']
        if not isinstance(parts,list):raise RuntimeError('invalid_native_gemini_parts')
        calls=[p['functionCall'] for p in parts if 'functionCall' in p]
        names=[c['name'] for c in self.calls+calls]
        # 网关会去掉函数 ID；同名并发调用的回填归属因此必须显式拒绝。
        if len(names)!=len(set(names)):raise RuntimeError('ambiguous_parallel_function_calls')
        self.calls.extend(copy.deepcopy(calls))
        if len(parts)<2:return [copy.deepcopy(event)]
        projected=[]
        for index,part in enumerate(parts):
            value=copy.deepcopy(body);target=value['candidates'][0];target['content']['parts']=[copy.deepcopy(part)]
            if index<len(parts)-1:target.pop('finishReason',None);value.pop('usageMetadata',None)
            raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode();frame=copy.deepcopy(event)
            self.sequence+=1;frame.update(data_base64=base64.b64encode(raw).decode(),bytes=len(raw),compatibility_part_index=index,compatibility_frame=self.sequence)
            projected.append(frame)
        return projected
