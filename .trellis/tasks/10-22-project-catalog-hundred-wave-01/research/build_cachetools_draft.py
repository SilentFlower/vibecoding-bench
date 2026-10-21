"""根据逐仓已冻结设计制作Cachetools草稿，不修改正式目录。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import snapshot_tree


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-01'
PROJECT = WORKSPACE / 'drafts/projects/cachetools'
REVISION = '6f23e2a7b75a42d30cb9d890ab3ca4059ee01bfd'


def write(relative: str, content: str | dict) -> None:
    """写入本仓独占草稿中的固定材料。

    :param relative: 草稿内相对路径。
    :param content: 文本或JSON对象。
    :return: None。
    """
    path = PROJECT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n'
        if isinstance(content, dict) else content, encoding='utf-8')


def main() -> None:
    """生成九项真实任务及独立材料、rubric和原生引用。

    :return: None。
    """
    if (PROJECT / 'project.json').exists():
        raise ValueError('草稿manifest已存在，拒绝覆盖')
    write('materials/config-loader.py', '''import json
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
''')
    write('materials/config-events.md', '''The JSON file initially contains {"商品":"咖啡","price":35}.
Call read_config(path) twice at clock=0. Replace the file with price=40 at clock=1.
Call again at clock=4.999 and clock=5.0. Keep the same path throughout.
The timer is controlled for a reproducible local exercise; no real sleeps are needed.
''')
    write('materials/publish-requirements.md', '''A local process reads a small validated configuration JSON file repeatedly.
Publishing a new version must not expose a partially written file. Bound the cache,
choose an explicit invalidation/version policy, and propagate invalid JSON on a cache miss.
Do not promise that TTLCache watches the filesystem, caches exceptions, or makes returned
mutable objects independent. Prefer existing library APIs and application design.
''')
    write('materials/price-symptom.md', '''A product-price lookup sometimes returns the wrong business price after another lookup.
The exact functions, cache/key configuration and call order are not yet available.
Do not modify files or assume a root cause from this symptom alone.
''')
    price_source = '''from cachetools import cachedmethod

class Prices:
    """模拟一个对象中的两种业务报价。"""
    def __init__(self):
        """创建共享缓存。@return None。"""
        self.cache = {}

    @cachedmethod(lambda obj: obj.cache)
    def retail(self, sku):
        """返回零售价。@param sku 商品。@return 金额。"""
        return 100

    @cachedmethod(lambda obj: obj.cache)
    def wholesale(self, sku):
        """返回批发价。@param sku 商品。@return 金额。"""
        return 90

prices = Prices()
print(prices.retail("coffee"))
print(prices.wholesale("coffee"))
'''
    write('disclosure/prices.py', price_source)
    write('disclosure/price-events.md', 'Pinned-version output for the supplied script is 100 followed by 100. Both calls use the same object and SKU. No other threads or writes are involved.\n')
    write('disclosure/unavailable.md', 'The exact functions, cache/key configuration and call sequence cannot be provided for this incident. No additional incident evidence is available.\n')
    write('materials/shared-prices.py', price_source)
    write('materials/call-forms.py', '''from cachetools import cached

calls = []

@cached(cache={}, info=True)
def quote(quantity=1):
    """记录实际求值。@param quantity 数量。@return 数量。"""
    calls.append(quantity)
    return quantity

quote()
quote(1)
quote(quantity=1)
print(calls)
print(quote.cache_info())
''')
    write('materials/receiver-reproducer.py', '''from cachetools import cachedmethod

class Catalog:
    """复现类入口与实例入口的调用差异。"""
    def __init__(self):
        """创建独立缓存。@return None。"""
        self.cache = {}

    @cachedmethod(lambda obj: obj.cache)
    def quote(self, sku):
        """返回业务参数。@param sku 商品。@return 商品。"""
        return sku

catalog = Catalog()
print(catalog.quote(sku="coffee"))
print(Catalog.quote(catalog, sku="coffee"))
print(Catalog.quote(self=catalog, sku="coffee"))
''')
    write('materials/receiver-contract.md', '''Repair class access to cachedmethod when the original receiver parameter can be supplied by keyword.
Use the receiver's actual parameter name, which need not be self. Preserve positional and bound calls,
business arguments, instance isolation and info counters. A positional-only receiver must still reject
keyword binding. Missing and duplicate receivers must still raise TypeError. Do not change signatures,
dependencies, unrelated descriptors, pytest controls or global settings. Deliver meaningful public
regression tests in library/tests/test_cachedmethod.py that fail on the pinned original and pass after
the repair. Only library/src/cachetools/_descriptor.py and that public test file are authorized.
''')
    write('materials/mutable-size.py', '''from cachetools import Cache

cache = Cache(maxsize=5, getsizeof=len)
rows = ["coffee"]
cache["rows"] = rows
rows.append("tea")
print(cache.currsize, len(cache["rows"]))
cache["rows"] = rows
print(cache.currsize)
''')

    definitions = [
        ('CT-U01', 'understand', '解释配置文件的命中与TTL精确边界',
            'Trace the supplied file loader and controlled-clock events. Give the returned prices and actual file-read count before and exactly at the five-second TTL boundary. Explain why expiry uses the timer rather than file contents. Do not edit files.',
            ['materials/config-loader.py', 'materials/config-events.md'], 'explained',
            'Explain actual cache hits, the strict expiry boundary and real file reads using the pinned TTLCache and supplied event sequence; distinguish cached data from later disk contents.',
            ['file_hit_and_expiry']),
        ('CT-C01', 'consult', '区分TTL过期与文件变化通知',
            'A configuration file changed but the same path still returns the earlier object before TTL expiry. Is this a library defect? Compare explicit invalidation, shorter TTL and versioned keys using existing APIs. State the consistency tradeoff without changing the library.',
            ['materials/config-loader.py', 'materials/config-events.md'], 'advice_no_code_change',
            'Treat the supplied staleness as normal TTL policy, not filesystem watching; recommend an explicit existing invalidation or version strategy and its limits without claiming automatic change detection.',
            ['file_change_waits_for_ttl']),
        ('CT-P01', 'plan', '规划本地配置发布与缓存一致性',
            'Plan a bounded local configuration publication and cache-read workflow for the supplied requirements. Cover atomic publication, validation, invalidation/versioning, mutable returned data and parse errors on misses. Use existing APIs; distinguish guarantees from tradeoffs. Do not implement changes.',
            ['materials/config-loader.py', 'materials/publish-requirements.md'], 'viable_plan_no_library_change',
            'Provide a workable application plan for atomic publication, validated values, bounded caching and explicit consistency; do not promise exception caching, live file watching or independent copies from ordinary memoization.',
            ['file_hit_and_expiry', 'invalid_json_not_cached']),
        ('CT-D01', 'diagnose', '先取实际缓存证据再判断价格串值',
            'Investigate the supplied intermittent price symptom. Request the minimal actual functions, cache/key configuration and call sequence before assigning a definite cause. Use any subsequently supplied reproduction to diagnose it; if evidence cannot be provided, state the limits and a concrete evidence plan. Do not edit files.',
            ['materials/price-symptom.md'], 'diagnosed_no_code_change',
            'The initial symptom is insufficient. Ask for the actual relevant functions, cache/key configuration and call sequence or an equivalent sufficient reproduction. Only after actual disclosure derive the supported cause. With explicitly unavailable evidence, insufficient_information is legitimate; never invent undisclosed facts.',
            None),
        ('CT-C02', 'consult', '用已有key参数隔离共享缓存的方法',
            'The complete supplied price methods intentionally share one cache. Recommend a correct existing key policy that keeps retail and wholesale results separate for the same SKU. Explain methodkey and instance versus method namespaces, preserve normal business arguments, and decide whether a library modification is needed.',
            ['materials/shared-prices.py'], 'advice_no_code_change',
            'Explain that default methodkey omits the receiver and does not add a method namespace; use distinct caches or a valid existing custom namespaced key without claiming the library already inserts method names or requiring a library change.',
            ['shared_cache_collision', 'namespaced_methods']),
        ('CT-U02', 'understand', '区分调用形式归一化和类型敏感缓存键',
            'Explain the actual calls and miss count for quote(), quote(1) and quote(quantity=1). Would typedkey normalize them? Contrast type-sensitive keys with an explicit argument-normalizing key using existing APIs. Do not edit files.',
            ['materials/call-forms.py'], 'explained',
            'Default hashkey preserves raw positional/keyword call structure and does not fill function defaults. typedkey distinguishes value types rather than normalizing signatures; a correctly defined existing custom key can normalize this specific function.',
            ['raw_call_forms_are_distinct', 'custom_key_normalizes', 'typed_keys_distinguish']),
        ('CT-D02', 'diagnose', '定位类访问的关键字receiver绑定差异',
            'Run or trace the complete cachedmethod reproducer. Explain why bound and positional class calls work but class access with the receiver keyword raises TypeError in the pinned source. Locate the descriptor boundary and distinguish it from cache-key behavior. Do not edit files.',
            ['materials/receiver-reproducer.py'], 'diagnosed',
            'Ground the diagnosis in the public _Unbound call path taking the receiver only from args, while the wrapped original method permits a keyword receiver. Preserve the successful bound/positional controls and do not blame unrelated cache size or timer settings.',
            ['positional_bound_controls', 'original_keyword_receiver_rejected']),
        ('CT-M01', 'modify', '修复类访问关键字receiver并保护原调用合同',
            'Repair the supplied cachedmethod class-access inconsistency under the complete public receiver contract. Support the original receiver parameter name without hardcoding self. Preserve valid bound/positional calls, info and independent instances; keep positional-only, missing and duplicate receiver rejection. Modify only the authorized implementation and public test file, and deliver meaningful original-failing public regression tests.',
            ['materials/receiver-reproducer.py', 'materials/receiver-contract.md'], 'implemented',
            'Satisfy the full public receiver contract using the actual wrapped method signature while preserving unrelated behavior. The independent call matrix and complete frozen upstream regression must pass. Deliver meaningful public original-failing tests and cite the actual authorized implementation and test files; no new pytest controls or dependencies.',
            ['positional_bound_controls', 'keyword_receiver_equivalent', 'custom_receiver_name',
                'missing_receiver_rejected', 'duplicate_receiver_rejected', 'positional_only_preserved',
                'instance_isolation', 'cache_info_preserved']),
        ('CT-C03', 'consult', '解释可变值的插入时容量记账',
            'Explain the actual currsize values in the supplied mutable-list example. Does getsizeof continuously track mutations? Recommend a safe application policy for a hard size budget, including explicit reinsertion and oversized values, without promising an existing automatic reweigh API.',
            ['materials/mutable-size.py'], 'advice_with_limits',
            'Explain insertion-time cost accounting and explicit reassignment remeasurement; recommend immutable values, controlled mutation/reinsertion or an application policy, preserving maxsize checks without inventing automatic tracking or a reweigh API.',
            ['insertion_time_size', 'explicit_reinsert_updates_size', 'oversize_rejected'])]

    tasks = {}
    for identifier, kind, goal, prompt, materials, outcome, criterion, fields in definitions:
        task = {'id': identifier, 'kind': kind, 'goal': goal, 'prompt': prompt,
            'requires': [], 'materials': materials, 'allowed_paths': [],
            'outcomes': [outcome], 'max_turns': 4,
            'evaluation': {'version': 1, 'rubric': 'verification/' + identifier + '.rubric.json', 'semantic': True},
            'branches': []}
        criteria = [{'id': 'business', 'requirement': criterion, 'evidence': []},
            {'id': 'scope', 'requirement': 'Use only actually supplied evidence and the pinned public source. Respect the task authorization and distinguish observed facts, normal limitations and proposals.', 'evidence': []}]
        if kind == 'modify':
            task['allowed_paths'] = ['library/src/cachetools/_descriptor.py', 'library/tests/test_cachedmethod.py']
            for item in criteria:
                item['allow_candidate_evidence'] = True
            criteria.append({'id': 'public-tests', 'requirement': 'Deliver meaningful public regression tests in the authorized test file that fail on the original receiver behavior and pass after the repair; cite the implementation and test files. Mere claims or unrelated tests are insufficient.', 'evidence': [], 'allow_candidate_evidence': True})
        if identifier == 'CT-D01':
            task['outcomes'].append('insufficient_information')
            task['branches'] = [{'id': 'price-evidence',
                'when': 'The complete actual functions, cache/key configuration and call sequence have not been disclosed, and the conversation does not say they are unavailable. The answer reasonably requests those inputs or an equivalently sufficient minimal reproduction. Supply all incident evidence together.',
                'materials': ['disclosure/prices.py', 'disclosure/price-events.md']}]
        if fields is not None:
            native = {'script': 'verification/native_observe.py', 'args': [identifier],
                'python_paths': ['library/src', 'app'],
                'expected': {'candidate_import': True, **{field: True for field in fields}},
                'resource_profile': 'business'}
            if kind == 'modify':
                native['regression'] = {'runner': 'verification/native_regression.py', 'contract': 'verification/native-contract.json'}
            write('verification/' + identifier + '.native.json', native)
            task['evaluation']['native'] = 'verification/' + identifier + '.native.json'
        write('verification/' + identifier + '.rubric.json', {'schema': 1, 'task_id': identifier,
            'source_commit': REVISION, 'criteria': criteria,
            'comparison': 'Accept equivalent correct reasoning and implementations grounded in actual evidence; do not match wording, verbosity or a reference answer.'})
        tasks[identifier] = task

    scenes = []
    for identifier, title, goal, selected in [
        ('CT-S01', '本地配置文件的缓存与发布', '区分缓存命中、过期、发布和实际文件读取', ['CT-U01', 'CT-C01', 'CT-P01']),
        ('CT-S02', '商品价格的共享缓存与键', '先取真实证据再隔离业务缓存键', ['CT-D01', 'CT-C02', 'CT-U02']),
        ('CT-S03', '类入口的关键字实例绑定', '定位并独立修复调用绑定不一致', ['CT-D02', 'CT-M01']),
        ('CT-S04', '可变记录的缓存容量', '解释真实插入时记账与应用预算', ['CT-C03'])]:
        entries = [{'id': 'normal', 'task_ids': selected}]
        if identifier == 'CT-S02':
            entries.extend([{'id': 'diagnose_only', 'task_ids': ['CT-D01']},
                {'id': 'unavailable', 'task_ids': ['CT-D01'], 'materials': ['disclosure/unavailable.md']}])
        if identifier == 'CT-S03':
            entries.extend([{'id': 'diagnose_only', 'task_ids': ['CT-D02']},
                {'id': 'modify_direct', 'task_ids': ['CT-M01']}])
        scenes.append({'id': identifier, 'title': title, 'goal': goal, 'default_entry': 'normal',
            'entries': entries, 'tasks': [tasks[key] for key in selected]})
    shutil.copyfile(Path(__file__).with_name('cachetools-native-observe.py'), PROJECT / 'verification/native_observe.py')
    write('project.json', {'schema': 2, 'project_key': 'cachetools', 'title': 'Cachetools缓存工作场景',
        'category': '应用缓存与调用语义', 'description': '固定真实源码上的配置缓存、键诊断、类调用修复和容量咨询；四场景九项独立任务。',
        'seed_digest': snapshot_tree(PROJECT / 'seed')['digest'], 'environment': 'cachetools-py312',
        'source': {'repository': 'https://github.com/tkem/cachetools', 'commit': REVISION,
            'license_files': ['seed/library/LICENSE']}, 'scenarios': scenes})
    catalog = {'schema': 2, 'version': 'real-project-scenarios-hundred-stage-01-draft', 'projects': ['cachetools']}
    (WORKSPACE / 'drafts/catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'draft_project': 'cachetools', 'scenarios': len(scenes), 'tasks': len(tasks),
        'formal_catalog_modified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
