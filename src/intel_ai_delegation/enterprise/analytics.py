"""Advanced Trust Analytics for enterprise decision-making.

Goes beyond raw trust scores to provide:
  - Trend analysis: How is an agent's trust evolving over time?
  - Anomaly detection: Flag sudden drops or unusual patterns.
  - Comparative scoring: Rank agents within a capability domain.
  - Risk assessment: Predict likelihood of task failure.
  - Portfolio analysis: Aggregate trust across delegation chains.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TrendDirection(Enum):
    """Direction of a trust metric trend."""

    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"


class AlertSeverity(Enum):
    """Severity of a trust anomaly alert."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(Enum):
    """Predicted risk level for a delegation."""

    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TrustTrend:
    """Trend analysis for an agent's trust metrics over time.

    Attributes:
        agent_id: The agent (DID).
        dimension: Which trust dimension (overall, quality, etc.).
        direction: The overall trend direction.
        current_score: Most recent score.
        period_start_score: Score at the start of the analysis window.
        change_rate: Rate of change per period (positive = improving).
        volatility: Standard deviation of scores in the window.
        sample_count: Number of data points in the analysis.
        window_days: Duration of the analysis window in days.
        computed_at: When this analysis was performed.
        data_points: Optional time-series data for visualization.
    """

    agent_id: str
    dimension: str
    direction: TrendDirection
    current_score: float
    period_start_score: float
    change_rate: float = 0.0
    volatility: float = 0.0
    sample_count: int = 0
    window_days: int = 30
    computed_at: datetime = field(default_factory=datetime.utcnow)
    data_points: list[dict[str, Any]] = field(default_factory=list)

    @property
    def absolute_change(self) -> float:
        """Total change from start to current."""
        return self.current_score - self.period_start_score

    @property
    def percentage_change(self) -> float:
        """Percentage change from start to current."""
        if self.period_start_score == 0:
            return 0.0
        return (self.absolute_change / self.period_start_score) * 100


@dataclass
class AnomalyAlert:
    """An alert raised when unusual trust patterns are detected.

    Anomalies include sudden drops, unexplained score spikes,
    inconsistent behavior across dimensions, and statistical outliers.

    Attributes:
        alert_id: Unique identifier.
        agent_id: The affected agent (DID).
        severity: How critical the anomaly is.
        anomaly_type: Classification (e.g., "sudden_drop", "score_spike",
            "dimension_mismatch", "statistical_outlier").
        dimension: Which trust dimension is affected.
        expected_value: What the score was expected to be.
        actual_value: What the score actually is.
        deviation: How far from expected (in standard deviations).
        description: Human-readable explanation.
        recommended_action: Suggested response.
        acknowledged: Whether a human has reviewed this alert.
        detected_at: When the anomaly was detected.
        metadata: Additional context.
    """

    agent_id: str
    severity: AlertSeverity
    anomaly_type: str
    dimension: str
    expected_value: float
    actual_value: float
    deviation: float = 0.0
    description: str = ""
    recommended_action: str = ""
    acknowledged: bool = False
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentComparison:
    """Comparative ranking of agents within a capability domain.

    Attributes:
        domain: The capability domain compared.
        rankings: Ordered list of (agent_id, score, rank) tuples.
        total_agents: Total agents in this domain.
        top_percentile: The score threshold for top 10%.
        median_score: Median score across all agents.
        computed_at: When the comparison was performed.
    """

    domain: str
    rankings: list[dict[str, Any]] = field(default_factory=list)
    total_agents: int = 0
    top_percentile: float = 0.0
    median_score: float = 0.0
    computed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskAssessment:
    """Risk prediction for delegating a specific task to a specific agent.

    Combines agent trust history, task characteristics, and historical
    failure patterns to predict the probability of successful completion.

    Attributes:
        task_id: The task being assessed.
        agent_id: The candidate agent (DID).
        risk_level: Overall risk classification.
        success_probability: Predicted probability of success (0-1).
        risk_factors: Specific factors contributing to risk.
        mitigations: Suggested actions to reduce risk.
        confidence: Confidence in this assessment (0-1).
        assessed_at: When the assessment was made.
    """

    task_id: str
    agent_id: str
    risk_level: RiskLevel
    success_probability: float
    risk_factors: list[dict[str, Any]] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    confidence: float = 0.5
    assessed_at: datetime = field(default_factory=datetime.utcnow)


class TrustAnalytics(ABC):
    """Abstract base for advanced trust analytics.

    Provides enterprise-grade insights beyond raw trust scores,
    enabling data-driven delegation decisions and proactive
    risk management.
    """

    @abstractmethod
    async def compute_trend(
        self, agent_id: str, dimension: str = "overall", window_days: int = 30
    ) -> TrustTrend:
        """Analyze the trend of an agent's trust score over time.

        Args:
            agent_id: The agent to analyze (DID).
            dimension: Trust dimension to track.
            window_days: How many days of history to analyze.

        Returns:
            Trend analysis with direction, rate, and volatility.
        """
        ...

    @abstractmethod
    async def detect_anomalies(
        self, agent_id: str, sensitivity: float = 2.0
    ) -> list[AnomalyAlert]:
        """Detect anomalies in an agent's trust history.

        Uses statistical methods to identify unusual patterns.
        The sensitivity parameter controls the z-score threshold:
        higher values mean fewer, more severe alerts.

        Args:
            agent_id: The agent to analyze (DID).
            sensitivity: Z-score threshold for anomaly detection.

        Returns:
            List of anomaly alerts, if any.
        """
        ...

    @abstractmethod
    async def compare_agents(
        self, domain: str, top_n: int = 10
    ) -> AgentComparison:
        """Rank agents by trust within a capability domain.

        Args:
            domain: The capability domain to compare.
            top_n: Number of top agents to include in rankings.

        Returns:
            Comparative ranking with statistics.
        """
        ...

    @abstractmethod
    async def assess_risk(
        self, task_id: str, agent_id: str
    ) -> RiskAssessment:
        """Predict the risk of delegating a task to an agent.

        Combines trust history, task characteristics, and historical
        failure patterns.

        Args:
            task_id: The task to assess.
            agent_id: The candidate agent (DID).

        Returns:
            Risk assessment with probability and factors.
        """
        ...

    @abstractmethod
    async def get_alerts(
        self,
        agent_id: str | None = None,
        severity: AlertSeverity | None = None,
        acknowledged: bool | None = None,
    ) -> list[AnomalyAlert]:
        """Retrieve anomaly alerts, optionally filtered.

        Args:
            agent_id: Filter by agent (optional).
            severity: Filter by minimum severity (optional).
            acknowledged: Filter by acknowledgment status (optional).

        Returns:
            List of matching alerts.
        """
        ...

    @abstractmethod
    async def acknowledge_alert(self, alert_id: str) -> None:
        """Mark an anomaly alert as reviewed by a human.

        Args:
            alert_id: The alert to acknowledge.
        """
        ...
