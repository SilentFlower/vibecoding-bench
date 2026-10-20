"""内置内容的参考行为，仅供控制端离线核验，不复制到模型工作目录。"""
from __future__ import annotations

import csv
import difflib
import fnmatch
import hashlib
import html
import io
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import PurePosixPath


def evaluate(operator: str, request: dict, fields: dict) -> object:
    """计算固定业务用例的参考结果。

    :param operator: 内容作者定义的算法原语。
    :param request: 合成业务输入。
    :param fields: 当前项目的领域字段映射。
    :return: 冻结验收所需的 JSON 值。
    """
    items = request.get('items', [])
    label, metric, group = fields['label'], fields['metric'], fields['group']
    state, day = fields['state'], fields['date']
    option = request.get('options', {})
    if operator == 'render_documents':
        documents = []
        for row in items:
            parts = []
            for line in str(row.get(label, '')).splitlines():
                heading = re.match(r'^(#{1,6})\s+(.+)$', line)
                if heading:
                    level = len(heading.group(1))
                    parts.append(f'<h{level}>'+html.escape(heading.group(2))+f'</h{level}>')
                elif line.strip():
                    parts.append('<p>'+html.escape(line)+'</p>')
            documents.append({'id':row['id'],'html':'\n'.join(parts)})
        return documents
    if operator == 'focus_schedule':
        count = option.get('cycles',2)
        focus,rest = option.get('focus_minutes',25),option.get('rest_minutes',5)
        result,current = [],0
        for index in range(count):
            result.append({'cycle':index+1,'phase':'focus','start':current,'end':current+focus})
            current += focus
            if index+1<count:
                result.append({'cycle':index+1,'phase':'rest','start':current,'end':current+rest})
                current += rest
        return result
    if operator == 'focus_remaining':
        elapsed = option.get('elapsed_minutes',12)
        return [{'id':row['id'],'remaining':max(0,row.get(metric,0)-elapsed),
            'completed':elapsed>=row.get(metric,0)} for row in items]
    if operator == 'snippet_expand':
        values = option.get('values',{'name':'Demo'})
        return [{'id':row['id'],'text':re.sub(r'\{([A-Za-z_][A-Za-z0-9_]*)\}',
            lambda match:str(values.get(match.group(1),match.group(0))),str(row.get(label,'')))} for row in items]
    if operator == 'changelog':
        return '\n\n'.join('## '+key+'\n'+'\n'.join('- '+str(row.get(label,'')) for row in items if str(row.get(group,''))==key)
            for key in sorted({str(row.get(group,'')) for row in items}))
    if operator == 'convert_records':
        target = option.get('format','ndjson')
        if target=='json':
            return json.dumps(items,ensure_ascii=False,sort_keys=True)
        if target=='ndjson':
            return '\n'.join(json.dumps(row,ensure_ascii=False,sort_keys=True) for row in items)
        return {'error':'unsupported_format'}
    if operator == 'history_favorites':
        counts = Counter(str(row.get(label,'')) for row in items)
        return [{'command':command,'count':count} for command,count in sorted(counts.items(),key=lambda item:(-item[1],item[0]))[:option.get('limit',5)]]
    if operator == 'typing_metrics':
        result = []
        for row in items:
            expected,typed = row.get('expected',''),row.get('typed','')
            correct = sum(a==b for a,b in zip(expected,typed))
            duration = row.get('duration',0)
            result.append({'id':row['id'],'accuracy':round(correct/max(1,len(expected)),6),
                'words_per_minute':round(len(typed)/5*60/duration,6) if duration>0 else None})
        return result
    if operator == 'recipe_steps':
        return [{'id':row['id'],'steps':[text.strip() for text in str(row.get('command','')).split(';') if text.strip()]}
            for row in items]
    if operator == 'stock_shortages':
        return [{'id':row['id'],'shortage':max(0,row.get('target',0)-row.get(metric,0))}
            for row in items if row.get(metric,0)<row.get('target',0)]
    if operator == 'quotation_tax':
        subtotal = sum(row.get(metric,0)*row.get('unit_price',0) for row in items)
        net = round(subtotal*(1-option.get('discount',0)),2)
        tax = round(net*option.get('tax_rate',0.1),2)
        return {'subtotal':round(subtotal,2),'net':net,'tax':tax,'total':round(net+tax,2)}
    if operator == 'filter':
        return [row for row in items if row.get(state) == option.get('value')]
    if operator == 'range':
        return [row for row in items if option.get('min', 0) <= row.get(metric, 0) <= option.get('max', 10**9)]
    if operator == 'search':
        return [row for row in items if option.get('query', '').casefold() in str(row.get(label, '')).casefold()]
    if operator == 'sort':
        return sorted(items, key=lambda row: (row.get(metric, 0), row['id']), reverse=bool(option.get('descending')))
    if operator == 'group':
        return dict(sorted(Counter(str(row.get(group, '')) for row in items).items()))
    if operator == 'totals':
        result = defaultdict(float)
        for row in items:
            result[str(row.get(group, ''))] += row.get(metric, 0)
        return dict(sorted(result.items()))
    if operator == 'deduplicate':
        seen, result = set(), []
        for row in items:
            key = str(row.get(label, '')).strip().casefold()
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result
    if operator == 'required':
        return [{'id': row.get('id'), 'missing': [key for key in (label, group) if not str(row.get(key, '')).strip()]}
            for row in items if any(not str(row.get(key, '')).strip() for key in (label, group))]
    if operator == 'page':
        offset, limit = option.get('offset', 0), option.get('limit', 2)
        return {'items': items[offset:offset+limit], 'total': len(items)}
    if operator == 'select':
        return [{key: row.get(key) for key in option.get('fields', ['id', label])} for row in items]
    if operator == 'csv':
        output = io.StringIO(newline='')
        keys = ['id', label, metric, group]
        writer = csv.DictWriter(output, fieldnames=keys, lineterminator='\n', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(items)
        return output.getvalue()
    if operator == 'roundtrip':
        return {'items': json.loads(json.dumps(items, ensure_ascii=False)), 'count': len(items)}
    if operator == 'rank':
        ordered = sorted(items, key=lambda row: (-row.get(metric, 0), row['id']))
        return [{'id': row['id'], 'rank': index+1} for index, row in enumerate(ordered)]
    if operator == 'average':
        values = [row.get(metric, 0) for row in items]
        return {'count': len(values), 'average': round(sum(values)/len(values), 6) if values else None,
            'minimum': min(values) if values else None, 'maximum': max(values) if values else None}
    if operator == 'histogram':
        width = option.get('width', 10)
        if width <= 0:
            return {'error': 'invalid_width'}
        return dict(sorted(Counter(str(math.floor(row.get(metric, 0)/width)*width) for row in items).items()))
    if operator == 'timeline':
        return sorted(items, key=lambda row: (row.get(day, ''), row['id']))
    if operator == 'window':
        return [row for row in items if option.get('start', '') <= row.get(day, '') <= option.get('end', '9999')]
    if operator == 'cumulative':
        result, total = [], 0
        for row in sorted(items, key=lambda row: (row.get(day, ''), row['id'])):
            total += row.get(metric, 0)
            result.append({'id': row['id'], 'total': total})
        return result
    if operator == 'weighted':
        denominator = sum(row.get('weight', 1) for row in items)
        return round(sum(row.get(metric, 0)*row.get('weight', 1) for row in items)/denominator, 6) if denominator else None
    if operator == 'median':
        return statistics.median([row.get(metric, 0) for row in items]) if items else None
    if operator == 'normalize':
        return [{**row, label: ' '.join(str(row.get(label, '')).split())} for row in items]
    if operator == 'mapping':
        mapping = option.get('mapping', {})
        return [{mapping.get(key, key): value for key, value in row.items()} for row in items]
    if operator == 'duplicates':
        groups = defaultdict(list)
        for row in items:
            groups[str(row.get(label, '')).strip().casefold()].append(row['id'])
        return [ids for _, ids in sorted(groups.items()) if len(ids) > 1]
    if operator == 'merge':
        groups = {}
        for row in items:
            key = str(row.get(label, '')).strip().casefold()
            if key not in groups:
                groups[key] = dict(row, tags=list(row.get('tags', [])))
            else:
                groups[key]['tags'] = sorted(set(groups[key]['tags']) | set(row.get('tags', [])))
        return list(groups.values())
    if operator == 'tags':
        return dict(sorted(Counter(tag for row in items for tag in set(row.get('tags', []))).items()))
    if operator == 'tag_filter':
        required = set(option.get('tags', []))
        return [row for row in items if required.issubset(row.get('tags', []))]
    if operator == 'transitions':
        rules = option.get('allowed', {})
        target = option.get('target')
        return [{'id': row['id'], 'allowed': target in rules.get(row.get(state), [])} for row in items]
    if operator == 'conflicts':
        result = []
        for left in range(len(items)):
            for right in range(left+1, len(items)):
                a, b = items[left], items[right]
                if a.get(group) == b.get(group) and max(a.get('start', 0), b.get('start', 0)) < min(a.get('end', 0), b.get('end', 0)):
                    result.append([a['id'], b['id']])
        return result
    if operator == 'missing_dates':
        if not items:
            return []
        existing = {row[day] for row in items}
        start, end = date.fromisoformat(min(existing)), date.fromisoformat(max(existing))
        return [(start+timedelta(days=n)).isoformat() for n in range((end-start).days+1)
            if (start+timedelta(days=n)).isoformat() not in existing]
    if operator == 'streak':
        days = sorted({date.fromisoformat(row[day]) for row in items})
        best = current = 0
        previous = None
        for item in days:
            current = current+1 if previous is not None and item-previous == timedelta(days=1) else 1
            best = max(best, current)
            previous = item
        return {'longest': best, 'last': current}
    if operator == 'moving':
        width = option.get('width', 2)
        values = [row.get(metric, 0) for row in sorted(items, key=lambda row: (row[day], row['id']))]
        return [round(sum(values[max(0, n-width+1):n+1])/len(values[max(0, n-width+1):n+1]), 6) for n in range(len(values))]
    if operator == 'ratio':
        return [{'id': row['id'], 'ratio': round(row.get(metric, 0)/row.get('target', 1), 6)
            if row.get('target', 1) else None} for row in items]
    if operator == 'budget':
        total = sum(row.get(metric, 0) for row in items)
        return {'used': total, 'remaining': option.get('budget', 100)-total, 'over_budget': total > option.get('budget', 100)}
    if operator == 'forecast':
        values = [row.get(metric, 0) for row in sorted(items, key=lambda row: (row[day], row['id']))]
        return round(values[-1]+(values[-1]-values[0])/(len(values)-1), 6) if len(values)>1 else (values[0] if values else None)
    if operator == 'percentages':
        total = sum(row.get(metric, 0) for row in items)
        return [{'id': row['id'], 'percent': round(100*row.get(metric, 0)/total, 6) if total else 0} for row in items]
    if operator == 'outliers':
        values = [row.get(metric, 0) for row in items]
        middle = statistics.median(values) if values else 0
        threshold = option.get('threshold', 10)
        return [row['id'] for row in items if abs(row.get(metric, 0)-middle)>threshold]
    if operator == 'compare':
        before = {row['id']: row for row in option.get('before', [])}
        after = {row['id']: row for row in items}
        return {'added': sorted(after.keys()-before.keys()), 'removed': sorted(before.keys()-after.keys()),
            'changed': sorted(key for key in after.keys() & before.keys() if after[key] != before[key])}
    if operator == 'digest':
        payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        return {'sha256': hashlib.sha256(payload).hexdigest(), 'count': len(items)}
    if operator == 'markdown':
        return '\n'.join('- '+str(row.get(label, '')).replace('\n', ' ') for row in items)
    if operator == 'html':
        return '<ul>'+''.join('<li>'+html.escape(str(row.get(label, '')))+'</li>' for row in items)+'</ul>'
    if operator == 'word_count':
        return [{'id': row['id'], 'words': len(re.findall(r'\w+', str(row.get(label, ''))))} for row in items]
    if operator == 'headings':
        return [{'id': row['id'], 'headings': re.findall(r'^#{1,6}\s+(.+)$', str(row.get(label, '')), re.M)} for row in items]
    if operator == 'links':
        return [{'id': row['id'], 'targets': re.findall(r'\[[^\]]*\]\(([^)]+)\)', str(row.get(label, '')))} for row in items]
    if operator == 'replace':
        return [{**row, label: str(row.get(label, '')).replace(option.get('old', ''), option.get('new', ''))} for row in items]
    if operator == 'template':
        template = option.get('template', '{id}')
        return [re.sub(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', lambda match: str(row.get(match.group(1), '')), template) for row in items]
    if operator == 'diff':
        return list(difflib.unified_diff(option.get('before', '').splitlines(), option.get('after', '').splitlines(), lineterm=''))
    if operator == 'terms':
        return dict(sorted(Counter(word.casefold() for row in items for word in re.findall(r'\w+', str(row.get(label, '')))).items()))
    if operator == 'slug':
        return [{'id': row['id'], 'slug': re.sub(r'[^a-z0-9]+', '-', str(row.get(label, '')).casefold()).strip('-')} for row in items]
    if operator == 'glob':
        return [row for row in items if fnmatch.fnmatchcase(str(row.get(label, '')), option.get('pattern', '*'))]
    if operator == 'extensions':
        return dict(sorted(Counter(PurePosixPath(str(row.get(label, ''))).suffix.casefold() for row in items).items()))
    if operator == 'rename':
        return [{'id': row['id'], 'before': row.get(label, ''), 'after': option.get('prefix', '')+str(row.get(label, ''))+option.get('suffix', '')} for row in items]
    if operator == 'sequence':
        return [{'id': row['id'], 'after': str(n+option.get('start', 1)).zfill(option.get('width', 3))+'-'+str(row.get(label, ''))}
            for n, row in enumerate(sorted(items, key=lambda row: str(row.get(label, ''))))]
    if operator == 'regex':
        try:
            pattern = re.compile(option.get('pattern', ''))
        except re.error:
            return {'error': 'invalid_pattern'}
        return [{**row, label: pattern.sub(option.get('replacement', ''), str(row.get(label, '')))} for row in items]
    if operator == 'paths':
        return [{'id': row['id'], 'valid': not (PurePosixPath(str(row.get(label, ''))).is_absolute()
            or '..' in PurePosixPath(str(row.get(label, ''))).parts or '\\' in str(row.get(label, '')))} for row in items]
    if operator == 'capacity':
        result = defaultdict(float)
        for row in items:
            result[str(row.get(group, ''))] += row.get(metric, 0)
        return [{'group': key, 'used': value, 'exceeded': value > option.get('capacity', 10)} for key, value in sorted(result.items())]
    if operator == 'dependencies':
        graph = {str(row['id']): [str(v) for v in row.get('depends_on', [])] for row in items}
        order = []
        while len(order) < len(graph):
            ready = sorted(key for key, dependencies in graph.items() if key not in order and all(v in order for v in dependencies))
            if not ready:
                return {'error': 'dependency_cycle_or_missing'}
            order.extend(ready)
        return order
    if operator == 'eligibility':
        return [{'id': row['id'], 'eligible': row.get(metric, 0) >= option.get('minimum', 5)
            and row.get(state) not in option.get('excluded', [])} for row in items]
    if operator == 'coverage':
        values = {str(row.get(group, '')) for row in items}
        return {'present': sorted(values), 'missing': sorted(set(option.get('required', []))-values)}
    if operator == 'matrix':
        result = defaultdict(Counter)
        for row in items:
            result[str(row.get(group, ''))][str(row.get(state, ''))] += 1
        return {key: dict(sorted(value.items())) for key, value in sorted(result.items())}
    if operator == 'errors':
        return [{'id': row.get('id'), 'error': 'negative_value'} for row in items if row.get(metric, 0)<0]
    if operator == 'uniqueness':
        seen, errors = set(), []
        for row in items:
            if row['id'] in seen:
                errors.append(row['id'])
            seen.add(row['id'])
        return sorted(set(errors))
    raise ValueError('未知参考业务原语：'+operator)
