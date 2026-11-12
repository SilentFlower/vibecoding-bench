"Public regression tests for LOGURU-O04-DEV; the complete business contract is in materials/LOGURU-O04-DEV-contract.md."
from copy import deepcopy
from loguru import logger
import json
import pytest

def clean():
    "Support the public regression through clean."
    logger.remove();log=deepcopy(logger);log.remove();return log

def test_per_sink_callback_and_shared_record_are_isolated():
    "Verify per sink callback and shared record are isolated."
    log=clean();encoded=[];plain=[];calls=[]
    def serializer(record,text):
        calls.append(text);record['extra']['nested'].append('private');record['level'].name='changed'
        return json.dumps({'message':record['message'],'extra':record['extra']},ensure_ascii=False)+'\n'
    log.add(encoded.append,format='{message}',serializer=serializer,catch=False)
    log.add(plain.append,format='{level}:{message}:{extra[nested]}')
    source=['original'];log.bind(nested=source).info('中文')
    assert calls==['中文\n'] and source==['original'] and ''.join(plain)=="INFO:中文:['original']\n"
    assert json.loads(encoded[0])=={'message':'中文','extra':{'nested':['original','private']}}
    log.remove()

def test_queue_producer_callback_once_and_builtin_json_stays_same():
    "Verify queue producer callback once and builtin json stays same."
    import threading
    log=clean();messages=[];threads=[]
    def serializer(record,text):threads.append(threading.get_ident());return 'custom:'+text
    log.add(messages.append,serializer=serializer,enqueue=True,format='{message}',catch=False)
    log.info('one');log.complete();assert ''.join(messages)=='custom:one\n' and threads==[threading.get_ident()]
    log.remove();encoded=[];log.add(encoded.append,serialize=True,format='{message}');log.info('two')
    assert json.loads(encoded[0])['record']['message']=='two';log.remove()

def test_invalid_config_result_and_callback_failure_are_explicit():
    "Verify invalid config result and callback failure are explicit."
    log=clean()
    with pytest.raises(TypeError):log.add(lambda message:None,serializer=42)
    with pytest.raises(ValueError):log.add(lambda message:None,serialize=True,serializer=lambda record,text:text)
    assert not log._core.handlers
    log.add(lambda message:None,serializer=lambda record,text:b'wrong',catch=False)
    with pytest.raises(TypeError):log.info('x')
    log.remove()
