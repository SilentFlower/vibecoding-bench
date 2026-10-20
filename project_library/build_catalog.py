"""构建自包含项目基线与冻结业务路线；不调用模型或外部服务。"""
from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrator'))
from project_library import snapshot_tree
from topic_library import parse_topics
from reference_runtime import evaluate


# 每个初始项目有独立的业务核心；公共外壳只处理输入、输出和样例加载。
CORES = [
    ('text', 'characters', 'document', "return {'html': '\\n'.join('<p>'+html.escape(text)+'</p>' for text in labels)}"),
    ('routine', 'minutes', 'cycle', "return {'focus_minutes': sum(values[::2]), 'rest_minutes': sum(values[1::2]), 'cycles': (len(items)+1)//2}"),
    ('snippet', 'uses', 'shelf', "return {'snippets': [{'id': r['id'], 'preview': str(r.get(label,''))[:40]} for r in items]}"),
    ('filename', 'bytes', 'directory', "return {'plan': [{'before': name, 'after': 'renamed-'+name} for name in labels], 'collisions': sorted(k for k,v in Counter(labels).items() if v>1)}"),
    ('alias', 'invocations', 'shell', "return {'aliases': dict(zip(labels, [r.get('command','echo demo') for r in items])), 'duplicates': sorted(k for k,v in Counter(labels).items() if v>1)}"),
    ('subject', 'changes', 'release', "return {'releases': {key: [r[label] for r in items if r.get(group)==key] for key in sorted(set(groups))}}"),
    ('document', 'bytes', 'format', "return {'json': json.dumps([{label:r.get(label), metric:r.get(metric)} for r in items],ensure_ascii=False,sort_keys=True), 'records': len(items)}"),
    ('command', 'executions', 'project', "return {'frequencies': dict(sorted(Counter(labels).items())), 'unique': len(set(labels))}"),
    ('exercise', 'seconds', 'lesson', "return {'accuracy': [round(sum(a==b for a,b in zip(r.get('expected','abc'),r.get('typed','abc')))/max(1,len(r.get('expected','abc'))),6) for r in items]}"),
    ('recipe', 'steps', 'collection', "return {'recipes': [{'name':r.get(label), 'commands':r.get('command','echo demo').split(';')} for r in items]}"),
    ('task', 'priority', 'list', "return {'open': sum(s!='done' for s in states), 'completed': sum(s=='done' for s in states), 'completion': round(states.count('done')/len(states),6) if states else 0}"),
    ('task', 'minutes', 'board', "return {'remaining_focus_blocks': sum(math.ceil(v/25) for r,v in zip(items,values) if r.get(state)!='done')}"),
    ('update', 'blockers', 'person', "return {'standups': {key:{'updates':sum(g==key for g in groups),'blocked':sum(r.get(group)==key and r.get(state)=='blocked' for r in items)} for key in sorted(set(groups))}}"),
    ('habit', 'checkins', 'routine', "return {'days': dict(sorted(Counter(days).items())), 'active_days':len(set(days))}"),
    ('note', 'revision', 'notebook', "return {'notes':[{'id':r['id'],'words':len(re.findall(r'\\w+',str(r.get(label,'')))),'characters':len(str(r.get(label,'')))} for r in items]}"),
    ('card', 'interval_days', 'deck', "return {'next_reviews':[{'id':r['id'],'date':(date.fromisoformat(r[day])+timedelta(days=max(1,int(r.get(metric,1))))).isoformat()} for r in items]}"),
    ('transaction', 'amount', 'account', "return {'balance':round(sum((-v if r.get(state)=='done' else v) for r,v in zip(items,values)),2)}"),
    ('event', 'duration', 'calendar', "return {'conflicts':[[a['id'],b['id']] for i,a in enumerate(items) for b in items[i+1:] if a.get(group)==b.get(group) and max(a['start'],b['start'])<min(a['end'],b['end'])]}"),
    ('idea', 'score', 'collection', "return {'keywords':dict(Counter(w.casefold() for text in labels for w in re.findall(r'\\w+',text)).most_common(5))}"),
    ('book', 'pages_read', 'shelf', "return {'progress':[{'id':r['id'],'percent':round(100*r.get(metric,0)/max(1,r.get('target',100)),2)} for r in items]}"),
    ('passage', 'position', 'document', "return {'passages':[{'id':r['id'],'sentences':len([s for s in re.split(r'[.!?]+',str(r.get(label,''))) if s.strip()])} for r in items]}"),
    ('heading', 'level', 'article', "return {'outline':[{'level':max(1,min(6,int(v))),'text':text} for text,v in zip(labels,values)]}"),
    ('action_item', 'effort', 'meeting', "return {'actions':[{'task':r.get(label),'owner':r.get(group),'due':r.get(day)} for r in items if r.get(state)!='done']}"),
    ('requirement', 'weight', 'role', "return {'matched_weight':sum(v for r,v in zip(items,values) if r.get(state)=='done'),'total_weight':sum(values)}"),
    ('template', 'replies', 'mailbox', "return {'replies':[r.get('command','Hello {name}').replace('{name}',str(r.get(label,''))) for r in items]}"),
    ('term', 'difficulty', 'language', "return {'cards':[{'front':r.get(label),'back':r.get(group),'difficulty':r.get(metric)} for r in items]}"),
    ('caption', 'length', 'album', "return {'captions':[{'text':html.escape(text),'length':len(text),'needs_shortening':len(text)>40} for text in labels]}"),
    ('prompt', 'minutes', 'session', "return {'schedule':[{'prompt':r.get(label),'seconds':int(r.get(metric,0)*60)} for r in items],'total_minutes':sum(values)}"),
    ('check', 'severity', 'change', "return {'ready':all(s=='done' for s in states),'remaining':[r['id'] for r in items if r.get(state)!='done']}"),
    ('segment', 'width', 'language', "return {'columns':{key:[r.get(label) for r in items if r.get(group)==key] for key in sorted(set(groups))}}"),
    ('commit', 'lines', 'repository', "return {'repositories':{key:sum(v for g,v in zip(groups,values) if g==key) for key in sorted(set(groups))},'commits':len(items)}"),
    ('symbol', 'price', 'market', "return {'changes':[{'symbol':r.get(label),'delta':round(r.get(metric,0)-r.get('previous',0),2)} for r in items]}"),
    ('location', 'temperature', 'region', "return {'stations':[{'name':r.get(label),'celsius':r.get(metric),'fahrenheit':round(r.get(metric,0)*9/5+32,2)} for r in items]}"),
    ('device', 'watts', 'room', "return {'power_watts':sum(v for r,v in zip(items,values) if r.get(state)=='open'),'devices':dict(Counter(states))}"),
    ('build', 'seconds', 'pipeline', "return {'p50_seconds':statistics.median(values) if values else None,'slowest':max(values) if values else None,'runs':len(items)}"),
    ('purchase', 'amount', 'category', "return {'flows':[{'from':'budget','to':key,'value':sum(v for g,v in zip(groups,values) if g==key)} for key in sorted(set(groups))]}"),
    ('work_item', 'lead_days', 'team', "return {'throughput':states.count('done'),'mean_lead_days':round(statistics.mean(values),6) if values else None}"),
    ('reading', 'pages', 'book', "return {'pages_per_minute':[{'id':r['id'],'pace':round(r.get(metric,0)/max(1,r.get('duration',1)),6)} for r in items]}"),
    ('paper', 'citations', 'collection', "return {'nodes':[{'id':r['id'],'label':r.get(label)} for r in items],'edges':[[parent,r['id']] for r in items for parent in r.get('depends_on',[])]}"),
    ('headline', 'mentions', 'topic', "return {'topics':{key:sum(v for g,v in zip(groups,values) if g==key) for key in sorted(set(groups))},'articles':len(items)}"),
    ('customer', 'value', 'stage', "return {'pipeline_value':sum(v for r,v in zip(items,values) if r.get(state)!='done'),'customers':len(set(labels))}"),
    ('sku', 'quantity', 'warehouse', "return {'reorder':[{'sku':r.get(label),'shortage':max(0,r.get('target',10)-r.get(metric,0))} for r in items if r.get(metric,0)<r.get('target',10)]}"),
    ('line_item', 'quantity', 'quotation', "return {'lines':[{'item':r.get(label),'subtotal':round(r.get(metric,0)*r.get('unit_price',1),2)} for r in items],'total':round(sum(r.get(metric,0)*r.get('unit_price',1) for r in items),2)}"),
    ('ticket', 'hours', 'queue', "return {'backlog_hours':sum(v for r,v in zip(items,values) if r.get(state)!='done'),'blocked_ids':[r['id'] for r in items if r.get(state)=='blocked']}"),
    ('subscription', 'monthly_fee', 'plan', "return {'mrr':sum(v for r,v in zip(items,values) if r.get(state)!='blocked'),'arr':12*sum(v for r,v in zip(items,values) if r.get(state)!='blocked')}"),
    ('post', 'minutes', 'channel', "return {'calendar':{key:[r.get(label) for r in items if r.get(day)==key] for key in sorted(set(days))}}"),
    ('expense', 'amount', 'event', "return {'event_spend':{key:sum(v for g,v in zip(groups,values) if g==key) for key in sorted(set(groups))},'total_spend':sum(values)}"),
    ('question', 'uses', 'category', "return {'answers':[{'question':r.get(label),'answer':r.get('command','Demo answer'),'category':r.get(group)} for r in items]}"),
    ('answer', 'rating', 'question', "return {'responses':len(items),'average_rating':round(statistics.mean(values),6) if values else None,'distribution':dict(sorted(Counter(str(v) for v in values).items()))}"),
    ('employee', 'hours', 'shift', "return {'hours_by_employee':{key:sum(v for text,v in zip(labels,values) if text==key) for key in sorted(set(labels))}}"),
    ('source', 'confidence', 'study', "return {'review_order':[r['id'] for r in sorted(items,key=lambda r:(r.get(metric,0),r['id']))],'unreviewed':sum(s!='done' for s in states)}"),
    ('module', 'files', 'layer', "return {'layers':{key:[r.get(label) for r in items if r.get(group)==key] for key in sorted(set(groups))},'file_total':sum(values)}"),
    ('failure', 'occurrences', 'suite', "return {'priority':[{'id':r['id'],'score':r.get(metric,0)*r.get('weight',1)} for r in sorted(items,key=lambda r:-r.get(metric,0)*r.get('weight',1))]}"),
    ('message', 'priority', 'inbox', "return {'routes':[{'id':r['id'],'queue':r.get(group),'urgent':r.get(metric,0)>=10} for r in items]}"),
    ('supplier', 'price', 'item', "return {'best_quotes':{key:min((r for r in items if r.get(group)==key),key=lambda r:r.get(metric,0))['id'] for key in sorted(set(groups))}}"),
    ('appointment', 'minutes', 'resource', "return {'available':all(a['end']<=b['start'] or b['end']<=a['start'] or a.get(group)!=b.get(group) for i,a in enumerate(items) for b in items[i+1:])}"),
    ('page', 'revision', 'collection', "return {'snapshots':[{'id':r['id'],'checksum':hashlib.sha256(str(r.get(label,'')).encode()).hexdigest()} for r in items]}"),
    ('log_entry', 'severity', 'service', "return {'playbook':[{'id':r['id'],'action':'inspect' if r.get(metric,0)>10 else 'observe'} for r in items]}"),
    ('row', 'errors', 'source', "return {'cleaned':[{**r,label:' '.join(str(r.get(label,'')).split())} for r in items],'flagged':[r['id'] for r in items if r.get(metric,0)>0]}"),
    ('course', 'hours', 'track', "return {'tracks':{key:sum(v for g,v in zip(groups,values) if g==key) for key in sorted(set(groups))},'required_hours':sum(values)}"),
    ('container', 'capacity', 'room', "return {'labels':[str(r.get(group,''))+' / '+str(r.get(label,'')) for r in items],'total_capacity':sum(values)}"),
    ('ingredient', 'grams', 'recipe', "return {'double_batch':[{'ingredient':r.get(label),'grams':2*r.get(metric,0)} for r in items]}"),
    ('packing_item', 'grams', 'bag', "return {'packed_weight':sum(v for r,v in zip(items,values) if r.get(state)=='done'),'remaining':[r.get(label) for r in items if r.get(state)!='done']}"),
    ('keepsake', 'year', 'album', "return {'chronology':[r.get(label) for r in sorted(items,key=lambda r:(r.get(day,''),r['id']))],'albums':len(set(groups))}"),
    ('stationery', 'quantity', 'collection', "return {'restock':[r.get(label) for r in items if r.get(metric,0)<5],'total_units':sum(values)}"),
    ('block', 'height', 'page', "return {'layout':[{'id':r['id'],'y':sum(values[:i]),'height':r.get(metric,0)} for i,r in enumerate(items)],'height':sum(values)}"),
    ('receipt', 'amount', 'merchant', "return {'merchants':len(set(groups)),'receipt_total':round(sum(values),2),'receipt_count':len(items)}"),
    ('event', 'attendance', 'neighborhood', "return {'events_by_day':dict(sorted(Counter(days).items())),'attendance_total':sum(values)}"),
    ('material', 'quantity', 'craft', "return {'available':[{'material':r.get(label),'remaining':max(0,r.get(metric,0)-r.get('target',0))} for r in items]}"),
    ('reference', 'uses', 'project', "return {'cards':[{'heading':r.get(label),'project':r.get(group),'tags':sorted(set(r.get('tags',[])))} for r in items]}"),
    ('procedure', 'revision', 'department', "return {'published':[r.get(label) for r in items if r.get(state)=='done'],'drafts':sum(s!='done' for s in states)}"),
    ('onboarding_task', 'minutes', 'role', "return {'completion_by_role':{key:round(sum(r.get(state)=='done' for r in items if r.get(group)==key)/sum(g==key for g in groups),6) for key in sorted(set(groups))}}"),
    ('term', 'references', 'domain', "return {'glossary':dict(sorted((str(r.get(label,'')).casefold(),r.get('command','Definition')) for r in items))}"),
    ('booking', 'minutes', 'room', "return {'room_minutes':{key:sum(r['end']-r['start'] for r in items if r.get(group)==key) for key in sorted(set(groups))}}"),
    ('question', 'votes', 'team', "return {'unanswered':[r.get(label) for r in items if r.get(state)!='done'],'most_helpful':max(items,key=lambda r:r.get(metric,0))['id'] if items else None}"),
    ('handover_item', 'priority', 'customer', "return {'handover_ready':{key:all(r.get(state)=='done' for r in items if r.get(group)==key) for key in sorted(set(groups))}}"),
    ('retrospective', 'score', 'team', "return {'team_scores':{key:round(statistics.mean(v for g,v in zip(groups,values) if g==key),6) for key in sorted(set(groups))}}"),
    ('participant', 'seats', 'course', "return {'registered_seats':{key:sum(v for g,v in zip(groups,values) if g==key) for key in sorted(set(groups))},'waitlist':[r['id'] for r in items if r.get(state)=='blocked']}"),
    ('equipment', 'days', 'borrower', "return {'checked_out':[r.get(label) for r in items if r.get(state)=='open'],'loan_days':sum(v for r,v in zip(items,values) if r.get(state)=='open')}"),
    ('objective', 'progress', 'team', "return {'weighted_progress':round(sum(v*r.get('weight',1) for r,v in zip(items,values))/max(1,sum(r.get('weight',1) for r in items)),6)}"),
    ('source_field', 'position', 'dataset', "return {'mapping':{r.get(label):re.sub(r'[^a-z0-9]+','_',str(r.get(label,'')).casefold()).strip('_') for r in items}}"),
    ('check', 'failures', 'dataset', "return {'failed_checks':[r.get(label) for r in items if r.get(metric,0)>0],'failure_count':sum(values)}"),
    ('customer_name', 'orders', 'source', "return {'duplicate_names':sorted(key for key,count in Counter(text.strip().casefold() for text in labels).items() if count>1)}"),
    ('metric', 'version', 'owner', "return {'definitions':[{'metric':r.get(label),'version':int(r.get(metric,0)),'owner':r.get(group)} for r in items]}"),
    ('funnel_stage', 'visitors', 'campaign', "return {'conversion':[round(values[i]/values[i-1],6) if values[i-1] else None for i in range(1,len(values))]}"),
    ('variant', 'conversions', 'experiment', "return {'rates':[{'variant':r.get(label),'rate':round(r.get(metric,0)/max(1,r.get('target',100)),6)} for r in items]}"),
    ('import_error', 'line', 'file', "return {'error_lines':sorted(set(values)),'by_file':dict(sorted(Counter(groups).items()))}"),
    ('touchpoint', 'revenue', 'channel', "return {'attributed':{key:round(sum(v for g,v in zip(groups,values) if g==key),2) for key in sorted(set(groups))}}"),
    ('cohort', 'retained', 'period', "return {'retention':[{'cohort':r.get(label),'retained_rate':round(r.get(metric,0)/max(1,r.get('target',100)),6)} for r in items]}"),
    ('order', 'amount', 'exception', "return {'exception_value':sum(v for r,v in zip(items,values) if r.get(state)=='blocked'),'review_queue':[r['id'] for r in items if r.get(state)=='blocked']}"),
    ('topic', 'priority', 'channel', "return {'next_topics':[r.get(label) for r in sorted(items,key=lambda r:(-r.get(metric,0),r['id'])) if r.get(state)!='done']}"),
    ('content', 'views', 'channel', "return {'engagement':[{'id':r['id'],'per_minute':round(r.get(metric,0)/max(1,r.get('duration',1)),6)} for r in items]}"),
    ('sponsor', 'fee', 'campaign', "return {'contracted':sum(v for r,v in zip(items,values) if r.get(state)=='done'),'potential':sum(values)}"),
    ('event', 'capacity', 'community', "return {'upcoming':sorted([{'event':r.get(label),'date':r.get(day),'capacity':r.get(metric)} for r in items],key=lambda r:r['date'])}"),
    ('question', 'votes', 'topic', "return {'answer_order':[r['id'] for r in sorted(items,key=lambda r:(-r.get(metric,0),r['id']))],'topics':dict(Counter(groups))}"),
    ('ebook', 'copies', 'edition', "return {'sales':[{'ebook':r.get(label),'revenue':round(r.get(metric,0)*r.get('unit_price',1),2)} for r in items]}"),
    ('chapter', 'minutes', 'course', "return {'published_minutes':sum(v for r,v in zip(items,values) if r.get(state)=='done'),'chapters_left':sum(s!='done' for s in states)}"),
    ('cue', 'seconds', 'broadcast', "return {'cues':[{'name':r.get(label),'at_second':sum(values[:i])} for i,r in enumerate(items)],'total_seconds':sum(values)}"),
    ('content', 'tier', 'membership', "return {'access':[{'id':r['id'],'tiers':list(range(1,max(1,int(r.get(metric,1)))+1))} for r in items]}"),
    ('segment', 'minutes', 'episode', "return {'episodes':{key:sum(v for g,v in zip(groups,values) if g==key) for key in sorted(set(groups))},'longest_segment':max(values) if values else 0}"),
]

FAMILIES = [
    ('Command-Line Tools', ['rename','sequence','regex','glob','extensions','paths','search','sort','deduplicate','required','template','replace','diff','word_count','group','csv','compare','digest','roundtrip','uniqueness']),
    ('Personal Productivity Web Apps', ['filter','search','sort','page','group','window','timeline','streak','missing_dates','totals','tags','tag_filter','budget','ratio','transitions','conflicts','csv','compare','roundtrip','digest']),
    ('Writing and Document Workbenches', ['word_count','headings','links','terms','search','replace','template','slug','normalize','deduplicate','group','tags','tag_filter','required','sort','diff','html','markdown','roundtrip','digest']),
    ('Data Visualization and Dashboard', ['average','median','rank','sort','group','totals','histogram','timeline','window','cumulative','moving','forecast','percentages','ratio','outliers','matrix','filter','csv','compare','digest']),
    ('Business and Operational Tools', ['filter','search','sort','required','totals','budget','ratio','weighted','group','capacity','transitions','eligibility','timeline','window','rank','percentages','csv','compare','roundtrip','digest']),
    ('Rule-Based Workflow Workbenches', ['required','errors','uniqueness','deduplicate','duplicates','merge','mapping','normalize','filter','search','sort','transitions','dependencies','eligibility','coverage','conflicts','matrix','csv','compare','digest']),
    ('Organization and Recordkeeping Tools', ['search','filter','tags','tag_filter','sort','group','totals','page','required','duplicates','merge','template','html','markdown','timeline','window','csv','compare','roundtrip','digest']),
    ('Team Knowledge and Internal Tools', ['search','filter','required','group','tags','tag_filter','sort','coverage','dependencies','transitions','capacity','conflicts','eligibility','timeline','window','matrix','csv','compare','roundtrip','digest']),
    ('Data Operations and Quality Governance', ['required','errors','uniqueness','normalize','mapping','duplicates','merge','deduplicate','filter','range','sort','group','totals','average','histogram','outliers','matrix','csv','compare','digest']),
    ('Creator Business and Community Operations', ['search','filter','sort','rank','tags','tag_filter','group','totals','budget','ratio','percentages','timeline','window','capacity','eligibility','transitions','csv','compare','roundtrip','digest']),
]

TITLES = {
    'render_documents':'按 Markdown 标题和段落导出文档','focus_schedule':'生成连续专注与休息时段',
    'focus_remaining':'按已用时间计算剩余专注时长','snippet_expand':'展开片段中的参数占位符',
    'changelog':'按发布版本生成变更记录','convert_records':'在 JSON 与逐行 JSON 间转换',
    'history_favorites':'按真实出现次数整理常用命令','typing_metrics':'计算输入准确率和每分钟词数',
    'recipe_steps':'拆分命令配方并保留步骤顺序','stock_shortages':'计算库存补货缺口',
    'quotation_tax':'计算报价折扣、税额与含税总价',
    'filter':'按业务状态筛选','range':'按数值区间筛选','search':'不区分大小写检索','sort':'稳定排序',
    'group':'按业务分组计数','totals':'分组累计','deduplicate':'保序去重','required':'必填项诊断',
    'page':'分页与总数','select':'选择导出字段','csv':'标准 CSV 导出','roundtrip':'JSON 往返一致性',
    'rank':'排名与同值顺序','average':'均值与极值','histogram':'数值分桶','timeline':'日期与同日顺序',
    'window':'日期窗口筛选','cumulative':'逐期累计','weighted':'加权指标','median':'中位数',
    'normalize':'空白规范化','mapping':'字段映射','duplicates':'重复记录预览','merge':'去重合并并保留标签',
    'tags':'标签统计','tag_filter':'组合标签筛选','transitions':'状态转换准入','conflicts':'资源时间冲突',
    'missing_dates':'缺失日期检查','streak':'连续日期统计','moving':'滚动均值','ratio':'目标完成比例',
    'budget':'预算余量','forecast':'简单趋势外推','percentages':'占比统计','outliers':'中位数偏差检查',
    'compare':'前后版本差异','digest':'规范内容摘要','markdown':'Markdown 清单导出','html':'转义后的 HTML 导出',
    'word_count':'逐条词数统计','headings':'Markdown 标题提取','links':'文档引用提取','replace':'局部文本替换',
    'template':'模板占位符填充','diff':'逐行文本差异','terms':'词频索引','slug':'稳定短标识',
    'glob':'名称模式选择','extensions':'扩展名归类','rename':'前后缀命名预览','sequence':'编号命名预览',
    'regex':'捕获替换与非法模式拒绝','paths':'相对路径越界诊断','capacity':'容量超额检查',
    'dependencies':'依赖拓扑与环检查','eligibility':'业务阈值准入','coverage':'必需分组覆盖','matrix':'分组状态矩阵',
    'errors':'负值记录定位','uniqueness':'业务 ID 唯一性检查',
}

# 工具项目按自身业务安排路线，避免对计时器或文档套用文件重命名步骤。
ROUTE_OVERRIDES = {
    1:['render_documents','headings','links','word_count','terms','normalize','replace','template','search','group','tags','tag_filter','sort','html','markdown','required','deduplicate','compare','roundtrip','digest'],
    2:['focus_schedule','focus_remaining','filter','totals','group','average','timeline','window','cumulative','moving','streak','missing_dates','budget','capacity','ratio','percentages','rank','csv','roundtrip','digest'],
    3:['snippet_expand','search','filter','tags','tag_filter','sort','page','deduplicate','duplicates','merge','template','replace','group','rank','timeline','window','csv','compare','roundtrip','digest'],
    5:['required','uniqueness','search','group','sort','filter','template','replace','duplicates','dependencies','coverage','mapping','normalize','tags','tag_filter','markdown','csv','compare','roundtrip','digest'],
    6:['changelog','group','filter','timeline','window','search','sort','template','markdown','html','word_count','terms','duplicates','deduplicate','tags','tag_filter','csv','compare','roundtrip','digest'],
    7:['convert_records','required','mapping','normalize','select','csv','roundtrip','errors','uniqueness','duplicates','deduplicate','merge','filter','range','sort','group','matrix','compare','html','digest'],
    8:['history_favorites','search','filter','group','timeline','window','rank','totals','sort','deduplicate','duplicates','tags','tag_filter','terms','page','csv','markdown','compare','roundtrip','digest'],
    9:['typing_metrics','average','median','rank','sort','group','timeline','window','moving','streak','missing_dates','ratio','histogram','outliers','percentages','filter','csv','compare','roundtrip','digest'],
    10:['recipe_steps','search','filter','group','tags','tag_filter','sort','page','template','required','duplicates','deduplicate','dependencies','coverage','markdown','html','csv','compare','roundtrip','digest'],
    137:['stock_shortages','filter','search','sort','required','totals','capacity','group','timeline','window','rank','average','histogram','errors','uniqueness','mapping','csv','compare','roundtrip','digest'],
    138:['quotation_tax','filter','search','sort','required','totals','budget','ratio','weighted','group','capacity','transitions','eligibility','timeline','window','rank','csv','compare','roundtrip','digest'],
}

HEADER = '''"""{title} 的可运行初始版本，样例均为合成数据。"""
import hashlib
import html
import json
import math
import re
import statistics
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

FIELDS = {fields!r}


def baseline(items):
    """计算初始业务结果。@param items 业务记录。@return 初始结果。"""
    label, metric, group = FIELDS['label'], FIELDS['metric'], FIELDS['group']
    state, day = FIELDS['state'], FIELDS['date']
    labels = [str(r.get(label, '')) for r in items]
    values = [r.get(metric, 0) for r in items]
    groups = [str(r.get(group, '')) for r in items]
    states = [r.get(state) for r in items]
    days = [r.get(day, '') for r in items]
    {body}


def handle(request):
    """处理一条本地 JSON 业务请求。@param request 输入对象。@return 业务结果。"""
    if not isinstance(request, dict):
        return {{'error': 'invalid_request'}}
    if request.get('action', 'overview') == 'overview':
        return baseline(request.get('items', json.loads(Path(__file__).with_name('demo.json').read_text())))
    return {{'error': 'unsupported_action'}}


if __name__ == '__main__':
    for line in sys.stdin:
        if line.strip():
            try:
                response = handle(json.loads(line))
                print(json.dumps(response, ensure_ascii=False, allow_nan=False))
            except (ValueError, KeyError, TypeError) as error:
                print(json.dumps({{'error': type(error).__name__}}))
'''


def build_catalog() -> dict:
    """写入完整项目源码、合成样例和冻结路线。

    :return: 项目和步骤数量摘要。
    """
    root = Path(__file__).resolve().parent
    topics = parse_topics(root.parent / 'topics.md')
    selected = [(i, family, operations) for family, operations in FAMILIES
        for i in [t for t in topics if t.category == family][:10]]
    if len(selected) != 100 or len(CORES) != 100:
        raise ValueError('首版项目定义必须恰好 100 项')
    keys = []
    for number, ((topic, family, operations), core) in enumerate(zip(selected, CORES), 1):
        operations = ROUTE_OVERRIDES.get(topic.no,operations)
        key = f'project-{number:03d}'
        keys.append(key)
        label, metric, group, body = core
        fields = {'label':label, 'metric':metric, 'group':group, 'state':'status', 'date':'date'}
        names = [f'{label} Alpha', f'{label} Beta', f'{label} Gamma', f'{label} Alpha', f'{label} Delta', f'{label} Epsilon']
        if label == 'filename':
            names = ['report.txt','notes.md','chart.csv','report.txt','draft.md','archive.json']
        if label in ('text','note','passage','heading','segment'):
            names = ['# Alpha\nSynthetic example.', 'Beta [link](alpha.md)', 'Gamma words here', '# Alpha\nSynthetic example.', '<draft> & review', 'Epsilon']
        rows = [{'id':n+1, label:names[n], metric:[12,5,9,0,21,4][n], group:['A','B','A','B','C','A'][n],
            'status':['open','done','open','blocked','done','open'][n], 'date':['2026-01-03','2026-01-01','2026-01-02','2026-01-03','2026-01-06','2026-01-07'][n],
            'tags':[['demo','alpha'],['demo'],['beta'],['extra'],[],['alpha']][n], 'synthetic':True,
            'weight':[1,2,1,1,3,1][n], 'target':20, 'unit_price':2.5, 'previous':3,
            'start':[0,15,5,30,40,45][n], 'end':[10,25,12,40,50,60][n], 'duration':5,
            'depends_on':[] if n==0 else [n], 'command':'echo demo; echo complete',
            'expected':'hello', 'typed':'hallo'} for n in range(6)]
        destination = root / 'projects' / key
        seed = destination / 'seed'
        verification = destination / 'verification'
        seed.mkdir(parents=True, exist_ok=True)
        verification.mkdir(parents=True, exist_ok=True)
        app = HEADER.format(title=topic.title, fields=fields, body=body)
        (seed/'app.py').write_text(app)
        (seed/'demo.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        (seed/'README.md').write_text(f'# {topic.title}\n\n这是可运行的初始版本，样例均为合成数据。\n\n运行：`python3 app.py`，每行输入一个 JSON 请求，每行输出一个 JSON 结果。\n\n初始请求：`{{"action":"overview"}}`。后续迭代在此代码和数据上继续。\n')
        baseline = []
        for data in (rows, []):
            request = {'action':'overview', 'items':data}
            result = subprocess.run([sys.executable,str(seed/'app.py')],input=json.dumps(request)+'\n',
                text=True,capture_output=True,timeout=5,check=True)
            baseline.append({'input':request,'expected':json.loads(result.stdout)})
        steps, reference = [], {}
        # 同领域使用不同的业务核心与字段；算法原语复用，不向模型提供参考答案源码。
        for index, operator in enumerate(operations,1):
            action = f'{label}_{operator}'
            options = {'value':'open','min':5,'max':15,'query':'alpha','descending':bool(number%2),
                'offset':1,'limit':2,'width':10,'start':'2026-01-02','end':'2026-01-06',
                'mapping':{label:'name',metric:'value'},'tags':['demo'],'allowed':{'open':['done'],'blocked':['open']},
                'target':'done','threshold':8,'budget':30,'prefix':'v2-','suffix':'.new',
                'pattern':'*a*','replacement':'result','old':'Alpha','new':'Reviewed','capacity':15,
                'minimum':5,'excluded':['blocked'],'required':['A','B','D'],'template':'{id}: {'+label+'}',
                'before':rows[:2], 'after':'new line\ncommon'}
            if operator == 'sequence':
                options['start'], options['width'] = 4, 3
            if operator == 'moving':
                options['width'] = 2
            if operator == 'diff':
                options['before'] = 'old line\ncommon'
            if operator == 'regex':
                options['pattern'], options['replacement'] = r'(Alpha|Beta)',r'checked-\1'
            cases = []
            variation = deepcopy(rows)
            variation[0][metric] += 7
            variation[1][label] = '  Synthetic ALPHA changed  '
            variation[2]['tags'] = ['new','demo']
            variation[-1]['depends_on'] = [999]
            variant_options = deepcopy(options)
            # 诊断类步骤必须同时覆盖真实问题，不能只验收空的错误列表。
            if operator == 'required':
                variation[0].pop(label)
                variation[1][group] = '  '
            elif operator == 'errors':
                variation[0][metric] = -7
            elif operator == 'uniqueness':
                variation[1]['id'] = variation[0]['id']
            elif operator == 'paths':
                variation[0][label] = '../outside.txt'
            elif operator == 'regex':
                variant_options['pattern'] = '['
            elif operator == 'snippet_expand':
                variation[1][label] = 'Hello {name} {missing}'
            elif operator == 'focus_schedule':
                variant_options.update(cycles=3,focus_minutes=10,rest_minutes=2)
            elif operator == 'quotation_tax':
                variant_options.update(discount=0.1,tax_rate=0.2)
            elif operator == 'typing_metrics':
                variation[0].update(expected='hello world',typed='hello',duration=0)
            elif operator == 'diff':
                variant_options.update(before='old line\nremove',after='added\nnew line')
            for data,case_options in ((rows,options),([],options),(variation,variant_options)):
                request = {'action':action,'items':data,'options':case_options}
                cases.append({'input':request,'expected':evaluate(operator,request,fields)})
            step_id = f'step-{index:02d}'
            contract = {'action':action,'fields':fields,'options':options}
            goal = f'为 {topic.title} 增加{TITLES[operator]}，处理领域字段 {label}、{metric}、{group}。保留已有能力，空数据须有确定结果。接口契约：'+json.dumps(contract,ensure_ascii=False)
            steps.append({'id':step_id,'goal':goal,'milestone':f'phase-{(index-1)//5+1}',
                'requires':[] if index==1 else [f'step-{index-1:02d}'],'checks':cases})
            reference[action] = operator
        manifest = {'schema':1,'project_key':key,'title':topic.title,'category':family,'source_topic_no':topic.no,
            'description':f'围绕 {topic.title} 的本地业务工作台，具有可运行的初始核心和分阶段改进路线。',
            'entrypoint':['python3','app.py'],'seed_digest':snapshot_tree(seed)['digest'],'baseline_checks':baseline,
            'milestones':[{'id':f'phase-{n}','title':title} for n,title in enumerate(('基础查询与业务操作','组合工作流','边界与数据处理','交付与可核对结果'),1)],
            'steps':steps}
        (destination/'project.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        (verification/'reference.json').write_text(json.dumps({'fields':fields,'actions':reference},ensure_ascii=False,indent=2)+'\n')
    (root/'catalog.json').write_text(json.dumps({'schema':1,'version':'2026.10.1','projects':keys},ensure_ascii=False,indent=2)+'\n')
    return {'projects':len(keys),'steps':sum(len(ROUTE_OVERRIDES.get(topic.no,ops)) for topic,_,ops in selected)}


if __name__ == '__main__':
    print(json.dumps(build_catalog(),ensure_ascii=False))
