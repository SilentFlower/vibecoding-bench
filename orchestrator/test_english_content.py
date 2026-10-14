"""英文题库、同步备份和 worker 自动提示的回归测试。"""

import importlib.util
import re
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = ROOT / "scripts/sync-topics-db.py"
SYNC_SPEC = importlib.util.spec_from_file_location("sync_topics_db", SYNC_PATH)
if SYNC_SPEC is None or SYNC_SPEC.loader is None:
    raise RuntimeError("无法载入题库同步模块")
SYNC = importlib.util.module_from_spec(SYNC_SPEC)
sys.modules[SYNC_SPEC.name] = SYNC
SYNC_SPEC.loader.exec_module(SYNC)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class EnglishTopicLibraryTests(unittest.TestCase):
    """验证 600 题英文迁移、安全替换与同步兼容。"""

    def test_full_library_is_complete_english_and_safe(self) -> None:
        """完整题库应通过固定集合、英文和风险词校验。@return None。"""
        topics = SYNC.parse_topics(ROOT / "topics.md")
        SYNC.validate_topics(topics)
        self.assertEqual(set(range(1, 601)), {topic.no for topic in topics})
        self.assertEqual(21, len({topic.category for topic in topics}))
        by_number = {topic.no: topic for topic in topics}
        self.assertEqual("Editorial Tone Consistency Checker", by_number[39].title)
        self.assertEqual("Recurring Routine Reminder", by_number[73].title)
        self.assertEqual("Public Event Availability Digest", by_number[76].title)

    def test_sync_parser_accepts_legacy_and_english_headings(self) -> None:
        """同步解析器应兼容回滚材料中的中文标题和新的英文标题。@return None。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topics.md"
            path.write_text(
                "## 十一、旧分类（1 题）\n"
                "- [ ] 1. **旧题**：旧描述\n"
                "## 2. New Category (1 topic)\n"
                "- [ ] 2. **New Topic**: New description.\n",
                encoding="utf-8",
            )
            topics = SYNC.parse_topics(path)
        self.assertEqual(["旧分类", "New Category"], [topic.category for topic in topics])

    def test_excluded_domains_are_rejected_but_ordinary_apps_remain_valid(self) -> None:
        """拒绝用户排除主题，同时允许天气 API、文件遍历和课程练习。@return None。"""
        topics = SYNC.parse_topics(ROOT / "topics.md")
        for description in (
            "Train a neural model with labeled examples.", "Fine-tune an LLM on a dataset.",
            "Implement a DNS proxy.", "Scan network hosts and open ports.", "Capture TCP packets.",
            "Review security vulnerabilities.", "Build a gene and protein analysis tool.",
            "Manage medical prescriptions and vaccine records.",
        ):
            with self.subTest(description=description):
                modified = [replace(topics[0], description=description), *topics[1:]]
                with self.assertRaisesRegex(SystemExit, "用户排除"):
                    SYNC.validate_topics(modified)
        for description in (
            "Call a weather API and display a forecast.", "Scan local folders and summarize disk usage.",
            "Track training courses, lesson attendance, and certificates.", "Configure an existing LLM client.",
            "Visualize a paper citation network graph.",
        ):
            with self.subTest(description=description):
                SYNC.validate_topics([replace(topics[0], description=description), *topics[1:]])

    def test_sqlite_backup_captures_committed_wal_data(self) -> None:
        """SQLite backup API 应包含仍在 WAL 中的已提交数据。@return None。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "db.sqlite"
            connection = sqlite3.connect(path)
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT)")
                connection.execute("INSERT INTO evidence(value) VALUES('committed-in-wal')")
                connection.commit()
                backup = SYNC.backup_db(path)
                copied = sqlite3.connect(backup)
                try:
                    self.assertEqual(
                        "committed-in-wal",
                        copied.execute("SELECT value FROM evidence").fetchone()[0],
                    )
                finally:
                    copied.close()
            finally:
                connection.close()

    def test_apply_preserves_topic_ids_and_historical_prompts(self) -> None:
        """按编号同步只更新题库字段，不改变 topic ID 或历史 prompt。@return None。"""
        topics = SYNC.parse_topics(ROOT / "topics.md")
        with tempfile.TemporaryDirectory() as tmp:
            connection = sqlite3.connect(Path(tmp) / "db.sqlite")
            connection.row_factory = sqlite3.Row
            try:
                connection.executescript(
                    "CREATE TABLE topics("
                    "id INTEGER PRIMARY KEY, no INTEGER UNIQUE, title TEXT, description TEXT, "
                    "category TEXT, enabled INTEGER DEFAULT 1, deleted_at REAL, updated_at REAL);"
                    "CREATE TABLE tasks(id INTEGER PRIMARY KEY, topic_id INTEGER, prompt TEXT);"
                )
                connection.executemany(
                    "INSERT INTO topics(id,no,title,description,category) VALUES(?,?,?,?,?)",
                    [(1000 + number, number, "old", "old", "old") for number in range(1, 601)],
                )
                connection.execute(
                    "INSERT INTO tasks(id,topic_id,prompt) VALUES(1,1039,'historical prompt')"
                )
                connection.commit()
                SYNC.apply_sync(connection, topics)
                topic = connection.execute("SELECT * FROM topics WHERE no=39").fetchone()
                self.assertEqual(1039, topic["id"])
                self.assertEqual("Editorial Tone Consistency Checker", topic["title"])
                self.assertEqual(
                    "historical prompt",
                    connection.execute("SELECT prompt FROM tasks WHERE id=1").fetchone()[0],
                )
                self.assertEqual(600, connection.execute("SELECT COUNT(*) FROM topics").fetchone()[0])
            finally:
                connection.close()


class EnglishWorkerPromptTests(unittest.TestCase):
    """验证 worker 自动注入的四类默认提示保持英文。"""

    def test_default_runtime_prompts_are_english(self) -> None:
        """续跑、收尾、认证恢复和 API 卡顿恢复默认文本都不得含 CJK。@return None。"""
        script = (ROOT / "images/worker/entrypoint.sh").read_text(encoding="utf-8")
        patterns = {
            "resume": r'TASK_PROMPT="(Continue the original task[^\"]+)',
            "wrapup": r'TIMEOUT_WRAPUP_PROMPT="\$\{TIMEOUT_WRAPUP_PROMPT:-(.+?)\}"',
            "auth": r'AUTH_RECOVERY_PROMPT="\$\{AUTH_RECOVERY_PROMPT:-(.+?)\}"',
            "stall": r'CLAUDE_API_STALL_RECOVERY_PROMPT="\$\{CLAUDE_API_STALL_RECOVERY_PROMPT:-(.+?)\}"',
        }
        prompts = {}
        for name, pattern in patterns.items():
            match = re.search(pattern, script)
            self.assertIsNotNone(match, name)
            prompts[name] = match.group(1)
            self.assertIsNone(CJK_RE.search(match.group(1)), name)
        self.assertIn("Do not start over", prompts["resume"])
        self.assertIn("minimal runnable delivery", prompts["wrapup"])
        self.assertIn("OAuth access token", prompts["auth"])
        self.assertIn("Claude API connection problem", prompts["stall"])


if __name__ == "__main__":
    unittest.main()
