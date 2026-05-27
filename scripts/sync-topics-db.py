#!/usr/bin/env python3
"""
把 topics.md 同步到已经 seed 过的 SQLite topics 表。

默认只做 dry-run 计划输出；只有传入 `--apply` 才会写数据库。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


_CAT_RE = re.compile(r"^##\s+[一二三四五六七八九十]+、(.+?)（")
_ITEM_RE = re.compile(r"^-\s+\[[ x]\]\s+(\d+)\.\s+\*\*(.+?)\*\*[:：]?\s*(.*)$")


@dataclass(frozen=True)
class Topic:
    """
    题库条目的结构化表示。

    :param no: 题目编号
    :param title: 题目标题
    :param description: 题目描述
    :param category: 题目分类
    """

    no: int
    title: str
    description: str
    category: str


def parse_topics(path: Path) -> list[Topic]:
    """
    从 Markdown 题库解析 topic 列表。

    :param path: `topics.md` 文件路径
    :return: 解析出的 topic 列表
    """
    topics: list[Topic] = []
    current_category = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        cm = _CAT_RE.match(line)
        if cm:
            current_category = cm.group(1).strip()
            continue
        im = _ITEM_RE.match(line)
        if not im:
            continue
        no, title, desc = im.groups()
        topics.append(Topic(
            no=int(no),
            title=title.strip(),
            description=desc.strip(),
            category=current_category,
        ))
    return topics


def validate_topics(topics: list[Topic]) -> None:
    """
    校验题库编号和必填字段，避免把坏数据写入远程库。

    :param topics: 待校验的 topic 列表
    :return: None
    """
    if not topics:
        raise SystemExit("题库为空，未解析到任何题目")
    numbers = [topic.no for topic in topics]
    duplicates = sorted({no for no in numbers if numbers.count(no) > 1})
    if duplicates:
        raise SystemExit(f"题目编号重复: {duplicates}")
    expected = list(range(1, max(numbers or [0]) + 1))
    if numbers != expected:
        raise SystemExit(f"题目编号不连续: 期望 1..{len(expected)}，实际 {numbers[:5]}...{numbers[-5:]}")
    missing = [topic.no for topic in topics if not topic.title or not topic.description or not topic.category]
    if missing:
        raise SystemExit(f"题目字段缺失: {missing}")


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
    备份 SQLite 文件，便于远程同步失败后回滚。

    :param path: SQLite 数据库路径
    :return: 备份文件路径
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def apply_sync(conn: sqlite3.Connection, topics: list[Topic]) -> None:
    """
    按 topic.no upsert 题库，保留已有 topic id。

    :param conn: SQLite 连接
    :param topics: 待同步 topic 列表
    :return: None
    """
    with conn:
        for topic in topics:
            cur = conn.execute(
                "UPDATE topics SET title=?, description=?, category=?, enabled=1, "
                "deleted_at=NULL, updated_at=julianday('now') WHERE no=?",
                (topic.title, topic.description, topic.category, topic.no),
            )
            if cur.rowcount:
                continue
            conn.execute(
                "INSERT INTO topics(no, title, description, category, enabled) "
                "VALUES(?,?,?,?,1)",
                (topic.no, topic.title, topic.description, topic.category),
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
