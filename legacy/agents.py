from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from db import WorkerDB
from receipts import utc_now_iso


AGENT_ROLES = {
    "miner",
    "inference_worker",
    "verifier",
    "router",
    "customer",
    "operator",
    "hybrid",
}

AGENT_STATUSES = {"active", "paused", "disabled"}
AGENT_ACTIONS = {"mine", "serve_inference", "verify", "submit_job", "idle"}
TREASURY_POLICIES = {
    "conservative": {"reserve_ratio": 0.75, "mining_bias": 0.00002, "growth_spend_ratio": 0.05},
    "balanced": {"reserve_ratio": 0.4, "mining_bias": 0.0, "growth_spend_ratio": 0.15},
    "aggressive": {"reserve_ratio": 0.15, "mining_bias": -0.00001, "growth_spend_ratio": 0.35},
}


@dataclass(frozen=True)
class AgentOperations:
    worker_count: int
    mining_hours: float
    inference_hours: float
    verification_hours: float
    routing_hours: float
    total_energy_cost: float
    total_profit: float
    utilization: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "worker_count": self.worker_count,
            "mining_hours": self.mining_hours,
            "inference_hours": self.inference_hours,
            "verification_hours": self.verification_hours,
            "routing_hours": self.routing_hours,
            "total_energy_cost": self.total_energy_cost,
            "total_profit": self.total_profit,
            "utilization": self.utilization,
        }


def create_agent_account(
    db: WorkerDB,
    *,
    agent_id: str,
    operator_id: str,
    role: str,
    worker_id: str | None = None,
    customer_id: str | None = None,
    status: str = "active",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if role not in AGENT_ROLES:
        raise ValueError(f"Unsupported agent role: {role}")
    if status not in AGENT_STATUSES:
        raise ValueError(f"Unsupported agent status: {status}")
    now = utc_now_iso()
    db.conn.execute(
        """
        INSERT INTO agent_accounts (
            agent_id, operator_id, worker_id, customer_id, qi_balance,
            mined_qi, earned_qi, spent_qi, role, status, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, ?, ?, ?, ?)
        """,
        (
            agent_id,
            operator_id,
            worker_id,
            customer_id,
            role,
            status,
            now,
            json.dumps(metadata or {}, sort_keys=True),
        ),
    )
    db.conn.commit()
    return get_agent_account(db, agent_id)


def get_agent_account(db: WorkerDB, agent_id: str) -> dict[str, Any] | None:
    row = db.conn.execute(
        "SELECT * FROM agent_accounts WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    return _agent_row_to_dict(row) if row else None


def record_agent_mining_income(db: WorkerDB, agent_id: str, qi_amount: float) -> dict[str, Any]:
    _require_positive_amount(qi_amount)
    _require_agent(db, agent_id)
    db.conn.execute(
        """
        UPDATE agent_accounts
        SET qi_balance = qi_balance + ?,
            mined_qi = mined_qi + ?
        WHERE agent_id = ?
        """,
        (float(qi_amount), float(qi_amount), agent_id),
    )
    db.conn.commit()
    return get_agent_account(db, agent_id)


def agent_can_spend_qi(db: WorkerDB, agent_id: str, amount: float) -> bool:
    if amount < 0:
        return False
    account = get_agent_account(db, agent_id)
    return bool(account and account["status"] == "active" and account["qi_balance"] >= amount)


def agent_balance(db: WorkerDB, agent_id: str) -> float:
    account = get_agent_account(db, agent_id)
    return float(account["qi_balance"]) if account else 0.0


def fund_agent_job_escrow(
    db: WorkerDB,
    *,
    agent_id: str,
    job_id: str,
    qi_amount: float,
    customer_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_positive_amount(qi_amount)
    account = _require_agent(db, agent_id)
    escrow_customer_id = customer_id or account.get("customer_id")
    now = utc_now_iso()
    with db.conn:
        fresh = db.conn.execute(
            "SELECT qi_balance FROM agent_accounts WHERE agent_id = ? AND status = 'active'",
            (agent_id,),
        ).fetchone()
        if not fresh or float(fresh["qi_balance"]) < qi_amount:
            raise ValueError("Agent has insufficient spendable Qi")
        db.conn.execute(
            """
            UPDATE agent_accounts
            SET qi_balance = qi_balance - ?
            WHERE agent_id = ?
            """,
            (float(qi_amount), agent_id),
        )
        db.conn.execute(
            """
            INSERT INTO agent_escrows (
                escrow_id, agent_id, customer_id, job_id, qi_amount,
                status, created_at, settled_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, 'reserved', ?, NULL, ?)
            """,
            (
                str(uuid4()),
                agent_id,
                escrow_customer_id,
                job_id,
                float(qi_amount),
                now,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
    return get_agent_escrow(db, job_id)


def spend_agent_job_escrow(db: WorkerDB, job_id: str) -> dict[str, Any]:
    escrow = _require_reserved_escrow(db, job_id)
    now = utc_now_iso()
    with db.conn:
        db.conn.execute(
            """
            UPDATE agent_escrows
            SET status = 'spent', settled_at = ?
            WHERE job_id = ? AND status = 'reserved'
            """,
            (now, job_id),
        )
        db.conn.execute(
            """
            UPDATE agent_accounts
            SET spent_qi = spent_qi + ?
            WHERE agent_id = ?
            """,
            (escrow["qi_amount"], escrow["agent_id"]),
        )
    return get_agent_escrow(db, job_id)


def refund_agent_job_escrow(db: WorkerDB, job_id: str) -> dict[str, Any]:
    escrow = _require_reserved_escrow(db, job_id)
    now = utc_now_iso()
    with db.conn:
        db.conn.execute(
            """
            UPDATE agent_escrows
            SET status = 'refunded', settled_at = ?
            WHERE job_id = ? AND status = 'reserved'
            """,
            (now, job_id),
        )
        db.conn.execute(
            """
            UPDATE agent_accounts
            SET qi_balance = qi_balance + ?
            WHERE agent_id = ?
            """,
            (escrow["qi_amount"], escrow["agent_id"]),
        )
    return get_agent_escrow(db, job_id)


def get_agent_escrow(db: WorkerDB, job_id: str) -> dict[str, Any] | None:
    row = db.conn.execute(
        "SELECT * FROM agent_escrows WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    return _escrow_row_to_dict(row) if row else None


def credit_agent_for_verified_worker_job(
    db: WorkerDB,
    *,
    worker_id: str,
    receipt_id: str,
    qi_amount: float,
    verification: dict[str, Any],
    job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Simulation-only direct agent credit.

    Reconciled marketplace accounting should use the customer escrow settlement
    path, which updates worker payable balances and treasury totals.
    """
    _require_positive_amount(qi_amount)
    if not verification.get("accepted"):
        return None
    agent = _agent_for_worker(db, worker_id)
    if not agent:
        return None
    existing = db.conn.execute(
        "SELECT * FROM agent_credit_receipts WHERE receipt_id = ?",
        (receipt_id,),
    ).fetchone()
    if existing:
        return _credit_row_to_dict(existing)

    now = utc_now_iso()
    payout_event_id = str(uuid4())
    event_job_id = job_id or receipt_id
    event_metadata = dict(metadata or {})
    event_metadata["verification"] = verification
    with db.conn:
        db.conn.execute(
            """
            INSERT INTO payout_events (
                event_id, worker_id, event_type, basis, qi_amount,
                created_at, source_id, epoch_id, metadata_json
            ) VALUES (?, ?, 'inference_job', 'verified_agent_worker_job', ?, ?, ?, NULL, ?)
            """,
            (
                payout_event_id,
                worker_id,
                float(qi_amount),
                now,
                receipt_id,
                json.dumps(event_metadata, sort_keys=True),
            ),
        )
        db.conn.execute(
            """
            INSERT INTO balances (worker_id, estimated_qi_owed, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                estimated_qi_owed = estimated_qi_owed + excluded.estimated_qi_owed,
                updated_at = excluded.updated_at
            """,
            (worker_id, float(qi_amount), now),
        )
        if not db.inference_job_was_paid(event_job_id):
            db.conn.execute(
                """
                INSERT INTO inference_jobs (
                    job_id, worker_id, receipt_id, accepted_at, payout_event_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (event_job_id, worker_id, receipt_id, now, payout_event_id),
            )
        db.conn.execute(
            """
            INSERT INTO agent_credit_receipts (
                receipt_id, agent_id, worker_id, job_id, qi_amount,
                credited_at, payout_event_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                agent["agent_id"],
                worker_id,
                job_id,
                float(qi_amount),
                now,
                payout_event_id,
                json.dumps(event_metadata, sort_keys=True),
            ),
        )
        db.conn.execute(
            """
            UPDATE agent_accounts
            SET qi_balance = qi_balance + ?,
                earned_qi = earned_qi + ?
            WHERE agent_id = ?
            """,
            (float(qi_amount), float(qi_amount), agent["agent_id"]),
        )
    return get_agent_credit(db, receipt_id)


def get_agent_credit(db: WorkerDB, receipt_id: str) -> dict[str, Any] | None:
    row = db.conn.execute(
        "SELECT * FROM agent_credit_receipts WHERE receipt_id = ?",
        (receipt_id,),
    ).fetchone()
    return _credit_row_to_dict(row) if row else None


def estimate_agent_profitability(agent: dict[str, Any], market_state: dict[str, Any]) -> dict[str, float]:
    mining = float(market_state.get("mining_qi_per_hour", 0))
    inference = float(market_state.get("inference_qi_per_hour", 0)) * float(market_state.get("inference_demand", 0))
    verify = float(market_state.get("verification_qi_per_hour", 0)) * float(market_state.get("verification_demand", 0))
    submit_job_value = float(market_state.get("job_value_qi", 0)) - float(market_state.get("job_cost_qi", 0))
    return {
        "mine": round(mining, 12),
        "serve_inference": round(inference, 12),
        "verify": round(verify, 12),
        "submit_job": round(submit_job_value, 12),
        "idle": 0.0,
    }


def choose_agent_action(agent: dict[str, Any], market_state: dict[str, Any], config: dict[str, Any]) -> str:
    if agent.get("status") != "active":
        return "idle"
    threshold = float(config.get("minimum_profit_qi_per_hour", config.get("minimum_profit_qi", 0)))
    allowed = set(config.get("allowed_actions", AGENT_ACTIONS))
    role = agent.get("role")
    if role == "miner":
        allowed &= {"mine", "idle"}
    elif role == "inference_worker":
        allowed &= {"serve_inference", "idle"}
    elif role == "verifier":
        allowed &= {"verify", "idle"}
    elif role == "customer":
        allowed &= {"submit_job", "idle"}

    profitability = estimate_agent_profitability(agent, market_state)
    ranked = sorted(
        ((action, value) for action, value in profitability.items() if action in allowed),
        key=lambda item: (item[1], _action_rank(item[0])),
        reverse=True,
    )
    if not ranked or ranked[0][1] < threshold:
        return "idle"
    return ranked[0][0]


def agent_operations(agent: dict[str, Any], operation_events: list[dict[str, Any]]) -> AgentOperations:
    worker_count = int(agent.get("worker_count", 1 if agent.get("worker_id") else 0))
    hours = {"mine": 0.0, "serve_inference": 0.0, "verify": 0.0, "route": 0.0}
    total_energy_cost = 0.0
    total_profit = 0.0
    for event in operation_events:
        action = str(event.get("action", ""))
        duration = max(float(event.get("hours", 0.0)), 0.0)
        if action in hours:
            hours[action] += duration
        total_energy_cost += max(float(event.get("energy_cost", 0.0)), 0.0)
        total_profit += float(event.get("profit", 0.0))
    active_hours = sum(hours.values())
    capacity_hours = max(worker_count, 1) * max(active_hours, 1.0)
    return AgentOperations(
        worker_count=worker_count,
        mining_hours=round(hours["mine"], 12),
        inference_hours=round(hours["serve_inference"], 12),
        verification_hours=round(hours["verify"], 12),
        routing_hours=round(hours["route"], 12),
        total_energy_cost=round(total_energy_cost, 12),
        total_profit=round(total_profit, 12),
        utilization=round(min(active_hours / capacity_hours, 1.0), 12),
    )


def choose_treasury_policy(agent: dict[str, Any], market_state: dict[str, Any]) -> str:
    balance = float(agent.get("qi_balance", 0.0))
    demand = float(market_state.get("inference_demand", 0.0))
    if balance < float(market_state.get("minimum_reserve_qi", 0.0)):
        return "conservative"
    if demand >= 0.8 and balance > float(market_state.get("growth_reserve_qi", 0.0)):
        return "aggressive"
    return "balanced"


def apply_treasury_policy(agent: dict[str, Any], policy_name: str, opportunity: dict[str, Any]) -> dict[str, float | str]:
    if policy_name not in TREASURY_POLICIES:
        raise ValueError(f"Unsupported treasury policy: {policy_name}")
    profile = TREASURY_POLICIES[policy_name]
    balance = max(float(agent.get("qi_balance", 0.0)), 0.0)
    reserve = balance * profile["reserve_ratio"]
    spendable = max(balance - reserve, 0.0)
    growth_budget = spendable * profile["growth_spend_ratio"]
    expected_profit = float(opportunity.get("expected_profit", opportunity.get("expected_profit_per_hour", 0.0)))
    preferred_action = "mine" if expected_profit + profile["mining_bias"] <= 0 else str(opportunity.get("action", "serve_inference"))
    return {
        "policy": policy_name,
        "reserve_qi": round(reserve, 12),
        "growth_budget_qi": round(growth_budget, 12),
        "preferred_action": preferred_action,
    }


def _require_positive_amount(amount: float) -> None:
    if amount <= 0:
        raise ValueError("Qi amount must be positive")


def _require_agent(db: WorkerDB, agent_id: str) -> dict[str, Any]:
    account = get_agent_account(db, agent_id)
    if not account:
        raise ValueError(f"Unknown agent account: {agent_id}")
    return account


def _require_reserved_escrow(db: WorkerDB, job_id: str) -> dict[str, Any]:
    escrow = get_agent_escrow(db, job_id)
    if not escrow or escrow["status"] != "reserved":
        raise ValueError(f"No reserved escrow for job: {job_id}")
    return escrow


def _agent_for_worker(db: WorkerDB, worker_id: str) -> dict[str, Any] | None:
    row = db.conn.execute(
        """
        SELECT * FROM agent_accounts
        WHERE worker_id = ?
          AND status = 'active'
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (worker_id,),
    ).fetchone()
    return _agent_row_to_dict(row) if row else None


def _action_rank(action: str) -> int:
    return {
        "serve_inference": 5,
        "verify": 4,
        "mine": 3,
        "submit_job": 2,
        "idle": 1,
    }.get(action, 0)


def _agent_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "agent_id": row["agent_id"],
        "operator_id": row["operator_id"],
        "worker_id": row["worker_id"],
        "customer_id": row["customer_id"],
        "qi_balance": float(row["qi_balance"]),
        "mined_qi": float(row["mined_qi"]),
        "earned_qi": float(row["earned_qi"]),
        "spent_qi": float(row["spent_qi"]),
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _escrow_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "escrow_id": row["escrow_id"],
        "agent_id": row["agent_id"],
        "customer_id": row["customer_id"],
        "job_id": row["job_id"],
        "qi_amount": float(row["qi_amount"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "settled_at": row["settled_at"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _credit_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "receipt_id": row["receipt_id"],
        "agent_id": row["agent_id"],
        "worker_id": row["worker_id"],
        "job_id": row["job_id"],
        "qi_amount": float(row["qi_amount"]),
        "credited_at": row["credited_at"],
        "payout_event_id": row["payout_event_id"],
        "metadata": json.loads(row["metadata_json"]),
    }
