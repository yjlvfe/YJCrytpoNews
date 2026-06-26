"""
YJCryptoNews v3.0 - Layer 2: Quality Engine
Fact Checker for verifying article claims
"""
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

from yjcryptonews.models.source import Article, Source, FactCheckStatus
from yjcryptonews import config

logger = logging.getLogger(__name__)


class ClaimType(str, Enum):
    PRICE = "price"
    MARKET_CAP = "market_cap"
    VOLUME = "volume"
    PERCENTAGE_CHANGE = "percentage_change"
    PARTNERSHIP = "partnership"
    LAUNCH = "launch"
    REGULATION = "regulation"
    HACK = "hack"
    FUNDING = "funding"
    PERSONNEL = "personnel"
    TECHNICAL = "technical"
    GENERAL = "general"


@dataclass
class ExtractedClaim:
    """A claim extracted from an article"""
    text: str
    claim_type: ClaimType
    entities: List[str]
    numbers: List[float]
    confidence: float


@dataclass
class VerificationResult:
    """Result of fact verification"""
    claim: ExtractedClaim
    status: FactCheckStatus
    evidence: List[str]
    sources_verified: int
    confidence: float
    notes: str


class ClaimExtractor:
    """Extracts verifiable claims from article text"""

    # Patterns for different claim types
    CLAIM_PATTERNS = {
        ClaimType.PRICE: [
            r"(?:price|trading at|worth|valued at)\s+\$?([\d,]+\.?\d*)",
            r"\$([\d,]+\.?\d*)\s*(?:per|/)\s*(?:btc|eth|token|coin)",
        ],
        ClaimType.MARKET_CAP: [
            r"market cap(?:italization)?\s+(?:of|is|at|reached)\s+\$?([\d,]+\.?\d*)\s*([bmbt])?",
            r"\$([\d,]+\.?\d*)\s*([bmbt])\s*market cap",
        ],
        ClaimType.VOLUME: [
            r"volume\s+(?:of|is|at|reached)\s+\$?([\d,]+\.?\d*)\s*([bmbt])?",
            r"(?:24h|daily)\s+volume\s+\$?([\d,]+\.?\d*)",
        ],
        ClaimType.PERCENTAGE_CHANGE: [
            r"(?:up|down|gained|lost|rose|fell|increased|decreased)\s+(\d+\.?\d*)%",
            r"(\d+\.?\d*)%\s+(?:increase|decrease|gain|loss|rise|fall)",
        ],
        ClaimType.PARTNERSHIP: [
            r"(?:partner(?:ed|ship)|collaborat(?:e|ion)|integrat(?:e|ion)|alliance)\s+with\s+([A-Z][a-zA-Z0-9\s]+)",
            r"([A-Z][a-zA-Z0-9\s]+)\s+(?:announces|announced)\s+(?:partnership|collaboration)",
        ],
        ClaimType.LAUNCH: [
            r"(?:launch(?:es|ed|ing)|debut|release|go live)\s+(?:on|at)\s+([A-Za-z0-9\s]+)",
            r"(?:mainnet|testnet|product)\s+(?:launch|goes live)",
        ],
        ClaimType.REGULATION: [
            r"(?:sec|regulation|regulatory|law|bill|act)\s+(?:approves?|rejects?|files?|passes?)",
            r"(?:etf|exchange.?traded.?fund)\s+(?:approv|reject|filing)",
        ],
        ClaimType.HACK: [
            r"(?:hack|exploit|breach|attack|vulnerability)\s+(?:on|at|of)\s+([A-Z][a-zA-Z0-9\s]+)",
            r"([A-Z][a-zA-Z0-9\s]+)\s+(?:hacked|exploited|compromised)",
            r"(?:lost|stolen|drained)\s+\$?([\d,]+\.?\d*)\s*([bmbt])?",
        ],
        ClaimType.FUNDING: [
            r"(?:rais(?:e|ed|ing)|secur(?:e|ed)|funding|investment)\s+\$?([\d,]+\.?\d*)\s*([bmk])?",
            r"series\s+[abc]\s+\$?([\d,]+\.?\d*)",
        ],
    }

    RED_FLAGS = [
        r"guaranteed.*profit",
        r"100%.*return",
        r"get rich quick",
        r"risk.?free",
        r"can't lose",
        r"secret.*strategy",
        r"insider.*tip",
        r"pump.*dump",
        r"guaranteed.*(\d+)x",
    ]

    def extract_claims(self, article: Article) -> List[ExtractedClaim]:
        """Extract verifiable claims from article"""
        text = f"{article.title} {article.content or ''}"
        claims = []

        for claim_type, patterns in self.CLAIM_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    claim_text = match.group(0)
                    entities = self._extract_entities(claim_text)
                    numbers = self._extract_numbers(claim_text)
                    confidence = self._calculate_confidence(claim_text, claim_type)

                    claims.append(ExtractedClaim(
                        text=claim_text,
                        claim_type=claim_type,
                        entities=entities,
                        numbers=numbers,
                        confidence=confidence,
                    ))

        # Check for red flags
        red_flag_claims = self._check_red_flags(text)
        claims.extend(red_flag_claims)

        return claims

    def _extract_entities(self, text: str) -> List[str]:
        """Extract named entities (simplified)"""
        # Look for capitalized words that could be entity names
        entities = re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}(?:\s+[A-Z][a-zA-Z0-9]{2,})*\b', text)
        return list(set(entities))[:10]  # Limit to 10

    def _extract_numbers(self, text: str) -> List[float]:
        """Extract numerical values"""
        numbers = []
        for match in re.finditer(r'[\d,]+\.?\d*', text.replace(',', '')):
            try:
                numbers.append(float(match.group()))
            except ValueError:
                pass
        return numbers

    def _calculate_confidence(self, text: str, claim_type: ClaimType) -> float:
        """Calculate confidence in the claim extraction"""
        confidence = 0.5  # Base confidence

        # Higher confidence for specific patterns
        if claim_type in [ClaimType.PRICE, ClaimType.PERCENTAGE_CHANGE]:
            confidence += 0.2
        if claim_type in [ClaimType.HACK, ClaimType.FUNDING]:
            confidence += 0.1

        # More context = higher confidence
        if len(text) > 50:
            confidence += 0.1

        return min(1.0, confidence)

    def _check_red_flags(self, text: str) -> List[ExtractedClaim]:
        """Check for promotional/scam red flags"""
        claims = []
        for pattern in self.RED_FLAGS:
            if re.search(pattern, text, re.IGNORECASE):
                claims.append(ExtractedClaim(
                    text=f"Red flag detected: {pattern}",
                    claim_type=ClaimType.GENERAL,
                    entities=[],
                    numbers=[],
                    confidence=0.9,
                ))
        return claims


class VerificationSource(ABC):
    """Abstract base for verification sources"""

    @abstractmethod
    async def verify(self, claim: ExtractedClaim) -> VerificationResult:
        """Verify a claim"""
        pass


class OfficialSourceVerifier(VerificationSource):
    """Verifies against official sources (GitHub, official blogs, etc.)"""

    def __init__(self):
        self.official_domains = {
            "github.com", "gitlab.com", "ethereum.org", "bitcoin.org",
            "binance.com", "coinbase.com", "kraken.com", "coinmarketcap.com",
            "coingecko.com", "defillama.com", "etherscan.io", "bscscan.com",
        }

    async def verify(self, claim: ExtractedClaim) -> VerificationResult:
        # In a real implementation, this would query official APIs
        # For now, return a placeholder
        return VerificationResult(
            claim=claim,
            status=FactCheckStatus.REQUIRES_REVIEW,
            evidence=["Manual verification required"],
            sources_verified=0,
            confidence=0.5,
            notes="Official source verification not fully implemented",
        )


class CrossReferenceVerifier(VerificationSource):
    """Cross-references claims with multiple sources"""

    def __init__(self):
        self.min_sources = config.quality_engine.fact_check.min_sources_required
        self.min_trust = config.quality_engine.fact_check.min_source_trust

    async def verify(self, claim: ExtractedClaim) -> VerificationResult:
        # In a real implementation, this would search across indexed articles
        # For now, return a placeholder
        return VerificationResult(
            claim=claim,
            status=FactCheckStatus.REQUIRES_REVIEW,
            evidence=["Cross-reference verification not fully implemented"],
            sources_verified=0,
            confidence=0.5,
            notes=f"Requires {self.min_sources} sources with trust > {self.min_trust}",
        )


class BlockchainVerifier(VerificationSource):
    """Verifies on-chain data"""

    async def verify(self, claim: ExtractedClaim) -> VerificationResult:
        if not config.quality_engine.fact_check.blockchain_verification_enabled:
            return VerificationResult(
                claim=claim,
                status=FactCheckStatus.PENDING,
                evidence=[],
                sources_verified=0,
                confidence=0.0,
                notes="Blockchain verification disabled",
            )

        # In a real implementation, this would query blockchain data
        # For example: verify token prices on DEX, check transaction hashes, etc.
        return VerificationResult(
            claim=claim,
            status=FactCheckStatus.REQUIRES_REVIEW,
            evidence=["Blockchain verification not fully implemented"],
            sources_verified=0,
            confidence=0.5,
            notes="Blockchain verification not fully implemented",
        )


class FactChecker:
    """Main fact-checking orchestrator"""

    def __init__(self):
        self.claim_extractor = ClaimExtractor()
        self.verifiers = [
            OfficialSourceVerifier(),
            CrossReferenceVerifier(),
        ]
        if config.quality_engine.fact_check.blockchain_verification_enabled:
            self.verifiers.append(BlockchainVerifier())

    async def check_article(self, article: Article) -> FactCheckStatus:
        """Run fact-checking on an article"""
        claims = self.claim_extractor.extract_claims(article)

        if not claims:
            article.fact_check_status = FactCheckStatus.VERIFIED.value
            article.metadata["fact_check"] = {
                "claims_found": 0,
                "status": "verified_no_claims",
            }
            return FactCheckStatus.VERIFIED

        results = []
        for claim in claims:
            for verifier in self.verifiers:
                try:
                    result = await verifier.verify(claim)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Verifier {verifier.__class__.__name__} failed: {e}")

        # Determine overall status
        status = self._determine_status(results)
        article.fact_check_status = status.value
        article.metadata["fact_check"] = {
            "claims_found": len(claims),
            "verifications_run": len(results),
            "status": status.value,
            "details": [
                {
                    "claim": r.claim.text,
                    "type": r.claim.claim_type.value,
                    "status": r.status.value,
                    "confidence": r.confidence,
                }
                for r in results
            ],
        }

        return status

    def _determine_status(self, results: List[VerificationResult]) -> FactCheckStatus:
        """Determine overall fact-check status from results"""
        if not results:
            return FactCheckStatus.REQUIRES_REVIEW

        verified = sum(1 for r in results if r.status == FactCheckStatus.VERIFIED)
        failed = sum(1 for r in results if r.status == FactCheckStatus.FAILED)
        flagged = sum(1 for r in results if r.status == FactCheckStatus.FLAGGED)
        requires_review = sum(1 for r in results if r.status == FactCheckStatus.REQUIRES_REVIEW)

        # If any critical claims failed or flagged
        if flagged > 0:
            return FactCheckStatus.FLAGGED

        # If majority verified
        if verified >= len(results) * 0.6:
            return FactCheckStatus.VERIFIED

        # If majority failed
        if failed >= len(results) * 0.5:
            return FactCheckStatus.FAILED

        return FactCheckStatus.REQUIRES_REVIEW


async def fact_check_articles(articles: List[Article]) -> List[Article]:
    """Fact-check a batch of articles"""
    checker = FactChecker()

    for article in articles:
        try:
            await checker.check_article(article)
            logger.info(f"Article {article.id} fact-check: {article.fact_check_status}")
        except Exception as e:
            logger.error(f"Fact-check failed for article {article.id}: {e}")
            article.fact_check_status = FactCheckStatus.FAILED.value
            article.metadata["fact_check"] = {"error": str(e)}

    return articles