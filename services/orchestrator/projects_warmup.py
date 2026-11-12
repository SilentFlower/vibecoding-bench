"""将旧题库养号的配置保留到独立工程养号空间，不迁移问答执行或通过证明。"""
from __future__ import annotations

import hashlib
import json
import time


def warmup_migration_blocker(database, account_id: int, *, connection=None) -> str | None:
    """只读核对旧养号是否留下真实执行，未知事实必须先人工处理。

    :param database: 原始 SQLite 连接工厂。
    :param account_id: 当前账号。
    :param connection: 调用者已持有的事务连接，传入时不另开连接。
    :return: 阻塞说明；没有旧执行时返回 None。
    """
    owned = connection is None
    connection = database() if owned else connection
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'warmup_pi_agents' not in tables:
            return None
        agent = connection.execute('SELECT managed,current_round_id,session_file FROM warmup_pi_agents WHERE account_id=?',
            (account_id,)).fetchone()
        if agent and (agent['managed'] or agent['current_round_id'] or agent['session_file']):
            return '旧题库养号已产生执行或会话，需先人工核对；不能替换为工程任务'
        if 'warmup_pi_rounds' in tables and connection.execute('SELECT 1 FROM warmup_pi_rounds WHERE account_id=? LIMIT 1',
                (account_id,)).fetchone():
            return '旧题库养号已有真实轮次，保留原记录并等待人工处理'
        if 'warmup_pi_actions' in tables and 'warmup_pi_rounds' in tables and connection.execute(
                'SELECT 1 FROM warmup_pi_actions a JOIN warmup_pi_rounds r ON r.id=a.round_id WHERE r.account_id=? LIMIT 1',
                (account_id,)).fetchone():
            return '旧题库养号有未处理输入，禁止自动接管'
        return None
    finally:
        if owned:
            connection.close()


def migrate_warmup_configuration(database, write_lock) -> dict:
    """幂等保留养号原文指南，并只复制已有授权项目池到新独立空间。

    :param database: 原始 SQLite 连接工厂，新工程空间已完成建表。
    :param write_lock: 与账号设置共用的写锁。
    :return: 不包含指南正文的迁移数量和阻塞账号摘要。
    """
    result = {'created_agents': 0, 'imported_guides': 0, 'blocked_accounts': []}
    with write_lock:
        connection = database()
        try:
            with connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'warmup_projects_agents', 'warmup_projects_events', 'projects_agents'} <= tables:
                    raise ValueError('独立工程养号空间尚未初始化')
                accounts = connection.execute('SELECT id FROM accounts WHERE enabled=1 AND deleted_at IS NULL ORDER BY id').fetchall()
                for account in accounts:
                    aid = account['id']
                    blocker = warmup_migration_blocker(database, aid, connection=connection)
                    if blocker:
                        result['blocked_accounts'].append(aid)
                        continue
                    source = connection.execute('SELECT * FROM warmup_pi_agents WHERE account_id=?', (aid,)).fetchone() if 'warmup_pi_agents' in tables else None
                    current = connection.execute('SELECT * FROM warmup_projects_agents WHERE account_id=?', (aid,)).fetchone()
                    original = connection.execute('SELECT project_keys_json FROM projects_agents WHERE account_id=?', (aid,)).fetchone()
                    if not current:
                        # 复制授权不等于开启执行；不存在原项目池时必须保持空池，不能擅自全选。
                        keys = original['project_keys_json'] if original else '[]'
                        budget = source['budget_sec'] if source else 1800
                        connection.execute('INSERT INTO warmup_projects_agents(account_id,project_keys_json,instructions,budget_sec,'
                            'schedule_enabled,schedule_interval_sec,schedule_interval_max_sec,schedule_next_at,updated_at) '
                            'VALUES(?,?,?,?,0,10800,18000,NULL,?)', (aid, keys, '', budget, time.time()))
                        result['created_agents'] += 1
                        current = connection.execute('SELECT * FROM warmup_projects_agents WHERE account_id=?', (aid,)).fetchone()
                    if not source or source['instructions'] == '':
                        continue
                    raw = source['instructions']
                    checksum = hashlib.sha256(raw.encode()).hexdigest()
                    key = f'legacy-warmup-guide:{aid}:{checksum}'
                    if connection.execute('SELECT 1 FROM warmup_projects_events WHERE event_key=?', (key,)).fetchone():
                        continue
                    previous = current['instructions']
                    merged = raw if not previous else previous if previous == raw else previous + '\n\n账号养号追加指南（原文）：\n' + raw
                    # 不调用 configure：它会重排已启用计划；这里只改变指南和更新时间。
                    connection.execute('UPDATE warmup_projects_agents SET instructions=?,updated_at=? WHERE account_id=?',
                        (merged, time.time(), aid))
                    payload = {'source': 'warmup_pi_agents', 'source_sha256': checksum,
                        'previous_sha256': hashlib.sha256(previous.encode()).hexdigest(),
                        'result_sha256': hashlib.sha256(merged.encode()).hexdigest()}
                    connection.execute('INSERT INTO warmup_projects_events(account_id,work_id,kind,payload_json,event_key,created_at) '
                        'VALUES(?,NULL,?,?,?,?)', (aid, 'guide_migrated', json.dumps(payload, ensure_ascii=False), key, time.time()))
                    result['imported_guides'] += 1
        finally:
            connection.close()
    return result
