"""MyridTV 任务表持久化：SQLite 单行 upsert（替代 canvas_tasks.json 整表覆盖写）。

为什么要换：
- 原实现每次状态更新都把整张表（500KB+ / 200+ 条）重写成 json —— 写放大、且写到一半被杀就留半截文件；
- 现在每次更新只写受影响的一行，事务保证原子性，WAL 保证并发读安全。

兼容：首次启动时若库是空的、而老的 canvas_tasks.json 有内容，就一次性导入，
并把老 json 改名为 ``canvas_tasks.json.migrated_<时间戳>`` 归档（不再读写，留作后路）。

只依赖标准库。对外接口：
    TaskStore(db_path, legacy_json_path=None, lock=None)
    .load_all() -> {task_id: state}
    .upsert(task_id, state) -> bool
    .upsert_many({task_id: state}) -> bool
    .count() -> int
    .migrated_from -> str   # 本次启动是否发生迁移的说明，未迁移为空串
    .last_error -> str
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id    TEXT PRIMARY KEY,
    state      TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class TaskStore:
    def __init__(self, db_path, legacy_json_path=None, lock=None):
        self.db_path = Path(db_path)
        self.legacy_json_path = Path(legacy_json_path) if legacy_json_path else None
        self._lock = lock if lock is not None else threading.Lock()
        self._conn = None
        self.migrated_from = ""
        self.last_error = ""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=15)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        except Exception as exc:  # 库都建不起来时降级为内存表，不影响进程启动
            self.last_error = "sqlite init failed: {}".format(exc)
            try:
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._conn.executescript(SCHEMA)
                self._conn.commit()
            except Exception:
                self._conn = None
            return
        self.migrated_from = self._migrate_legacy()

    # ---------- 迁移 ----------

    def _migrate_legacy(self):
        """老 json -> 库（只在库为空且 json 有内容时做一次）。"""
        try:
            with self._lock:
                if self._conn is None:
                    return ""
                total = self.count_locked()
                if total:
                    return ""
                src = self.legacy_json_path
                if not src or not src.exists():
                    return ""
                try:
                    data = json.loads(src.read_text(encoding="utf-8"))
                except Exception as exc:
                    self.last_error = "legacy json unreadable: {}".format(exc)
                    return ""
                if not isinstance(data, dict) or not data:
                    return ""
                rows = []
                now = int(time.time() * 1000)
                for task_id, state in data.items():
                    if isinstance(state, dict) and task_id:
                        rows.append((str(task_id),
                                     json.dumps(state, ensure_ascii=False),
                                     int(state.get("updated_at") or now)))
                if rows:
                    self._conn.executemany(
                        "INSERT OR REPLACE INTO tasks(task_id, state, updated_at) VALUES(?,?,?)", rows)
                    self._conn.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES('migrated_from_json', ?)", (str(src),))
                    self._conn.commit()
                archive = src.with_name(src.name + ".migrated_" + time.strftime("%Y%m%d_%H%M%S"))
                try:
                    src.replace(archive)
                except Exception as exc:
                    self.last_error = "legacy json archive failed: {}".format(exc)
                    archive = src
                return "{} 条 -> {}（原 json 归档为 {}）".format(len(rows), self.db_path.name, Path(archive).name)
        except Exception as exc:
            self.last_error = "migrate failed: {}".format(exc)
            return ""

    # ---------- 读 ----------

    def count_locked(self):
        if self._conn is None:
            return 0
        cur = self._conn.execute("SELECT COUNT(*) FROM tasks")
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0

    def count(self):
        try:
            with self._lock:
                return self.count_locked()
        except Exception as exc:
            self.last_error = "count failed: {}".format(exc)
            return 0

    def load_all(self):
        data = {}
        try:
            with self._lock:
                if self._conn is None:
                    return data
                for task_id, state in self._conn.execute("SELECT task_id, state FROM tasks"):
                    try:
                        parsed = json.loads(state)
                    except Exception:
                        continue
                    if isinstance(parsed, dict):
                        data[str(task_id)] = parsed
        except Exception as exc:
            self.last_error = "load failed: {}".format(exc)
        return data

    # ---------- 写 ----------

    def upsert(self, task_id, state):
        """单行事务写（热路径：任务状态更新只写一行）。"""
        safe_id = str(task_id or "").strip()
        if not safe_id or not isinstance(state, dict):
            return False
        try:
            payload = json.dumps(state, ensure_ascii=False)
        except Exception as exc:
            self.last_error = "not json-serializable: {}".format(exc)
            return False
        return self._upsert_rows([(safe_id, payload, int(state.get("updated_at") or time.time() * 1000))])

    def upsert_many(self, store):
        """整表同步（一次事务；给不确定改动的调用点兜底用）。"""
        rows = []
        now = int(time.time() * 1000)
        for task_id, state in (store or {}).items():
            if not isinstance(state, dict) or not task_id:
                continue
            try:
                rows.append((str(task_id), json.dumps(state, ensure_ascii=False),
                             int(state.get("updated_at") or now)))
            except Exception:
                continue
        return self._upsert_rows(rows)

    def _upsert_rows(self, rows):
        if not rows:
            return True
        try:
            with self._lock:
                if self._conn is None:
                    return False
                self._conn.executemany(
                    "INSERT OR REPLACE INTO tasks(task_id, state, updated_at) VALUES(?,?,?)", rows)
                self._conn.commit()
            return True
        except Exception as exc:
            self.last_error = "upsert failed: {}".format(exc)
            return False

    def delete(self, task_id):
        safe_id = str(task_id or "").strip()
        if not safe_id:
            return False
        try:
            with self._lock:
                if self._conn is None:
                    return False
                self._conn.execute("DELETE FROM tasks WHERE task_id = ?", (safe_id,))
                self._conn.commit()
            return True
        except Exception as exc:
            self.last_error = "delete failed: {}".format(exc)
            return False

    def close(self):
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None
