"""解笼拨付：核验通过后把笼内可用额拨付给受益人。

违约出金门闸（纪要 2026-11-22 锁死，甲路径）：
核验违约的笼在本写口**直接拒写零增**，记 `breach_outflow_reject`；
绝不改道影子罚没（乙路径不启用），也绝不只置灰页面。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from gate import GATE_BASIS, GATE_LOCKED_AT, GATE_MEMO, breach_gate, write_reject_audit
from locks import release, require_lock
from models import ReleaseIn

router = APIRouter(tags=["release"])

# 纪要锁定甲路径；携带乙路径口径的请求记偏航并拒写
_MODE_DEVIATION = {"乙路径", "影子罚没", "影子拨付", "改道罚没"}


@router.get("/api/releases")
def list_releases(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.*, c.cage_code, c.contract_no
               FROM releases r
               JOIN cages c ON c.id=r.cage_id
               ORDER BY r.id DESC LIMIT 200"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/gate/outflow")
def gate_outflow(cage_id: int | None = None, authorization: AuthHeader = None):
    """五页同源：违约出金门闸只读视图。

    不带 cage_id 时返回全笼门闸，供解笼/罚没/核验/对账/审计页共用。
    """
    require_user(authorization)
    with connect() as conn:
        if cage_id:
            cages = conn.execute(
                "SELECT * FROM cages WHERE id=?", (cage_id,)
            ).fetchall()
        else:
            cages = conn.execute("SELECT * FROM cages ORDER BY id").fetchall()
        items = []
        for cage in cages:
            gate = breach_gate(conn, cage)
            items.append(
                {
                    "cage_id": cage["id"],
                    "cage_code": cage["cage_code"],
                    "generation": int(cage["generation"]),
                    "status": cage["status"],
                    "available": float(cage["available"]),
                    **gate,
                }
            )
        return {
            "items": items,
            "meta": {
                "basis": GATE_BASIS,
                "memo": GATE_MEMO,
                "locked_at": GATE_LOCKED_AT,
            },
        }


@router.post("/api/releases")
def do_release(body: ReleaseIn, authorization: AuthHeader = None):
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
                    {"path": "release", "mode": body.mode},
                )
                conn.commit()
                raise HTTPException(409, "偏离纪要：本仓只启用甲路径，禁止乙路径改道")
            if gate["breach"]:
                write_reject_audit(
                    conn,
                    write_audit,
                    user,
                    cage,
                    "breach_outflow_reject",
                    {
                        "path": "release",
                        "amount": body.amount,
                        "payee": body.payee,
                        "outflow": gate["outflow"],
                        "reason": gate["reason"],
                    },
                )
                conn.commit()
                raise HTTPException(
                    409,
                    f"违约出金门闸：{gate['reason']}；拨付册零增",
                )
            if cage["status"] != "核验通过" and cage["status"] != "部分解笼":
                raise HTTPException(409, "仅核验通过的笼可解笼拨付")
            # 核验结论必须对齐当前笼代
            att = conn.execute(
                """SELECT * FROM attestations
                   WHERE cage_id=? AND attest_gen=? AND outcome='通过'
                   ORDER BY id DESC LIMIT 1""",
                (body.cage_id, int(cage["generation"])),
            ).fetchone()
            if not att:
                raise HTTPException(409, "缺少与笼代对齐的通过核验")
            avail = float(cage["available"])
            amount = float(body.amount) if body.amount is not None else avail
            if amount <= 0:
                raise HTTPException(400, "拨付金额须大于 0")
            if amount > avail + 1e-9:
                raise HTTPException(409, "拨付金额超过笼可用额")
            payee = body.payee or cage["beneficiary"]
            now = now_iso()
            gen = int(cage["generation"])
            ref = f"REL-{cage['cage_code']}-g{gen}-{int(now.replace(':', '').replace('-', '').replace('T', '')[-8:])}"
            cur = conn.execute(
                """INSERT INTO releases(cage_id,amount,payee,cage_generation,status,release_ref,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (body.cage_id, amount, payee, gen, "已拨付", ref, now),
            )
            new_avail = round(avail - amount, 6)
            new_status = "已解笼" if new_avail <= 1e-9 else "部分解笼"
            conn.execute(
                "UPDATE cages SET available=?, status=? WHERE id=?",
                (max(new_avail, 0.0), new_status, body.cage_id),
            )
            # 账户：冻结减少，余额减少（资金离开系统）
            conn.execute(
                """UPDATE bond_accounts
                   SET frozen = frozen - ?, balance = balance - ?
                   WHERE party_key=?""",
                (amount, amount, cage["party_key"]),
            )
            write_audit(
                conn,
                user,
                "cage_release",
                cage["cage_code"],
                {
                    "release_id": cur.lastrowid,
                    "amount": amount,
                    "payee": payee,
                    "cage_generation": gen,
                    "release_ref": ref,
                },
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM releases WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)
        finally:
            release(conn, lock_key, user)
            conn.commit()
