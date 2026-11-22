"""审计只读面。"""
from __future__ import annotations

from fastapi import APIRouter

from auth import AuthHeader, require_user
from db import connect
from gate import GATE_BASIS, GATE_LOCKED_AT, GATE_MEMO

router = APIRouter(tags=["audit"])

GATE_ACTIONS = ("breach_outflow_reject", "gate_deviation")


@router.get("/api/audit")
def list_audit(authorization: AuthHeader = None, limit: int = 100):
    require_user(authorization)
    limit = max(1, min(int(limit), 500))
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_trail ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/audit/gate")
def list_gate_events(authorization: AuthHeader = None, limit: int = 200):
    """审计页门闸视图：拒写与偏航事件，与其余四页同源同纪要。"""
    require_user(authorization)
    limit = max(1, min(int(limit), 500))
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT * FROM audit_trail
                WHERE action IN ({','.join('?' * len(GATE_ACTIONS))})
                ORDER BY id DESC LIMIT ?""",
            (*GATE_ACTIONS, limit),
        ).fetchall()
        counts = {
            row["action"]: row["c"]
            for row in conn.execute(
                f"""SELECT action, COUNT(*) c FROM audit_trail
                    WHERE action IN ({','.join('?' * len(GATE_ACTIONS))})
                    GROUP BY action""",
                GATE_ACTIONS,
            )
        }
        return {
            "items": [dict(r) for r in rows],
            "counts": counts,
            "meta": {
                "basis": GATE_BASIS,
                "memo": GATE_MEMO,
                "locked_at": GATE_LOCKED_AT,
            },
        }


@router.get("/api/audit/actions")
def list_actions(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT action, COUNT(*) c FROM audit_trail
               GROUP BY action ORDER BY c DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
