"""AGY受控阶段快照；原生日志、HOME和配置不作为管理下载。"""
import copy
import fcntl
import gzip
import hashlib
from io import BytesIO
import json
import os
import re
import stat
import shutil
import time
import uuid
import zlib
from pathlib import Path

from runtime_files import atomic_json, directory_fd
from .system_prompt import POLICY_SOURCE, RULE_VERSION, USER_REMINDER_SOURCE

BODY_LIMIT = 2 * 1024 * 1024
FILE_LIMIT = 6 * 1024 * 1024
FULL_EGRESS_BODY_LIMIT = 64 * 1024 * 1024
EGRESS_FILE_LIMIT = 2 * FULL_EGRESS_BODY_LIMIT + FILE_LIMIT
STORAGE_LIMIT = 1024 * 1024 * 1024
RETENTION_MS = 7 * 86400 * 1000
SENSITIVE = re.compile(r'authorization|cookie|token|api[-_]?key|password|secret', re.I)
PREVIEW_KEYS = {'source','representation','headers','body','body_truncated','headers_truncated','original_body_bytes','original_body_sha256','captured_at_ms'}
EGRESS_SOURCE = 'agy_http_transport'
EGRESS_REPRESENTATION = 'http_entity_from_transport_trace'
NATIVE_TLS_SOURCE = 'agy_native_tls'
NATIVE_TLS_REPRESENTATION = 'http_entity_from_tls_accepted_write'
EGRESS_KEYS = PREVIEW_KEYS | {'status','http_status','complete','reason'}
HEADER_TOKEN = re.compile(r"[!#$%&'*+.^_\x60|~0-9A-Za-z-]{1,128}")


def _identifier(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('AGY采集尝试标识无效')
    return value


def _redacted(value, bearer, related):
    secrets = {bearer} if isinstance(bearer, str) and bearer else set()
    def collect(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if SENSITIVE.search(key) and isinstance(child, str) and child:
                    secrets.add(child)
                collect(child)
        elif isinstance(item, list):
            for child in item: collect(child)
    def redact(item):
        if isinstance(item, dict): return {key: '[redacted]' if SENSITIVE.search(key) else redact(child) for key, child in item.items()}
        if isinstance(item, list): return [redact(child) for child in item]
        return item
    collect(value)
    for item in related:collect(item)
    raw = json.dumps(redact(value), ensure_ascii=False)
    for secret in sorted(secrets, key=len, reverse=True):
        for encoded in {json.dumps(secret, ensure_ascii=False)[1:-1], json.dumps(secret)[1:-1]}:
            raw = raw.replace(encoded, '[redacted]')
    return raw


def _preview(value, source, representation, budget, bearer, related):
    original = json.dumps(value, ensure_ascii=False).encode()
    redacted = _redacted(value, bearer, related).encode()
    body = redacted[:budget].decode('utf-8', errors='ignore')
    return {'source': source, 'representation': representation, 'headers': [], 'body': body,
        'body_truncated': len(redacted) > budget, 'headers_truncated': False,
        'original_body_bytes': len(original), 'original_body_sha256': hashlib.sha256(original).hexdigest()}


def _snapshot_directory(folder):
    directory=directory_fd(folder)
    try:
        owner=os.fstat(directory)
        try:
            os.mkdir('snapshots',0o700,dir_fd=directory)
            if os.geteuid()==0:os.chown('snapshots',owner.st_uid,owner.st_gid,dir_fd=directory,follow_symlinks=False)
        except FileExistsError:pass
        return directory_fd(Path(folder)/'snapshots'),owner
    finally:os.close(directory)


def _save(folder, value):
    folder=Path(folder);base=folder.parent if folder.name in ('ingress','egress') else folder
    directory,owner=_snapshot_directory(base)
    lock=None
    try:
        lock=os.open('.capture.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=directory)
        metadata=os.fstat(lock)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1:raise ValueError('采集写入锁无效')
        if os.geteuid()==0:os.fchown(lock,owner.st_uid,owner.st_gid)
        # 三阶段共享容量锁。后台写入短暂等待，避免 TLS 快照挤掉紧随其后的拒绝入站。
        lock_deadline = time.monotonic() + .15
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= lock_deadline:
                    raise
                time.sleep(.005)
        target,unused=_snapshot_directory(folder)
        os.close(target)
        # 同一账号的入站、提交快照和历史调试材料共同占用预算；路径逐级拒绝链接。
        stack=[base];entries=[];total=0;count=0;deadline=time.monotonic()+1
        while stack:
            current=stack.pop();source=directory_fd(current)
            try:
                with os.scandir(source) as listing:
                    for entry in listing:
                        count+=1
                        if count>10000 or time.monotonic()>deadline:raise ValueError('采集容量扫描达到预算')
                        metadata=entry.stat(follow_symlinks=False)
                        if stat.S_ISDIR(metadata.st_mode):stack.append(current/entry.name)
                        elif stat.S_ISREG(metadata.st_mode):
                            if metadata.st_nlink!=1:raise ValueError('采集存储包含硬链接')
                            total+=metadata.st_size
                            if current.name=='snapshots' and entry.name.endswith('.json'):
                                try:_identifier(entry.name[:-5])
                                except ValueError:continue
                                entries.append((metadata.st_mtime_ns,str(current),entry.name,metadata))
                        elif stat.S_ISLNK(metadata.st_mode):raise ValueError('采集存储包含链接')
            finally:os.close(source)
        raw_size=len(json.dumps(value,ensure_ascii=False).encode())
        limit=EGRESS_FILE_LIMIT if value.get('full_body') else FILE_LIMIT
        if raw_size>limit:raise ValueError('AGY快照超过上限')
        for _,parent,name,previous in sorted(entries):
            if total+raw_size<=STORAGE_LIMIT:break
            source=directory_fd(Path(parent))
            try:
                current=os.stat(name,dir_fd=source,follow_symlinks=False)
                if (current.st_ino,current.st_dev,current.st_mtime_ns)!=(previous.st_ino,previous.st_dev,previous.st_mtime_ns):raise ValueError('采集文件身份已变化')
                os.unlink(name,dir_fd=source);total-=previous.st_size
            finally:os.close(source)
        if total+raw_size>STORAGE_LIMIT:raise ValueError('AGY快照存储已满')
        atomic_json(folder/'snapshots'/(_identifier(value['attempt_id'])+'.json'),value)
    finally:
        if lock is not None:os.close(lock)
        os.close(directory)


def save_submission(root, account_id, attempt_id, decoded, submitted, bearer, policy=None):
    """保存本次独立系统段及原生提交预览。@param root 账号采集根。@param account_id 账号。@param attempt_id 真实尝试。@param decoded 解码输入。@param submitted Cortex请求。@param bearer 已知AT。@return 无。"""
    _identifier(attempt_id)
    related=(decoded,submitted)
    native = _preview(submitted, 'cortex_submission', 'native_cascade_prompt_sections', BODY_LIMIT // 2, bearer,related)
    original = _preview(decoded, 'decoded_gemini_input', 'decoded_gemini_input', BODY_LIMIT // 4, bearer,related)
    value = {'schema_version': 1, 'stage': 'agy_prepared', 'account_id': account_id, 'attempt_id': attempt_id,
        'captured_at_ms': int(time.time() * 1000), **native, 'decoded_gemini': original,'system_prompt_policy':policy,
        'stages': [{'stage': 'decoded_gemini', 'source': original['source'], 'representation': original['representation'], 'status': 'truncated' if original['body_truncated'] else 'complete'},
            {'stage': 'agy_prepared', 'source': native['source'], 'representation': native['representation'], 'status': 'truncated' if native['body_truncated'] else 'complete'},
            {'stage': 'wire_final', 'source': 'unavailable', 'representation': 'unavailable', 'status': 'unavailable', 'note': '本次未采集AGY最终TLS线字节'}]}
    _save(root, value)


def save_ingress(root, account_id, attempt_id, ingress):
    """保存网关已脱敏的独立入站旁路。@param root 已绑定账号根。@param account_id 账号。@param attempt_id 尝试。@param ingress 有界入站。@return 无。"""
    if not isinstance(ingress,dict) or ingress.get('source')!='gateway_http_ingress' or ingress.get('representation')!='http_logical_bytes':raise ValueError('入口来源无效')
    _validate_preview(ingress,1024*1024)
    if set(ingress)-PREVIEW_KEYS:raise ValueError('入口包含未知字段')
    value = {'schema_version': 1, 'stage': 'agy_ingress', 'account_id': account_id, 'attempt_id': _identifier(attempt_id),
        'captured_at_ms': int(time.time() * 1000), 'ingress': ingress}
    _save(_channel(root,'ingress'), value)


def _channel(root, name):
    root=Path(root)
    directory=directory_fd(root)
    try:
        owner=os.fstat(directory)
        try:
            os.mkdir(name,0o700,dir_fd=directory)
            if os.geteuid()==0:os.chown(name,owner.st_uid,owner.st_gid,dir_fd=directory,follow_symlinks=False)
        except FileExistsError:pass
    finally:os.close(directory)
    return root/name


def save_egress(root, account_id, attempt_id, trace, expected, incoming, forwarded, bearer, *, native_tls=False, full_body=False):
    """保存实际传输观察及逐头处理。@param root 采集根。@param account_id 账号。@param attempt_id 尝试。@param trace 实际传输观察。@param expected 本次发送实体。@param incoming AGY 交给适配层的头。@param forwarded 适配层保留的头。@param bearer 当前访问凭据。@param native_tls 是否原生TLS接受字节。@param full_body 是否保存完整脱敏正文。@return 无。"""
    raw=trace.body(expected)
    headers=trace.headers or []
    original_headers={name.lower() for name,_ in incoming if HEADER_TOKEN.fullmatch(name)}
    forwarded_values={name.lower():value.strip() for name,_,value in (header.partition(':') for header in forwarded)}
    sent_values={name:value for name,value in headers if HEADER_TOKEN.fullmatch(name)}
    secrets={value for name,value in (*incoming,*headers) if value and SENSITIVE.search(name)}
    if bearer:secrets.add(bearer)
    ordered_secrets=sorted(secrets,key=len,reverse=True)
    display=[];header_bytes=0
    for name,value in headers:
        if SENSITIVE.search(name):
            value='[redacted]'
        else:
            for secret in ordered_secrets:
                value=value.replace(secret,'[redacted]')
        size=len(name.encode())+len(value.encode())
        if header_bytes+size>64*1024 or len(display)>=128:break
        display.append([name,value]);header_bytes+=size
    body='';truncated=False
    if raw is not None:
        try:
            entity=raw
            if ['content-encoding','gzip'] in headers:
                with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                    entity=stream.read(FULL_EGRESS_BODY_LIMIT+1)
            if len(entity)>FULL_EGRESS_BODY_LIMIT:raise ValueError('出站正文过大')
            related=({name:value} for name,value in (*incoming,*headers))
            cleaned=_redacted(json.loads(entity),bearer,related).encode()
            budget=FULL_EGRESS_BODY_LIMIT if full_body else BODY_LIMIT//2
            body=cleaned[:budget].decode('utf-8',errors='ignore')
            truncated=len(cleaned)>budget
        except (ValueError,OSError,EOFError,zlib.error):truncated=True
    source,representation=(NATIVE_TLS_SOURCE,NATIVE_TLS_REPRESENTATION) if native_tls else (EGRESS_SOURCE,EGRESS_REPRESENTATION)
    wire={'source':source,'representation':representation,'status':'complete' if raw is not None else 'incomplete',
        'complete':raw is not None,'reason':None if raw is not None else 'HTTP_PARTIAL','http_status':trace.status,
        'body':body,'body_truncated':truncated,'headers':display,'headers_truncated':len(display)<len(headers),
        'original_body_bytes':len(raw) if raw is not None else None,
        'original_body_sha256':hashlib.sha256(raw).hexdigest() if raw is not None else None}
    decisions=[]
    for name in sorted(original_headers|sent_values.keys()):
        if native_tls:
            action,reason='runtime','AGY 原生 TLS 写入观察'
        elif name in sent_values and name in forwarded_values and sent_values[name]==forwarded_values[name]:
            action,reason='keep','出站适配沿用 AGY 原生值'
        elif name in sent_values:
            action,reason='runtime','按实际目标或正文重新生成'
        elif trace.headers is None:
            continue
        else:
            action,reason='drop','出站适配移除或由传输层重新计算'
        decisions.append({'name':name,'action':action,'reason':reason})
    value={'schema_version':1,'stage':'agy_egress','account_id':account_id,'attempt_id':_identifier(attempt_id),
        'captured_at_ms':int(time.time()*1000),'wire_final':wire,'decisions':decisions[:128],
        'observed_count':len(decisions)}
    if full_body:value['full_body']=True
    _save(_channel(root,'egress'), value)


def _read(root, account_id, attempt_id, stage, allow_expired=False):
    file_limit=EGRESS_FILE_LIMIT if stage=='agy_egress' else FILE_LIMIT
    directory = directory_fd(Path(root) / 'snapshots')
    try:
        descriptor = os.open(_identifier(attempt_id) + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_mode & 0o077 or metadata.st_size > file_limit:
                raise ValueError('AGY快照文件无效')
            value = json.loads(stream.read(metadata.st_size + 1))
    finally: os.close(directory)
    if not isinstance(value,dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1 or type(value.get('account_id')) is not int or value['account_id'] != account_id or value.get('attempt_id') != attempt_id or value.get('stage') != stage:
        raise ValueError('AGY快照归属无效')
    captured = value.get('captured_at_ms')
    now = int(time.time() * 1000)
    if type(captured) is not int or captured<=0 or captured > now + 300000: raise ValueError('AGY快照时间无效')
    if not allow_expired and captured < now - RETENTION_MS: raise TimeoutError('AGY快照已过期')
    if stage=='agy_prepared':
        _validate_preview(value,BODY_LIMIT//2);_validate_preview(value.get('decoded_gemini'),BODY_LIMIT//4)
        decoded=value['decoded_gemini']
        if set(decoded)-PREVIEW_KEYS or decoded.get('source')!='decoded_gemini_input' or decoded.get('representation')!='decoded_gemini_input':raise ValueError('解码输入来源无效')
        policy=value.get('system_prompt_policy')
        if policy is not None:
            if not isinstance(policy,dict) or set(policy)!={'schema_version','enabled','rule_version','rule_sha256','source','changed','replaced_codepoints','system_codepoints'}:raise ValueError('策略回执字段无效')
            if type(policy['schema_version']) is not int or policy['schema_version']!=1 or type(policy['enabled']) is not bool or type(policy['changed']) is not bool or policy['rule_version']!=RULE_VERSION or policy['source'] not in (POLICY_SOURCE, USER_REMINDER_SOURCE) or not isinstance(policy['rule_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',policy['rule_sha256']):raise ValueError('策略回执来源无效')
            if any(type(policy[key]) is not int or policy[key]<0 for key in ['replaced_codepoints','system_codepoints']):raise ValueError('策略回执计数无效')
        if value.get('source')!='cortex_submission' or value.get('representation')!='native_cascade_prompt_sections':raise ValueError('原生提交来源无效')
        if not isinstance(value.get('stages'),list) or len(value['stages'])!=3:raise ValueError('原生阶段数量无效')
        for row,name,source,representation in zip(value['stages'],['decoded_gemini','agy_prepared','wire_final'],['decoded_gemini_input','cortex_submission','unavailable'],['decoded_gemini_input','native_cascade_prompt_sections','unavailable']):
            if not isinstance(row,dict) or row.get('stage')!=name or row.get('source')!=source or row.get('representation')!=representation or row.get('status') not in {'complete','truncated','unavailable'}:raise ValueError('原生阶段来源无效')
            if set(row)-{'stage','source','representation','status','note'} or not isinstance(row.get('note',''),str) or len(row.get('note',''))>128:raise ValueError('原生阶段字段无效')
            if (name=='wire_final') != (row['status']=='unavailable'):raise ValueError('最终线字节状态无效')
        allowed={'schema_version','stage','account_id','attempt_id','captured_at_ms','source','representation','headers','body','body_truncated','headers_truncated','original_body_bytes','original_body_sha256','decoded_gemini','stages','system_prompt_policy'}
        if set(value)-allowed:raise ValueError('快照包含未知字段')
    elif stage=='agy_ingress':
        ingress=value.get('ingress');_validate_preview(ingress,1024*1024)
        if set(value)-{'schema_version','stage','account_id','attempt_id','captured_at_ms','ingress'} or set(ingress)-PREVIEW_KEYS or ingress.get('source')!='gateway_http_ingress' or ingress.get('representation')!='http_logical_bytes':raise ValueError('入口来源无效')
    else:
        _validate_egress(value)
    return value


def cleanup_snapshot_steps(root, account_id, stopping=lambda: False):
    """按实际归属和七天时间清理快照，保护后来原子替换。@param root 环境根。@param account_id 网关账号。@param stopping 停止标记。@return 逐项清理计数。"""
    base=Path(root)/'flows/api/agy-prepared'
    for folder,stage in [(base,'agy_prepared'),(base/'ingress','agy_ingress'),(base/'egress','agy_egress')]:
        try:directory=directory_fd(folder/'snapshots')
        except FileNotFoundError:continue
        try:
            for entry in os.scandir(directory):
                if stopping():return
                result={'scanned':1,'deleted':0,'failed':0}
                try:
                    if not entry.name.endswith('.json'):continue
                    attempt=_identifier(entry.name[:-5]);before=entry.stat(follow_symlinks=False)
                    value=_read(folder,account_id,attempt,stage,allow_expired=True)
                    if value['captured_at_ms']<int(time.time()*1000)-RETENTION_MS:
                        current=os.stat(entry.name,dir_fd=directory,follow_symlinks=False)
                        if (before.st_dev,before.st_ino,before.st_mtime_ns)==(current.st_dev,current.st_ino,current.st_mtime_ns):
                            os.unlink(entry.name,dir_fd=directory);result['deleted']=1
                except FileNotFoundError:pass
                except (ValueError,OSError):result['failed']=1
                yield result
        finally:os.close(directory)
    # 历史调试目录仅在原worker已退役且保留期结束后清理。
    if base.is_symlink():raise ValueError('AGY采集根不能为链接')
    if base.is_dir():
        for folder in base.iterdir():
            if stopping():return
            if not re.fullmatch('[0-9a-f]{32}',folder.name) or folder.is_symlink() or not folder.is_dir():continue
            result={'scanned':1,'deleted':0,'failed':0}
            try:
                directory=directory_fd(folder)
                try:
                    records=[]
                    for name in ['retired.json','config.json']:
                        descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
                        with os.fdopen(descriptor,'rb') as stream:
                            info=os.fstat(stream.fileno())
                            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>16384:raise ValueError('历史采集标记无效')
                            records.append(json.loads(stream.read(16385)))
                    retired,config=records
                    if config.get('account_id')!=account_id:raise ValueError('历史采集账号不符')
                    at=retired.get('retired_at')
                    if type(at) in (int,float) and 0<at<time.time()-RETENTION_MS/1000:
                        shutil.rmtree(folder);result['deleted']=1
                finally:os.close(directory)
            except FileNotFoundError:pass
            except (ValueError,OSError,AttributeError):result['failed']=1
            yield result


def cleanup_environment_steps(runtime):
    """按AGY独立账号映射分页生成清理步骤。@param runtime 现有环境运行时。@return 逐项计数。"""
    after=''
    while not runtime.stopping.is_set():
        connection=runtime.database()
        try:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='platform_api_environments'").fetchone():return
            rows=connection.execute('SELECT e.*,p.gateway_account_id FROM platform_api_environments p JOIN account_environments e ON e.environment_id=p.environment_id WHERE e.environment_id>? ORDER BY e.environment_id LIMIT 32',(after,)).fetchall()
        finally:connection.close()
        if not rows:return
        for stored in rows:
            if runtime.stopping.is_set():return
            row=dict(stored);after=row['environment_id']
            try:yield from cleanup_snapshot_steps(runtime._root(row),row['gateway_account_id'],runtime.stopping.is_set)
            except (ValueError,OSError):yield {'scanned':0,'deleted':0,'failed':1}


def _validate_preview(value,budget):
    if not isinstance(value,dict) or not isinstance(value.get('body'),str) or len(value['body'].encode())>budget:raise ValueError('预览正文无效')
    headers=value.get('headers')
    if not isinstance(headers,list) or len(headers)>1024 or len(json.dumps(headers).encode())>128*1024:raise ValueError('预览头无效')
    if any(not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(item,str) for item in pair) for pair in headers):raise ValueError('预览头类型无效')
    if type(value.get('body_truncated')) is not bool or type(value.get('headers_truncated')) is not bool:raise ValueError('预览截断状态无效')
    if type(value.get('original_body_bytes')) is not int or value['original_body_bytes']<0 or not isinstance(value.get('original_body_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',value['original_body_sha256']):raise ValueError('原始摘要无效')
    if 'captured_at_ms' in value and (type(value['captured_at_ms']) is not int or value['captured_at_ms']<=0 or value['captured_at_ms']>int(time.time()*1000)+300000):raise ValueError('入口预览时间无效')


def _validate_egress(value):
    keys={'schema_version','stage','account_id','attempt_id','captured_at_ms','wire_final','decisions','observed_count'}
    wire=value.get('wire_final')
    if set(value)-{'full_body'}!=keys or type(value.get('full_body',False)) is not bool or not isinstance(wire,dict) or set(wire)!=EGRESS_KEYS-{'captured_at_ms'}:
        raise ValueError('出站采集字段无效')
    if (wire.get('source'),wire.get('representation')) not in ((EGRESS_SOURCE,EGRESS_REPRESENTATION),(NATIVE_TLS_SOURCE,NATIVE_TLS_REPRESENTATION)):
        raise ValueError('出站采集来源无效')
    status=wire.get('http_status')
    if status is not None and (type(status) is not int or not 100<=status<=599):raise ValueError('上游状态无效')
    if wire.get('complete') is True and wire.get('status')=='complete' and wire.get('reason') is None:
        _validate_preview(wire,FULL_EGRESS_BODY_LIMIT if value.get('full_body') else BODY_LIMIT//2)
    elif (wire.get('complete') is False and wire.get('status')=='incomplete' and wire.get('reason')=='HTTP_PARTIAL'
          and wire.get('original_body_bytes') is None and wire.get('original_body_sha256') is None and wire.get('body')==''):
        _validate_preview({**wire,'original_body_bytes':0,'original_body_sha256':'0'*64},BODY_LIMIT//2)
    else:raise ValueError('出站采集完整性无效')
    decisions=value['decisions']
    count=value['observed_count']
    if not isinstance(decisions,list) or len(decisions)>128 or type(count) is not int or count<len(decisions):
        raise ValueError('出站头处理数量无效')
    for row in decisions:
        if (not isinstance(row,dict) or set(row)!={'name','action','reason'} or not isinstance(row['name'],str)
                or not HEADER_TOKEN.fullmatch(row['name']) or row['action'] not in ('drop','keep','runtime')
                or not isinstance(row['reason'],str) or len(row['reason'])>128):
            raise ValueError('出站头处理无效')


def _ingress_decisions(ingress):
    for name in sorted({name.lower() for name,_ in ingress.get('headers',[]) if HEADER_TOKEN.fullmatch(name)}):
        if name in ('x-api-key','x-goog-api-key'):
            action,reason='context','网关用于入口鉴权'
        elif name=='authorization':
            action,reason='runtime','网关鉴权后由 AGY 使用账号凭据'
        elif name in ('content-type','content-length','transfer-encoding','host','user-agent','accept-encoding','connection'):
            action,reason='runtime','由 AGY 生成实际模型请求头'
        else:
            action,reason='drop','网关的 Gemini 请求信封未转发该入口头'
        yield {'name':name,'action':action,'reason':reason,'stage':'ingress'}


def read_snapshot(root, account_id, attempt_id):
    """读取固定平台目录并合并有界阶段。@param root 已绑定环境根。@param account_id 账号。@param attempt_id 尝试。@return 脱敏快照。"""
    base = Path(root) / 'flows/api/agy-prepared'
    try:
        value = _read(base, account_id, attempt_id, 'agy_prepared')
    except FileNotFoundError:
        value = None
    try:
        ingress = _read(base / 'ingress', account_id, attempt_id, 'agy_ingress')['ingress']
    except FileNotFoundError: ingress = None
    try:
        egress = _read(base / 'egress', account_id, attempt_id, 'agy_egress')
    except FileNotFoundError: egress = None
    if ingress is not None:
        ingress = copy.deepcopy(ingress)
        raw = ingress['body'].encode()
        ingress['body'] = raw[:BODY_LIMIT // 4].decode('utf-8', errors='ignore')
        ingress['body_truncated'] = bool(ingress.get('body_truncated')) or len(raw) > BODY_LIMIT // 4
        if value is None:
            value = {**ingress, 'schema_version': 1, 'stage': 'agy_ingress', 'account_id': account_id,
                'attempt_id': attempt_id, 'stages': []}
        value['ingress'] = ingress
        value['stages'].insert(0, {'stage': 'ingress', 'source': 'gateway_http_ingress', 'representation': 'http_logical_bytes', 'status': 'truncated' if ingress['body_truncated'] else 'complete'})
    else:
        if value is None and egress is None:
            raise FileNotFoundError('本次请求的采集文件尚未保存')
        if value is not None:
            value['stages'].insert(0, {'stage':'ingress','source':'unavailable','representation':'unavailable','status':'unavailable','note':'本次入站旁路缺失或尚未保存'})
    decisions=list(_ingress_decisions(ingress or {}))
    count=len(decisions)
    if egress is not None:
        wire=egress['wire_final']
        if value is None:
            value={key:egress[key] for key in ('schema_version','account_id','attempt_id','captured_at_ms')}
            value.update(stage='agy_egress',stages=[])
        elif value['stage']=='agy_ingress':
            value['stage']='agy_egress'
            for key in PREVIEW_KEYS-{'captured_at_ms'}:value.pop(key,None)
        value['wire_final']=wire
        # 给出站预览腾出共享正文预算，历史及仅入口记录沿原预算读取。
        sections={'ingress':ingress,'decoded_gemini':value.get('decoded_gemini'),'agy_prepared':value}
        for stage,budget in [('agy_prepared',BODY_LIMIT//4),('decoded_gemini',BODY_LIMIT//8),('ingress',BODY_LIMIT//8)]:
            section=sections[stage]
            if section is None or 'body' not in section:continue
            encoded=section['body'].encode()
            if len(encoded)>budget:
                section['body']=encoded[:budget].decode('utf-8',errors='ignore')
                section['body_truncated']=True
        value['stages']=[row for row in value['stages'] if row['stage']!='wire_final']
        for row in value['stages']:
            section=sections.get(row['stage'])
            if section and section.get('body_truncated'):row['status']='truncated'
        status='truncated' if wire['complete'] and wire['body_truncated'] else wire['status']
        value['stages'].append({'stage':'wire_final','source':wire['source'],'representation':wire['representation'],'status':status})
        decisions.extend({**row,'stage':'egress'} for row in egress['decisions'])
        count+=egress['observed_count']
    if decisions and value['stage']!='agy_ingress':
        value['header_policy']={'source':'agy_header_policy','status':'truncated' if count>128 or (ingress or {}).get('headers_truncated') else 'complete',
            'observed_count':count,'stored_count':min(128,len(decisions)),'decisions':decisions[:128]}
    return value
