-- ============================================================================
-- Intelligent AI Delegation — Relational Schema
-- ============================================================================
-- This schema defines the application-layer data model. In production the
-- Ledger_Transactions and Verifiable_Credentials tables should be synced to
-- an immutable smart-contract backend (e.g., Ethereum L2) for tamper-proof
-- reputation tracking and cryptographic verification.
-- ============================================================================

-- --------------------------------------------------------------------------
-- 1. Agents — Delegators, Delegatees, and Verifiers
-- --------------------------------------------------------------------------
-- Identified by Decentralized Identifiers (DIDs) rather than usernames.
-- The public_key is used to cryptographically sign bids, attestations,
-- and monitoring reports.

CREATE TABLE IF NOT EXISTS agents (
    agent_id        TEXT PRIMARY KEY,           -- DID, e.g. "did:web:agent-name"
    name            TEXT NOT NULL,
    agent_type      TEXT NOT NULL CHECK (agent_type IN ('ai', 'human', 'hybrid')),
    public_key      TEXT NOT NULL DEFAULT '',
    base_reputation_score REAL NOT NULL DEFAULT 0.5
        CHECK (base_reputation_score >= 0.0 AND base_reputation_score <= 1.0),
    active_status   BOOLEAN NOT NULL DEFAULT TRUE,
    max_concurrent_tasks INTEGER NOT NULL DEFAULT 1,
    registered_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_agents_type ON agents (agent_type);
CREATE INDEX IF NOT EXISTS idx_agents_active ON agents (active_status);
CREATE INDEX IF NOT EXISTS idx_agents_reputation ON agents (base_reputation_score DESC);

-- --------------------------------------------------------------------------
-- 2. Verifiable_Credentials — The Web of Trust
-- --------------------------------------------------------------------------
-- An agent's reputation is a portfolio of domain-specific endorsements
-- rather than a single generic score. Each credential is cryptographically
-- hashed to guarantee integrity.

CREATE TABLE IF NOT EXISTS verifiable_credentials (
    credential_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL REFERENCES agents (agent_id),
    issuer_id       TEXT NOT NULL REFERENCES agents (agent_id),
    skill_domain    TEXT NOT NULL,              -- e.g. "legal_translation"
    credential_hash TEXT NOT NULL DEFAULT '',   -- SHA-256 of signed payload
    issued_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE,
    evidence        JSONB NOT NULL DEFAULT '{}',
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_credentials_agent ON verifiable_credentials (agent_id);
CREATE INDEX IF NOT EXISTS idx_credentials_issuer ON verifiable_credentials (issuer_id);
CREATE INDEX IF NOT EXISTS idx_credentials_domain ON verifiable_credentials (skill_domain);
CREATE INDEX IF NOT EXISTS idx_credentials_valid
    ON verifiable_credentials (agent_id)
    WHERE revoked = FALSE;

-- --------------------------------------------------------------------------
-- 3. Tasks — The Execution Graph
-- --------------------------------------------------------------------------
-- Supports recursive sub-delegation chains via parent_task_id.
-- Criticality determines permission gating and oversight depth.
-- Reversibility determines failure handling: automatic re-delegation
-- vs. immediate human escalation.

CREATE TABLE IF NOT EXISTS tasks (
    task_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_task_id  UUID REFERENCES tasks (task_id),
    delegator_id    TEXT REFERENCES agents (agent_id),
    assignee_id     TEXT REFERENCES agents (agent_id),
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'bidding', 'assigned', 'in_progress', 'paused',
            'under_verification', 'completed', 'failed', 'cancelled',
            'disputed', 're_delegated'
        )),
    criticality     TEXT NOT NULL DEFAULT 'medium'
        CHECK (criticality IN ('low', 'medium', 'high')),
    reversible      BOOLEAN NOT NULL DEFAULT TRUE,
    priority        TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    verification_method TEXT NOT NULL DEFAULT 'direct_inspection',
    verification_spec   TEXT NOT NULL DEFAULT '',
    acceptance_threshold REAL NOT NULL DEFAULT 1.0,
    input_data      JSONB NOT NULL DEFAULT '{}',
    output_data     JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deadline        TIMESTAMP,
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks (parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_delegator ON tasks (delegator_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks (assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_criticality ON tasks (criticality);

-- --------------------------------------------------------------------------
-- 4. Bids — Market Proposals
-- --------------------------------------------------------------------------
-- Agents bid on tasks in the decentralized market hub. Each bid includes
-- a privacy guarantee and a reputation bond staked into escrow.

CREATE TABLE IF NOT EXISTS bids (
    bid_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             UUID NOT NULL REFERENCES tasks (task_id),
    agent_id            TEXT NOT NULL REFERENCES agents (agent_id),
    proposed_cost       DECIMAL NOT NULL DEFAULT 0,
    proposed_duration_seconds REAL NOT NULL DEFAULT 0,
    confidence          REAL NOT NULL DEFAULT 1.0
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    privacy_guarantee   TEXT NOT NULL DEFAULT 'none',
        -- e.g. "tee_enclave_sgx", "zk_snark", "none"
    reputation_bond     DECIMAL NOT NULL DEFAULT 0,
    message             TEXT NOT NULL DEFAULT '',
    submitted_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata            JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_bids_task ON bids (task_id);
CREATE INDEX IF NOT EXISTS idx_bids_agent ON bids (agent_id);

-- --------------------------------------------------------------------------
-- 5. Smart_Contracts — The Binding Agreements
-- --------------------------------------------------------------------------
-- When a bid is accepted it is formalized here. The contract_terms_hash
-- is an immutable hash of the exact terms to detect retroactive tampering.

CREATE TABLE IF NOT EXISTS smart_contracts (
    contract_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             UUID NOT NULL REFERENCES tasks (task_id),
    bid_id              UUID NOT NULL REFERENCES bids (bid_id),
    delegator_id        TEXT NOT NULL REFERENCES agents (agent_id),
    delegatee_id        TEXT NOT NULL REFERENCES agents (agent_id),
    status              TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN (
            'proposed', 'accepted', 'active', 'completed',
            'breached', 'terminated', 'expired'
        )),
    verification_method TEXT NOT NULL DEFAULT 'direct_inspection'
        CHECK (verification_method IN (
            'direct_inspection', 'third_party_audit',
            'cryptographic_zk_proof', 'consensus_game', 'automated_test'
        )),
    monitoring_cadence  TEXT NOT NULL DEFAULT 'on_completion',
        -- e.g. "every_5m", "on_checkpoint", "on_completion"
    contract_terms_hash TEXT NOT NULL DEFAULT '',
    sla_max_duration_seconds REAL,
    sla_min_quality_score REAL DEFAULT 0.0,
    sla_max_cost        DECIMAL,
    permissions_granted TEXT[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at        TIMESTAMP,
    completed_at        TIMESTAMP,
    metadata            JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_contracts_task ON smart_contracts (task_id);
CREATE INDEX IF NOT EXISTS idx_contracts_delegator ON smart_contracts (delegator_id);
CREATE INDEX IF NOT EXISTS idx_contracts_delegatee ON smart_contracts (delegatee_id);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON smart_contracts (status);

-- --------------------------------------------------------------------------
-- 6. Ledger_Transactions — The Immutable History
-- --------------------------------------------------------------------------
-- Core of the reputation system. Every completed or failed task results
-- in a permanent, append-only record. This table should be synced to an
-- immutable blockchain backend.
--
-- Multi-dimensional scoring: quality, transparency, and safety are tracked
-- independently to support nuanced trust computation.

CREATE TABLE IF NOT EXISTS ledger_transactions (
    transaction_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                 UUID NOT NULL REFERENCES tasks (task_id),
    delegatee_id            TEXT NOT NULL REFERENCES agents (agent_id),
    delegator_id            TEXT REFERENCES agents (agent_id),
    contract_id             UUID REFERENCES smart_contracts (contract_id),
    completion_status       TEXT NOT NULL
        CHECK (completion_status IN ('success', 'failure', 'partial')),
    quality_score           REAL NOT NULL DEFAULT 1.0
        CHECK (quality_score >= 0.0 AND quality_score <= 1.0),
    transparency_score      REAL NOT NULL DEFAULT 1.0
        CHECK (transparency_score >= 0.0 AND transparency_score <= 1.0),
    safety_score            REAL NOT NULL DEFAULT 1.0
        CHECK (safety_score >= 0.0 AND safety_score <= 1.0),
    resource_consumed       JSONB NOT NULL DEFAULT '{}',
        -- e.g. {"gpu_hours": 2.5, "api_tokens": 15000}
    verification_proof_hash TEXT NOT NULL DEFAULT '',
        -- Cryptographic receipt, e.g. zk-SNARK trace
    recorded_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata                JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ledger_task ON ledger_transactions (task_id);
CREATE INDEX IF NOT EXISTS idx_ledger_delegatee ON ledger_transactions (delegatee_id);
CREATE INDEX IF NOT EXISTS idx_ledger_status ON ledger_transactions (completion_status);
CREATE INDEX IF NOT EXISTS idx_ledger_recorded ON ledger_transactions (recorded_at DESC);

-- --------------------------------------------------------------------------
-- 7. Contract_Penalties — Penalty records linked to contracts
-- --------------------------------------------------------------------------
-- Tracks individual penalty events triggered during contract execution.

CREATE TABLE IF NOT EXISTS contract_penalties (
    penalty_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id     UUID NOT NULL REFERENCES smart_contracts (contract_id),
    condition       TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    reputation_impact REAL NOT NULL DEFAULT 0.0,
    description     TEXT NOT NULL DEFAULT '',
    triggered_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_penalties_contract ON contract_penalties (contract_id);

-- --------------------------------------------------------------------------
-- 8. Permission_Grants — Just-in-time scoped access
-- --------------------------------------------------------------------------
-- Tracks temporary, scoped permissions granted to agents for specific tasks.

CREATE TABLE IF NOT EXISTS permission_grants (
    grant_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL REFERENCES agents (agent_id),
    task_id         UUID NOT NULL REFERENCES tasks (task_id),
    contract_id     UUID REFERENCES smart_contracts (contract_id),
    scope           TEXT NOT NULL,              -- e.g. "api:read:users"
    resource        TEXT NOT NULL DEFAULT '*',
    granted_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_permissions_agent ON permission_grants (agent_id);
CREATE INDEX IF NOT EXISTS idx_permissions_task ON permission_grants (task_id);
CREATE INDEX IF NOT EXISTS idx_permissions_active
    ON permission_grants (agent_id)
    WHERE revoked = FALSE;

-- --------------------------------------------------------------------------
-- 9. Monitoring_Events — Telemetry and health checks
-- --------------------------------------------------------------------------
-- Stores monitoring events emitted during task execution. The monitoring
-- cadence is negotiated in the smart contract.

CREATE TABLE IF NOT EXISTS monitoring_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks (task_id),
    contract_id     UUID REFERENCES smart_contracts (contract_id),
    event_type      TEXT NOT NULL,              -- e.g. "progress", "health_check"
    severity        TEXT NOT NULL DEFAULT 'info'
        CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    message         TEXT NOT NULL DEFAULT '',
    data            JSONB NOT NULL DEFAULT '{}',
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_monitoring_task ON monitoring_events (task_id);
CREATE INDEX IF NOT EXISTS idx_monitoring_time ON monitoring_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_severity ON monitoring_events (severity);
