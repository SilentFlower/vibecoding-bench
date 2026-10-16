#!/usr/bin/env python3
"""
把 topics.md 同步到已经 seed 过的 SQLite topics 表。

默认只做 dry-run 计划输出；只有传入 `--apply` 才会写数据库。
"""
from __future__ import annotations

import argparse
import sys
import sqlite3
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestrator"))
from topic_library import Topic, encode_followups, parse_topics, validate_topics


def connect_db(path: Path) -> sqlite3.Connection:
    """
    打开 SQLite 数据库并启用按列名访问。

    :param path: SQLite 数据库路径
    :return: SQLite 连接
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_topics_table(conn: sqlite3.Connection) -> None:
    """
    确认目标数据库已存在 topics 表。

    :param conn: SQLite 连接
    :return: None
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='topics'"
    ).fetchone()
    if not row:
        raise SystemExit("目标数据库没有 topics 表，请先启动 orchestrator 初始化 schema")


def plan_sync(conn: sqlite3.Connection, topics: list[Topic]) -> tuple[int, int]:
    """
    统计按编号同步会更新和新增多少条。

    :param conn: SQLite 连接
    :param topics: 待同步 topic 列表
    :return: `(update_count, insert_count)`
    """
    existing = {
        int(row["no"])
        for row in conn.execute("SELECT no FROM topics").fetchall()
    }
    update_count = sum(1 for topic in topics if topic.no in existing)
    insert_count = sum(1 for topic in topics if topic.no not in existing)
    return update_count, insert_count


def backup_db(path: Path) -> Path:
    """
    用 SQLite backup API 生成一致备份，便于远程同步失败后回滚。

    :param path: SQLite 数据库路径
    :return: 备份文件路径
    """
    stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}"
    backup_path = path.with_name(f"{path.name}.bak-{stamp}")
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_path


def apply_sync(conn: sqlite3.Connection, topics: list[Topic]) -> None:
    """
    按 topic.no upsert 题库，保留已有 topic id。

    :param conn: SQLite 连接
    :param topics: 待同步 topic 列表
    :return: None
    """
    with conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(topics)")}
        if "followups_json" not in columns:
            conn.execute("ALTER TABLE topics ADD COLUMN followups_json TEXT NOT NULL DEFAULT '[]'")
        for topic in topics:
            cur = conn.execute(
                "UPDATE topics SET title=?, description=?, category=?, followups_json=?, enabled=1, "
                "deleted_at=NULL, updated_at=julianday('now') WHERE no=?",
                (topic.title, topic.description, topic.category, encode_followups(topic.followups), topic.no),
            )
            if cur.rowcount:
                continue
            conn.execute(
                "INSERT INTO topics(no, title, description, category, followups_json, enabled) "
                "VALUES(?,?,?,?,?,1)",
                (topic.no, topic.title, topic.description, topic.category, encode_followups(topic.followups)),
            )


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    :return: argparse 命名空间
    """
    parser = argparse.ArgumentParser(description="把 topics.md 按编号同步到 SQLite topics 表")
    parser.add_argument("--topics", default="topics.md", help="topics.md 路径")
    parser.add_argument("--db", default="data/db.sqlite", help="SQLite 数据库路径")
    parser.add_argument("--validate-only", action="store_true", help="只校验 topics.md，不访问数据库")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库；默认只输出计划")
    return parser.parse_args()


def main() -> None:
    """
    执行题库同步命令。

    :return: None
    """
    args = parse_args()
    topics_path = Path(args.topics)
    db_path = Path(args.db)
    topics = parse_topics(topics_path)
    validate_topics(topics)
    if args.validate_only:
        print(f"题库校验通过: {len(topics)} 条，编号 1..{topics[-1].no}")
        return
    if not db_path.exists():
        raise SystemExit(f"数据库不存在: {db_path}")

    conn = connect_db(db_path)
    try:
        ensure_topics_table(conn)
        update_count, insert_count = plan_sync(conn, topics)
        print(f"解析题目: {len(topics)} 条")
        print(f"计划更新: {update_count} 条")
        print(f"计划新增: {insert_count} 条")
        if not args.apply:
            print("dry-run 完成；传入 --apply 才会写入数据库")
            return
        backup_path = backup_db(db_path)
        print(f"已备份数据库: {backup_path}")
        apply_sync(conn, topics)
        final_count = conn.execute(
            "SELECT COUNT(*) AS n FROM topics WHERE deleted_at IS NULL AND enabled=1"
        ).fetchone()["n"]
        print(f"同步完成，当前启用题目: {final_count} 条")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
