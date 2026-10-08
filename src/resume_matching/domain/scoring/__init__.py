"""Deterministic, explainable scoring (see docs/scoring.md)."""

from resume_matching.domain.scoring.engine import ScoringInput, score_match, verdict_for
from resume_matching.domain.scoring.models import MatchComputation

__all__ = ["MatchComputation", "ScoringInput", "score_match", "verdict_for"]
