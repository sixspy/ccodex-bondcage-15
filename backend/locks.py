"""笼锁与争用登记（公共并发面）。

争用痕必须独立落盘：后到者的业务事务会回滚，争用痕不得随之消失。
持锁也须立即提交，后到者才能快速看到持有者，而不是被写事务阻塞。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit

router = APIRouter(tags=["locks"])


class LockIn(BaseModel):
    lock_key: str
    action: str = "acquire"


def _record_contention(lock_key: str, holder: str, held_by: str) -> None:
    """用独立连接立即提交争用痕，业务回滚不得抹掉。"""
    with connect() as side:
        side.execute(
            """INSERT INTO contention_log(lock_key,actor,action,detail,created_at)
               VALUES (?,?,?,?,?)""",
            (lock_key, holder, "争用", f"持有者={held_by}", now_iso()),
        )
        side.commit()


def try_acquire(conn, lock_key: str, holder: str) -> bool:
    """原子抢锁；失败只写争用痕。

    锁与争用痕走独立连接：持锁立即提交，后到者才能看到持有者；
    争用痕独立提交，业务事务回滚也不得抹掉。
    """
    with connect() as side:
        # INSERT OR IGNORE 判 rowcount：并发下只有一人能插入成功
        cur = side.execute(
            """INSERT OR IGNORE INTO cage_locks(lock_key,holder,acquired_at)
               VALUES (?,?,?)""",
            (lock_key, holder, now_iso()),
        )
        won = cur.rowcount == 1
        side.commit()
        if won:
            return True
        row = side.execute(
            "SELECT holder FROM cage_locks WHERE lock_key=?", (lock_key,)
        ).fetchone()
        if row is not None and row["holder"] == holder:
            return True
        held_by = row["holder"] if row else "-"
    _record_contention(lock_key, holder, held_by)
    return False


def release(conn, lock_key: str, holder: str) -> None:
    conn.execute(
        "DELETE FROM cage_locks WHERE lock_key=? AND holder=?",
        (lock_key, holder),
    )


def require_lock(conn, lock_key: str, holder: str) -> None:
    if not try_acquire(conn, lock_key, holder):
        raise HTTPException(409, "争用：后到只记争用，不写业务")


@router.get("/api/locks")
def list_locks(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM cage_locks ORDER BY acquired_at DESC"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/contention")
def list_contention(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM contention_log ORDER BY id DESC LIMIT 200"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/locks/acquire")
def acquire_lock(body: LockIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        ok = try_acquire(conn, body.lock_key, user)
        write_audit(
            conn,
            user,
            "lock_acquire",
            body.lock_key,
            {"ok": ok},
        )
        conn.commit()
        if not ok:
            raise HTTPException(409, "争用：未能获得锁")
        return {"ok": True, "lock_key": body.lock_key, "holder": user}


@router.post("/api/locks/release")
def release_lock(body: LockIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    with connect() as conn:
        release(conn, body.lock_key, user)
        write_audit(conn, user, "lock_release", body.lock_key, {})
        conn.commit()
        return {"ok": True}
