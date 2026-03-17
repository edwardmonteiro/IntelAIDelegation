"""Verifiable Credential model — the Web of Trust for agent reputation.

Instead of a single generic reputation score, an agent's reputation operates
as a portfolio of domain-specific endorsements. Each credential is issued by
a trusted third party or a previous delegator and is cryptographically signed
to ensure tamper-resistance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class VerifiableCredential:
    """A domain-specific endorsement in an agent's reputation portfolio.

    Credentials are issued by other agents (delegators, verifiers, or
    trusted third parties) and stored with a cryptographic hash to
    guarantee integrity.

    Attributes:
        credential_id: Globally unique identifier.
        agent_id: The agent this credential belongs to (DID).
        issuer_id: The agent or authority that issued this credential (DID).
        skill_domain: Domain-specific skill endorsed, e.g.
            "legal_translation", "formal_code_verification".
        credential_hash: Cryptographic hash proving the credential
            has not been tampered with (e.g., SHA-256 of signed payload).
        issued_at: When the credential was issued.
        expires_at: Optional expiration date.
        revoked: Whether the issuer has revoked this credential.
        evidence: Supporting evidence or proof payload.
        metadata: Extensible key-value data.
    """

    agent_id: str
    issuer_id: str
    skill_domain: str
    credential_hash: str = ""
    credential_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    issued_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    revoked: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if the credential is currently active (not expired, not revoked)."""
        if self.revoked:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True
