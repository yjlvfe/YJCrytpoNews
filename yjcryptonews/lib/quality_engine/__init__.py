"""
YJCryptoNews v3.0 - Layer 2: Quality Engine Package
"""
from yjcryptonews.lib.quality_scorer import QualityScorer, QualityScore, score_articles, create_quality_logs
from yjcryptonews.lib.fact_checker import FactChecker, ClaimExtractor, ExtractedClaim, VerificationResult, ClaimType, fact_check_articles
from yjcryptonews.lib.dedup_engine import DeduplicationEngine, DedupResult, DedupAction, DedupStage, deduplicate_articles

__all__ = [
    # Quality Scorer
    "QualityScorer",
    "QualityScore",
    "score_articles",
    "create_quality_logs",
    # Fact Checker
    "FactChecker",
    "ClaimExtractor",
    "ExtractedClaim",
    "VerificationResult",
    "ClaimType",
    "fact_check_articles",
    # Deduplication
    "DeduplicationEngine",
    "DedupResult",
    "DedupAction",
    "DedupStage",
    "deduplicate_articles",
]