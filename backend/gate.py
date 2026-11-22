"""违约出金门闸：单一判定源。

纪要：`ops/违约出金门闸纪要.md`（2026-11-22 锁死）。
口径：甲路径 —— 违约态只许罚没方向出金；解笼写口遇违约直接拒写零增，
并写 `breach_outflow_reject` 审计。乙路径（影子罚没晋升）本仓不启用；
任何偏离纪要的写入一律记 `gate_deviation` 并拒写。

五页（解笼 / 罚没 / 核验 / 对账 / 审计）共用本模块判定，不得各写一套。
"""
from __future__ import annotations

import json

GATE_MEMO = "ops/违约出金门闸纪要.md"
GATE_LOCKED_AT = "2026-11-22"
GATE_BASIS = "甲路径·状态门闸拒写零增"

# 出金方向
OUTFLOW_FORFEIT_ONLY = "仅罚没"

BREACH_CAGE_STATUSES = frozenset({"核验违约", "部分罚没", "已罚没"})
PASS_CAGE_STATUSES = frozenset({"核验通过", "部分解笼"})


def effective_outcome(conn, cage) -> str | None:
    """合并笼状态与当前笼代核验结论，取违约优先。

    状态字符串可能因历史假绿停在通过态；核验结论才是事实源。
    """
    if not cage:
        return None
    gen = int(cage["generation"])
    rows = conn.execute(
        """SELECT outcome FROM attestations
           WHERE cage_id=? AND attest_gen=?
           ORDER BY id DESC""",
        (cage["id"], gen),
    ).fetchall()
    outcomes = {r["outcome"] for r in rows}
    if "违约" in outcomes:
        return "违约"
    if "通过" in outcomes:
        return "通过"
    if cage["status"] in BREACH_CAGE_STATUSES:
        return "违约"
    if cage["status"] in PASS_CAGE_STATUSES:
        return "通过"
    if cage["status"] == "已冻结":
        return None
    return None


def breach_gate(conn, cage) -> dict:
    """违约出金门闸判定。

    返回 dict：
      breach: 是否违约态
      outflow: 允许方向（禁止 / 仅罚没）
      reason: 人类可读口径
      cage_code / generation: 便于审计与页面展示
    """
    outcome = effective_outcome(conn, cage)
    breach = outcome == "违约"
    if breach:
        outflow = OUTFLOW_FORFEIT_ONLY
        reason = "核验违约：禁止解笼拨付，只允许罚没方向出金"
    else:
        outflow = "允许解笼"
        reason = "非违约态：解笼拨付按通过口径办理"
    return {
        "breach": breach,
        "outflow": outflow,
        "reason": reason,
        "outcome": outcome,
        "cage_code": cage["cage_code"] if cage else None,
        "generation": int(cage["generation"]) if cage else None,
        "basis": GATE_BASIS,
        "memo": GATE_MEMO,
        "locked_at": GATE_LOCKED_AT,
    }


def write_reject_audit(conn, write_audit_fn, actor: str, cage, action: str, detail: dict) -> None:
    """拒写审计：门闸拒写与偏航共用格式。"""
    write_audit_fn(
        conn,
        actor,
        action,
        cage["cage_code"] if cage else "-",
        {
            "gate": GATE_BASIS,
            "memo": GATE_MEMO,
            "locked_at": GATE_LOCKED_AT,
            **detail,
        },
    )
