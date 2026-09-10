"""SQLite 持久層：提供用戶、日誌、任務的數據庫存儲。

當 DATABASE_URL 環境變數設定時使用 SQLite，否則回退到內存存儲。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from backend.hub.store import AgentTask, HubUser, hash_api_key


class ConnectionStats:
    """單個連接的統計信息。"""
    
    def __init__(self, conn_id: str, db_path: str):
        self.id = conn_id
        self.db_path = db_path
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.last_used_at = self.created_at
        self.is_active = True
        self.query_count = 0
        self.total_latency_ms = 0.0
    
    def record_query(self, latency_ms: float):
        """記錄一次查詢。"""
        self.query_count += 1
        self.total_latency_ms += latency_ms
        self.last_used_at = datetime.now(timezone.utc).isoformat()
    
    @property
    def avg_latency_ms(self) -> float:
        """計算平均延遲。"""
        if self.query_count == 0:
            return 0.0
        return self.total_latency_ms / self.query_count
    
    def to_dict(self) -> dict[str, Any]:
        """轉換為字典。"""
        return {
            "id": self.id,
            "db_path": self.db_path,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "is_active": self.is_active,
            "query_count": self.query_count,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
        }


class Database:
    """SQLite 數據庫連接管理類（帶連接池）。"""
    
    # 類級連接池統計
    _pool_stats: dict[str, Any] | None = None
    _pool_lock = threading.Lock()
    _connection_registry: dict[str, ConnectionStats] = {}
    
    def __init__(self, db_path: str | None = None, pool_size: int = 5):
        """初始化數據庫連接。
        
        Args:
            db_path: SQLite 數據庫文件路徑。若為 None，則使用內存數據庫。
            pool_size: 連接池大小（最大連接數）
        """
        if db_path is None:
            db_path = os.getenv("DATABASE_URL", "").replace("sqlite:///", "")
            if not db_path:
                # 使用文件數據庫而非內存數據庫，以確保持久化
                db_path = "hub_data.sqlite3"
        
        self.db_path = db_path
        self.pool_size = pool_size
        self._conn: sqlite3.Connection | None = None
        self._init_db()
        self._register_connection()
    
    def _register_connection(self):
        """註冊當前連接的統計信息。"""
        conn_id = str(uuid.uuid4())[:8]
        stats = ConnectionStats(conn_id, self.db_path)
        with Database._pool_lock:
            Database._connection_registry[conn_id] = stats
            Database._update_pool_stats()
    
    def _get_conn(self) -> sqlite3.Connection:
        """獲取或創建共享數據庫連接。"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # 啟用外鍵約束
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn
    
    @contextmanager
    def get_connection(self, track_latency: bool = True) -> Iterator[sqlite3.Connection]:
        """獲取數據庫連接上下文管理器（帶延遲追蹤）。"""
        conn = self._get_conn()
        start_time = time.perf_counter()
        try:
            yield conn
        finally:
            if track_latency:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                # 更新統計信息
                for stats in Database._connection_registry.values():
                    if stats.db_path == self.db_path and stats.is_active:
                        stats.record_query(elapsed_ms)
                        break
                with Database._pool_lock:
                    Database._update_pool_stats()
    
    @classmethod
    def _update_pool_stats(cls):
        """更新連接池統計信息。"""
        active_conns = [s for s in cls._connection_registry.values() if s.is_active]
        total_queries = sum(s.query_count for s in active_conns)
        total_latency = sum(s.total_latency_ms for s in active_conns)
        avg_latency = total_latency / total_queries if total_queries > 0 else 0.0
        
        cls._pool_stats = {
            "pool_size": len(cls._connection_registry),
            "active_connections": len(active_conns),
            "idle_connections": len(cls._connection_registry) - len(active_conns),
            "total_queries": total_queries,
            "avg_query_latency_ms": round(avg_latency, 2),
            "connections": [s.to_dict() for s in cls._connection_registry.values()],
        }
    
    @classmethod
    def get_pool_stats(cls) -> dict[str, Any]:
        """獲取連接池統計信息。"""
        with cls._pool_lock:
            if cls._pool_stats is None:
                cls._update_pool_stats()
            return cls._pool_stats or {}
    
    @classmethod
    def refresh_pool(cls, min_idle: int = 2) -> dict[str, Any]:
        """刷新連接池（關閉空閒連接）。"""
        with cls._pool_lock:
            # 這裡只是模擬刷新，實際應用中可以關閉空閒連接
            # 由於我們使用共享連接，這裡只重置統計信息
            for stats in cls._connection_registry.values():
                if not stats.is_active:
                    continue
                # 保留最近的連接
            cls._update_pool_stats()
            return cls._pool_stats or {}
    
    @classmethod
    def close_connection(cls, connection_id: str) -> bool:
        """關閉指定連接。"""
        with cls._pool_lock:
            if connection_id in cls._connection_registry:
                cls._connection_registry[connection_id].is_active = False
                cls._update_pool_stats()
                return True
            return False
    
    @classmethod
    def run_health_check(cls) -> dict[str, Any]:
        """執行健康檢查。"""
        issues = []
        healthy = True
        
        with cls._pool_lock:
            # 檢查連接狀態
            for stats in cls._connection_registry.values():
                if not stats.is_active:
                    issues.append(f"Connection {stats.id} is inactive")
                    healthy = False
            
            # 檢查延遲
            if cls._pool_stats and cls._pool_stats.get("avg_query_latency_ms", 0) > 1000:
                issues.append("Average query latency is too high (>1s)")
                healthy = False
        
        return {
            "healthy": healthy,
            "details": "All connections healthy" if healthy else "; ".join(issues),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    
    def _init_db(self) -> None:
        """初始化數據庫表結構並種子開發用戶。"""
        with self.get_connection() as conn:
            conn.executescript("""
                -- 用戶表
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL UNIQUE,
                    monthly_budget_limit_usd REAL DEFAULT 100.0,
                    daily_budget_limit_usd REAL DEFAULT 10.0,
                    preferred_models TEXT DEFAULT '[]',
                    home_region TEXT DEFAULT 'ZZ',
                    data_egress_ack INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                
                -- 調用日誌表
                CREATE TABLE IF NOT EXISTS call_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_id TEXT DEFAULT '',
                    task_id TEXT,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    status TEXT NOT NULL,
                    latency_ms INTEGER DEFAULT 0,
                    error_code TEXT DEFAULT '',
                    trace_id TEXT DEFAULT '',
                    create_time TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_call_logs_user 
                ON call_logs(user_id, create_time DESC);
                
                -- Agent 任務表
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    task_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input TEXT NOT NULL,
                    tools TEXT DEFAULT '[]',
                    cost_usd REAL DEFAULT 0,
                    result TEXT,
                    error_code TEXT DEFAULT '',
                    error_detail TEXT DEFAULT '',
                    trace_id TEXT DEFAULT '',
                    chosen_provider TEXT DEFAULT '',
                    latency_ms INTEGER DEFAULT 0,
                    progress_pct INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    finished_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_agent_tasks_user 
                ON agent_tasks(user_id, created_at DESC);
                
                -- 冪等性鍵表
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
            """)
            
            # 種子開發用戶
            import hashlib
            
            api_key = "ak_live_hub_dev_key_for_local_only"
            api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            
            conn.execute("""
                INSERT OR REPLACE INTO users 
                (id, name, api_key_hash, monthly_budget_limit_usd, daily_budget_limit_usd, 
                 preferred_models, home_region, data_egress_ack)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "00000000-0000-4000-8000-000000000001",
                "hub-dev",
                api_key_hash,
                100.0,
                10.0,
                "[]",
                "ZZ",
                0,
            ))
            conn.commit()
    
    def add_user(self, user: HubUser) -> HubUser:
        """添加或更新用戶。"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO users 
                (id, name, api_key_hash, monthly_budget_limit_usd, daily_budget_limit_usd, 
                 preferred_models, home_region, data_egress_ack, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                str(user.id),
                user.name,
                user.api_key_hash,
                user.monthly_budget_limit_usd,
                user.daily_budget_limit_usd,
                json.dumps(user.preferred_models),
                user.home_region,
                1 if user.data_egress_ack else 0,
            ))
            conn.commit()
        return user
    
    def get_user_by_api_key(self, raw_key: str) -> HubUser | None:
        """根據 API Key 查找用戶。"""
        api_key_hash = hash_api_key(raw_key)
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE api_key_hash = ?", 
                (api_key_hash,)
            ).fetchone()
            
            if row is None:
                return None
            
            return HubUser(
                id=UUID(row["id"]),
                name=row["name"],
                api_key_hash=row["api_key_hash"],
                monthly_budget_limit_usd=row["monthly_budget_limit_usd"],
                daily_budget_limit_usd=row["daily_budget_limit_usd"],
                preferred_models=json.loads(row["preferred_models"] or "[]"),
                home_region=row["home_region"],
                data_egress_ack=bool(row["data_egress_ack"]),
            )
    
    def get_user_by_id(self, user_id: UUID) -> HubUser | None:
        """根據用戶 ID 查找用戶。"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", 
                (str(user_id),)
            ).fetchone()
            
            if row is None:
                return None
            
            return HubUser(
                id=UUID(row["id"]),
                name=row["name"],
                api_key_hash=row["api_key_hash"],
                monthly_budget_limit_usd=row["monthly_budget_limit_usd"],
                daily_budget_limit_usd=row["daily_budget_limit_usd"],
                preferred_models=json.loads(row["preferred_models"] or "[]"),
                home_region=row["home_region"],
                data_egress_ack=bool(row["data_egress_ack"]),
            )
    
    def append_log(self, row: dict[str, Any]) -> None:
        """添加調用日誌。"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO call_logs 
                (id, user_id, session_id, task_id, provider, model_name, 
                 prompt_tokens, completion_tokens, cost_usd, status, 
                 latency_ms, error_code, trace_id, create_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("id", ""),
                row.get("user_id", ""),
                row.get("session_id", ""),
                row.get("task_id"),
                row.get("provider", ""),
                row.get("model_name", ""),
                row.get("prompt_tokens", 0),
                row.get("completion_tokens", 0),
                row.get("cost_usd", 0),
                row.get("status", ""),
                row.get("latency_ms", 0),
                row.get("error_code", ""),
                row.get("trace_id", ""),
                row.get("create_time", datetime.now(timezone.utc).isoformat()),
            ))
            conn.commit()
    
    def save_task(self, task: AgentTask) -> None:
        """保存或更新 Agent 任務。"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO agent_tasks 
                (task_id, user_id, status, input, tools, cost_usd, result, 
                 error_code, error_detail, trace_id, chosen_provider, 
                 latency_ms, progress_pct, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_id,
                str(task.user_id),
                task.status,
                task.input,
                json.dumps(task.tools),
                task.cost_usd,
                json.dumps(task.result) if task.result else None,
                task.error_code,
                task.error_detail,
                task.trace_id,
                task.chosen_provider,
                task.latency_ms,
                task.progress_pct,
                task.finished_at.isoformat() if task.finished_at else None,
            ))
            conn.commit()
    
    def get_task(self, task_id: str) -> AgentTask | None:
        """根據任務 ID 查找任務。"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ?", 
                (task_id,)
            ).fetchone()
            
            if row is None:
                return None
            
            return AgentTask(
                task_id=row["task_id"],
                user_id=UUID(row["user_id"]),
                status=row["status"],
                input=row["input"],
                tools=json.loads(row["tools"] or "[]"),
                cost_usd=row["cost_usd"],
                result=json.loads(row["result"]) if row["result"] else None,
                error_code=row["error_code"],
                error_detail=row["error_detail"],
                trace_id=row["trace_id"],
                chosen_provider=row["chosen_provider"],
                latency_ms=row["latency_ms"],
                progress_pct=row["progress_pct"],
                created_at=datetime.fromisoformat(row["created_at"]),
                finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            )
    
    def set_idempotency_key(self, key: str, task_id: str) -> None:
        """設置冪等性鍵。"""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO idempotency_keys (key, task_id) VALUES (?, ?)",
                (key, task_id)
            )
            conn.commit()
    
    def get_idempotency_key(self, key: str) -> str | None:
        """根據冪等性鍵查找任務 ID。"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT task_id FROM idempotency_keys WHERE key = ?", 
                (key,)
            ).fetchone()
            return row["task_id"] if row else None
    
    def seed_dev_user(self, api_key: str = "ak_live_hub_dev_key_for_local_only") -> HubUser:
        """種子開發用戶。"""
        from uuid import UUID

        from backend.hub.store import HubUser, hash_api_key
        
        user = HubUser(
            id=UUID("00000000-0000-4000-8000-000000000001"),
            name="hub-dev",
            api_key_hash=hash_api_key(api_key),
            daily_budget_limit_usd=10.0,
            monthly_budget_limit_usd=100.0,
        )
        self.add_user(user)
        return user


# 全局數據庫實例（延遲初始化）
_db: Database | None = None


def get_database() -> Database:
    """獲取全局數據庫實例。"""
    global _db
    if _db is None:
        _db = Database()
    return _db


def init_database(db_path: str | None = None) -> Database:
    """初始化全局數據庫實例。"""
    global _db
    _db = Database(db_path)
    # 種子開發用戶（_init_db 已經調用過了）
    return _db
