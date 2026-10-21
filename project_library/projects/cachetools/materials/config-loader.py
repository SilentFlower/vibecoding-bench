import json
from pathlib import Path
from cachetools import TTLCache, cached

clock = [0.0]
reads = []
cache = TTLCache(maxsize=4, ttl=5, timer=lambda: clock[0])

@cached(cache)
def read_config(filename):
    """读取一次真实配置。@param filename 文件路径。@return JSON对象。"""
    reads.append(filename)
    return json.loads(Path(filename).read_text(encoding="utf-8"))
