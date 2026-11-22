"""罚没：核验违约后将笼内可用额写入罚没册。

违约出金门闸（纪要 2026-11-22 锁死，甲路径）：
违约笼只允许罚没方向出金；部分罚没后可继续罚尾款，直到出清。
同一笼代已有拨付记录时禁止罚没，避免一笔钱两边走。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from gate import breach_gate, write_reject_audit
from locks import release, require_lock
from models import ForfeitIn

router = APIRouter(tags=["forfeit"])

# 纪要锁定甲路径；携带乙路径口径的请求记偏航并拒写
_MODE_DEVIATION = {"乙路径", "影子罚没", "改道解笼", "先拨后罚"}


@router.get("/api/forfeits")
def list_forfeits(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT f.*, c.cage_code, c.contract_no
               FROM forfeits f
               JOIN cages c ON c.id=f.cage_id
               ORDER BY f.id DESC LIMIT 200"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/forfeits")
def do_forfeit(body: ForfeitIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    lock_key = f"cage:{body.cage_id}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            cage = conn.execute(
                "SELECT * FROM cages WHERE id=?", (body.cage_id,)
            ).fetchone()
            if not cage:
                raise HTTPException(404, "笼不存在")
            gate = breach_gate(conn, cage)
            if body.mode in _MODE_DEVIATION:
                write_reject_audit(
                    conn,
                    write_audit,
                    user,
                    cage,
                    "gate_deviation",
                    {"path": "forfeit", "mode": body.mode},
                )
                conn.commit()
                raise HTTPException(409, "偏离纪要：本仓只启用甲路径，禁止乙路径改道")
            if not gate["breach"]:
                write_reject_audit(
                    conn,
                    write_audit,
                    user,
                    cage,
                    "gate_deviation",
                    {"path": "forfeit", "outcome": gate["outcome"]},
                )
                conn.commit()
                raise HTTPException(409, "非违约态：罚没方向出金被门闸拒绝")
            # 允许违约态，以及事故遗留的状态串滞后（核验已违约、状态仍停在通过态）
            if cage["status"] not in (
                "核验违约",
                "部分罚没",
                "核验通过",
                "部分解笼",
            ):
                raise HTTPException(409, "该笼非违约出金态，禁止罚没")
            gen = int(cage["generation"])
            # 同笼代已拨付过，禁止再罚没：不得一笔钱两边走
            released_prior = conn.execute(
                """SELECT COALESCE(SUM(amount),0) s FROM releases
                   WHERE cage_id=? AND cage_generation=? AND status='已拨付'""",
                (body.cage_id, gen),
            ).fetchone()["s"]
            if float(released_prior) > 1e-9:
                write_reject_audit(
                    conn,
                    write_audit,
                    user,
                    cage,
                    "gate_deviation",
                    {
                        "path": "forfeit",
                        "released_prior": float(released_prior),
                        "note": "同笼代已拨付，禁止罚没",
                    },
                )
                conn.commit()
                raise HTTPException(409, "偏离纪要：同笼代已有拨付，禁止再罚没")
            att = conn.execute(
                """SELECT * FROM attestations
                   WHERE cage_id=? AND attest_gen=? AND outcome='违约'
                   ORDER BY id DESC LIMIT 1""",
                (body.cage_id, gen),
            ).fetchone()
            if not att:
                raise HTTPException(409, "缺少与笼代对齐的违约核验")
            avail = float(cage["available"])
            amount = float(body.amount) if body.amount is not None else avail
            if amount <= 0:
                raise HTTPException(400, "罚没金额须大于 0")
            if amount > avail + 1e-9:
                raise HTTPException(409, "罚没金额超过笼可用额")
            now = now_iso()
            ref = f"FOR-{cage['cage_code']}-g{gen}-{int(now.replace(':', '').replace('-', '').replace('T', '')[-8:])}"
            cur = conn.execute(
                """INSERT INTO forfeits(cage_id,amount,reason,cage_generation,status,forfeit_ref,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    body.cage_id,
                    amount,
                    body.reason or "履约违约",
                    gen,
                    "已罚没",
                    ref,
                    now,
                ),
            )
            new_avail = round(avail - amount, 6)
            new_status = "已罚没" if new_avail <= 1e-9 else "部分罚没"
            conn.execute(
                "UPDATE cages SET available=?, status=? WHERE id=?",
                (max(new_avail, 0.0), new_status, body.cage_id),
            )
            conn.execute(
                """UPDATE bond_accounts
                   SET frozen = frozen - ?, balance = balance - ?
                   WHERE party_key=?""",
                (amount, amount, cage["party_key"]),
            )
            write_audit(
                conn,
                user,
                "cage_forfeit",
                cage["cage_code"],
                {
                    "forfeit_id": cur.lastrowid,
                    "amount": amount,
                    "reason": body.reason,
                    "cage_generation": gen,
                    "forfeit_ref": ref,
                },
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM forfeits WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)
        finally:
            release(conn, lock_key, user)
            conn.commit()
