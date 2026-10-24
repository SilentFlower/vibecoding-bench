"""完整原生回归仅规范化子项repr对象地址，不丢节点或结果。"""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import base64
import gzip
import hashlib
import json
import re
spec=spec_from_file_location("frozen_more_control",Path(__file__).with_name("native_regression.py"))
control=module_from_spec(spec);spec.loader.exec_module(control)
original=control._subtest_results
address=re.compile(r"(?<= at )0x[0-9a-fA-F]+(?=>)")


def normalized(reports,node_ids):
    """保留每个真实子项只替换repr地址。@param reports 原报告。@param node_ids 原节点。@return 全部同序子项。"""
    result=original(reports,node_ids)
    for item in result:
        for key,value in item["context"]["kwargs"].items():
            item["context"]["kwargs"][key]=address.sub("<address>",value)
    return result


control._subtest_results=normalized
original_run=control._run


def archived_run(options):
    """原控制已完整逐项核验后无损压缩输出。@param options 原CLI参数。@return 保全部实际子项可恢复档案的有界报告。"""
    result=original_run(options)
    if "subtests" not in result:return result
    result=dict(result);items=result.pop("subtests")
    raw=json.dumps(items,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
    compressed=gzip.compress(raw,mtime=0)
    result["subtests_archive"]={"encoding":"canonical-json+gzip+base64","count":len(items),
        "raw_bytes":len(raw),"raw_sha256":hashlib.sha256(raw).hexdigest(),
        "gzip_bytes":len(compressed),"gzip_sha256":hashlib.sha256(compressed).hexdigest(),
        "data":base64.b64encode(compressed).decode("ascii")}
    result["subtests_digest"]=hashlib.sha256(raw).hexdigest()
    # Docker日志和协议都是2MiB，预留一半余量；压缩不会跳过任何节点、顺序或结果。
    if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode("utf-8"))>1024*1024:
        raise ValueError("完整子项无损档案超过安全输出预算")
    return result


control._run=archived_run
if __name__=="__main__":control.main()
