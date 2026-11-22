"""违约出金门闸事故回归。

夹具在本机文件型 SQLite（tmp_path/*.db）上运行，复刻事故：
同笼代先有“通过”核验，随后被写入“违约”结论，状态字符串仍停在
“核验通过”。旧解笼写口只看状态 + 一条通过核验，于是把本该罚没的
钱误拨出去，罚没册空白。
"""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_path = tmp_path / "incident.db"
    monkeypatch.setattr("db.DB_PATH", db_path)
    init_db()
    assert db_path.exists(), "夹具必须跑在本机文件库上"
    yield


def _auth(c: TestClient, user: str = "admin") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": "123456"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _seed_false_green(c: TestClient, h: dict) -> dict:
    """假绿事故夹具：违约笼仍被解笼口放行。"""
    assert (
        c.post(
            "/api/bonds",
            headers=h,
            json={
                "party_key": "P-INC",
                "party_name": "事故当事方",
                "initial_deposit": 200000,
            },
        ).status_code
        == 200
    )
    cage = c.post(
        "/api/cages/freeze",
        headers=h,
        json={
            "party_key": "P-INC",
            "contract_no": "HT-INC-001",
            "amount": 60000,
            "beneficiary": "事故受益方",
            "cage_code": "CG-INC-001",
        },
    ).json()
    # 事故前：通过核验
    assert (
        c.post(
            "/api/attestations",
            headers=h,
            json={
                "cage_id": cage["id"],
                "outcome": "通过",
                "evidence": "事故前通过",
            },
        ).status_code
        == 200
    )
    # 事故快照：同笼代出现违约结论，状态字符串未同步（假绿）
    with connect() as conn:
        conn.execute(
            """INSERT INTO attestations(cage_id,outcome,evidence,attest_gen,officer,created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                cage["id"],
                "违约",
                "事故夹具：同代违约结论",
                int(cage["generation"]),
                "incident-fixture",
                "2026-11-22T09:59:59",
            ),
        )
        conn.execute(
            "UPDATE cages SET status='核验通过' WHERE id=?", (cage["id"],)
        )
        conn.commit()
    cage["status"] = "核验通过"
    return cage


def _seed_breach(c: TestClient, h: dict) -> dict:
    """正常违约笼：核验结论为违约。"""
    assert (
        c.post(
            "/api/bonds",
            headers=h,
            json={
                "party_key": "P-RACE",
                "party_name": "争用当事方",
                "initial_deposit": 200000,
            },
        ).status_code
        == 200
    )
    cage = c.post(
        "/api/cages/freeze",
        headers=h,
        json={
            "party_key": "P-RACE",
            "contract_no": "HT-RACE-001",
            "amount": 50000,
            "beneficiary": "争用受益方",
            "cage_code": "CG-RACE-001",
        },
    ).json()
    assert (
        c.post(
            "/api/attestations",
            headers=h,
            json={
                "cage_id": cage["id"],
                "outcome": "违约",
                "evidence": "逾期",
            },
        ).status_code
        == 200
    )
    return cage


def test_breach_false_green_release_rejected_zero_increment():
    """红测一：违约笼误拨付必须被门闸拒绝，拨付册零增。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _seed_false_green(c, h)

    with connect() as conn:
        before_releases = conn.execute(
            "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
        ).fetchone()["c"]
        before_forfeits = conn.execute(
            "SELECT COUNT(*) c FROM forfeits WHERE cage_id=?", (cage["id"],)
        ).fetchone()["c"]
        before = conn.execute(
            "SELECT available FROM cages WHERE id=?", (cage["id"],)
        ).fetchone()
        before_frozen = conn.execute(
            "SELECT frozen FROM bond_accounts WHERE party_key='P-INC'"
        ).fetchone()["frozen"]

    r = c.post(
        "/api/releases",
        headers=h,
        json={"cage_id": cage["id"], "payee": "误拨收款方"},
    )
    assert r.status_code == 409, (r.status_code, r.text)
    assert "违约" in r.json()["detail"]

    with connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
            ).fetchone()["c"]
            == before_releases
        ), "拨付册必须零增"
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM forfeits WHERE cage_id=?", (cage["id"],)
            ).fetchone()["c"]
            == before_forfeits
        )
        after = conn.execute(
            "SELECT available FROM cages WHERE id=?", (cage["id"],)
        ).fetchone()
        assert after["available"] == before["available"], "笼可用额不得变动"
        assert (
            conn.execute(
                "SELECT frozen FROM bond_accounts WHERE party_key='P-INC'"
            ).fetchone()["frozen"]
            == before_frozen
        ), "账户冻结不得变动"
        actions = [
            row["action"]
            for row in conn.execute(
                "SELECT action FROM audit_trail WHERE target=?",
                (cage["cage_code"],),
            )
        ]
        assert "breach_outflow_reject" in actions, "必须记拒写审计"
        assert "cage_release" not in actions, "不得落拨付审计"


def test_concurrent_breach_outflow_locks_and_keeps_contention_trace():
    """红测二：两人同抢违约笼出金，须抢笼锁；后到只留争用痕。"""
    c = TestClient(app)
    h_admin = _auth(c, "admin")
    h_clerk = _auth(c, "clerk")
    cage = _seed_breach(c, h_admin)
    lock_key = f"cage:{cage['id']}"

    # 先到者（柜员）抢到笼锁
    assert (
        c.post(
            "/api/locks/acquire", headers=h_clerk, json={"lock_key": lock_key}
        ).status_code
        == 200
    )

    with connect() as conn:
        before_f = conn.execute(
            "SELECT COUNT(*) c FROM forfeits WHERE cage_id=?", (cage["id"],)
        ).fetchone()["c"]
        before_r = conn.execute(
            "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
        ).fetchone()["c"]
        before_avail = conn.execute(
            "SELECT available FROM cages WHERE id=?", (cage["id"],)
        ).fetchone()["available"]

    # 后到者（管理员）同时抢写违约笼出金：只准留争用痕，不准写业务
    late = c.post(
        "/api/forfeits",
        headers=h_admin,
        json={"cage_id": cage["id"], "reason": "后到抢写"},
    )
    assert late.status_code == 409, (late.status_code, late.text)

    with connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM forfeits WHERE cage_id=?", (cage["id"],)
            ).fetchone()["c"]
            == before_f
        ), "后到者不得写罚没册"
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
            ).fetchone()["c"]
            == before_r
        )
        assert (
            conn.execute(
                "SELECT available FROM cages WHERE id=?", (cage["id"],)
            ).fetchone()["available"]
            == before_avail
        )
        trace = conn.execute(
            """SELECT * FROM contention_log
               WHERE lock_key=? AND actor='admin' ORDER BY id DESC""",
            (lock_key,),
        ).fetchall()
        assert trace, "争用痕必须在业务回滚后仍然留存"
        assert trace[0]["action"] == "争用"

    # 持锁者仍可完成罚没出金
    assert (
        c.post(
            "/api/locks/release", headers=h_clerk, json={"lock_key": lock_key}
        ).status_code
        == 200
    )
    ok = c.post(
        "/api/forfeits",
        headers=h_admin,
        json={"cage_id": cage["id"], "reason": "逾期"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["amount"] == 50000


def test_two_simultaneous_breach_outflows_exactly_one_wins():
    """双人同时抢写出金：抢笼锁，恰好一人拿锁出金，后到只留争用痕。"""
    c = TestClient(app)
    h1 = _auth(c, "admin")
    h2 = _auth(c, "clerk")
    cage = _seed_breach(c, h1)
    lock_key = f"cage:{cage['id']}"

    barrier = threading.Barrier(2)
    acquired: list[tuple[str, int]] = []
    lock = threading.Lock()

    def attempt(name: str, headers: dict) -> None:
        barrier.wait()
        r = c.post(
            "/api/locks/acquire", headers=headers, json={"lock_key": lock_key}
        )
        with lock:
            acquired.append((name, r.status_code))

    threads = [
        threading.Thread(target=attempt, args=("admin", h1)),
        threading.Thread(target=attempt, args=("clerk", h2)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    codes = sorted(code for _name, code in acquired)
    assert codes == [200, 409], acquired
    winner_name = next(name for name, code in acquired if code == 200)
    winner_h = h1 if winner_name == "admin" else h2

    with connect() as conn:
        trace = conn.execute(
            "SELECT COUNT(*) c FROM contention_log WHERE lock_key=?", (lock_key,)
        ).fetchone()["c"]
        assert trace >= 1, "后到者须留争用痕"

    # 未拿锁者不得出金；拿锁者完成唯一一笔罚没出金
    assert (
        c.post(
            "/api/forfeits",
            headers=h1 if winner_name != "admin" else h2,
            json={"cage_id": cage["id"], "reason": "未拿锁抢写"},
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/locks/release", headers=winner_h, json={"lock_key": lock_key}
        ).status_code
        == 200
    )
    won = c.post(
        "/api/forfeits",
        headers=winner_h,
        json={"cage_id": cage["id"], "reason": "并发罚没"},
    )
    assert won.status_code == 200, won.text

    with connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM forfeits WHERE cage_id=?", (cage["id"],)
            ).fetchone()["c"]
            == 1
        ), "只允许一笔出金"
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM releases WHERE cage_id=?", (cage["id"],)
            ).fetchone()["c"]
            == 0
        )
        acct = conn.execute(
            "SELECT balance, frozen FROM bond_accounts WHERE party_key='P-RACE'"
        ).fetchone()
        assert acct["frozen"] == 0
        assert acct["balance"] == 150000


def test_false_green_breach_cage_forfeit_allowed():
    """假绿笼（状态停在通过、核验已违约）必须能走罚没，不得两头堵死。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _seed_false_green(c, h)

    r = c.post(
        "/api/forfeits",
        headers=h,
        json={"cage_id": cage["id"], "reason": "事故夹具违约罚没"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 60000
    with connect() as conn:
        row = conn.execute(
            "SELECT available, status FROM cages WHERE id=?", (cage["id"],)
        ).fetchone()
        assert row["available"] == 0
        assert row["status"] == "已罚没"
        acct = conn.execute(
            "SELECT balance, frozen FROM bond_accounts WHERE party_key='P-INC'"
        ).fetchone()
        assert acct["frozen"] == 0
        assert acct["balance"] == 140000


def test_gate_endpoint_is_single_source_for_five_views():
    """五页同源：门闸只读面与写口判定一致，且带纪要素材。"""
    c = TestClient(app)
    h = _auth(c)
    breach = _seed_breach(c, h)
    false_green = _seed_false_green(c, h)

    gate = c.get("/api/gate/outflow", headers=h).json()
    items = {x["cage_id"]: x for x in gate["items"]}
    assert gate["meta"]["basis"] == "甲路径·状态门闸拒写零增"
    assert gate["meta"]["locked_at"] == "2026-11-22"
    assert items[breach["id"]]["breach"] is True
    assert items[breach["id"]]["outflow"] == "仅罚没"
    # 假绿：状态停在通过态，但核验结论为违约，门闸仍判违约
    assert items[false_green["id"]]["breach"] is True
    assert items[false_green["id"]]["outflow"] == "仅罚没"

    # 通过态笼：门闸判非违约，解笼写口可用
    assert (
        c.post(
            "/api/bonds",
            headers=h,
            json={
                "party_key": "P-GATE",
                "party_name": "门闸对照",
                "initial_deposit": 100000,
            },
        ).status_code
        == 200
    )
    ok_cage = c.post(
        "/api/cages/freeze",
        headers=h,
        json={
            "party_key": "P-GATE",
            "contract_no": "HT-GATE-001",
            "amount": 20000,
            "beneficiary": "对照受益方",
            "cage_code": "CG-GATE-001",
        },
    ).json()
    assert (
        c.post(
            "/api/attestations",
            headers=h,
            json={"cage_id": ok_cage["id"], "outcome": "通过", "evidence": "OK"},
        ).status_code
        == 200
    )
    gate2 = c.get(
        f"/api/gate/outflow?cage_id={ok_cage['id']}", headers=h
    ).json()
    assert gate2["items"][0]["breach"] is False
    assert gate2["items"][0]["outflow"] == "允许解笼"
    assert (
        c.post("/api/releases", headers=h, json={"cage_id": ok_cage["id"]}).status_code
        == 200
    )


def test_breach_cage_release_forbidden_but_partial_forfeit_continues():
    """违约只能罚不能拨；部分罚没后仍可续罚，直到出清。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _seed_breach(c, h)

    r = c.post("/api/releases", headers=h, json={"cage_id": cage["id"]})
    assert r.status_code == 409

    first = c.post(
        "/api/forfeits",
        headers=h,
        json={"cage_id": cage["id"], "amount": 20000, "reason": "部分罚没"},
    )
    assert first.status_code == 200, first.text
    second = c.post(
        "/api/forfeits",
        headers=h,
        json={"cage_id": cage["id"], "reason": "尾款罚没"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["amount"] == 30000
    with connect() as conn:
        cage_row = conn.execute(
            "SELECT available, status FROM cages WHERE id=?", (cage["id"],)
        ).fetchone()
        assert cage_row["available"] == 0
        assert cage_row["status"] == "已罚没"
        acct = conn.execute(
            "SELECT balance, frozen FROM bond_accounts WHERE party_key='P-RACE'"
        ).fetchone()
        assert acct["frozen"] == 0
        assert acct["balance"] == 150000


def test_frozen_cage_cannot_be_forfeited_directly():
    """未核验的已冻结笼不得直接进罚没册。"""
    c = TestClient(app)
    h = _auth(c)
    assert (
        c.post(
            "/api/bonds",
            headers=h,
            json={
                "party_key": "P-RAW",
                "party_name": "未核验当事方",
                "initial_deposit": 50000,
            },
        ).status_code
        == 200
    )
    cage = c.post(
        "/api/cages/freeze",
        headers=h,
        json={
            "party_key": "P-RAW",
            "contract_no": "HT-RAW-001",
            "amount": 10000,
            "beneficiary": "未核验受益方",
            "cage_code": "CG-RAW-001",
        },
    ).json()
    r = c.post("/api/forfeits", headers=h, json={"cage_id": cage["id"]})
    assert r.status_code == 409
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM forfeits WHERE cage_id=?", (cage["id"],)
            ).fetchone()["c"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT available FROM cages WHERE id=?", (cage["id"],)
            ).fetchone()["available"]
            == 10000
        )


def test_audit_gate_view_shares_same_memo_and_events():
    """审计页门闸视图与其余四页同源：同纪要、同事件口径。"""
    c = TestClient(app)
    h = _auth(c)
    cage = _seed_false_green(c, h)
    assert c.post("/api/releases", headers=h, json={"cage_id": cage["id"]}).status_code == 409

    gate = c.get("/api/gate/outflow", headers=h).json()
    audit = c.get("/api/audit/gate", headers=h).json()
    assert audit["meta"] == gate["meta"]
    assert audit["meta"]["memo"] == "ops/违约出金门闸纪要.md"
    assert audit["counts"].get("breach_outflow_reject", 0) >= 1
    assert any(x["action"] == "breach_outflow_reject" for x in audit["items"])

    recon = c.get(f"/api/reconcile/{cage['cage_code']}", headers=h).json()
    assert recon["gate"]["breach"] is True
    assert recon["gate"]["outflow"] == "仅罚没"
