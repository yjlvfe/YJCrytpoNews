"""
YJCryptoNews v3.0 - Layer 2: Quality Engine
Deduplication Engine (4-Stage)
"""
import logging
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import numpy as np
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer

from yjcryptonews.models.source import Article, DuplicateCheck
from yjcryptonews import config

logger = logging.getLogger(__name__)


class DedupAction(str, Enum):
    REJECT = "reject"
    MERGE = "merge"
    QUEUE_REVIEW = "queue_review"
    FLAG = "flag"


class DedupStage(int, Enum):
    EXACT_MATCH = 1
    FUZZY_MATCH = 2
    SEMANTIC_SIMILARITY = 3
    KEY_FACTS = 4


@dataclass
class DedupResult:
    """Result of deduplication check"""
    action: DedupAction
    matched_article_id: Optional[int]
    similarity_score: float
    stage: DedupStage
    details: Dict[str, Any]


class DeduplicationEngine:
    """4-Stage deduplication engine"""

    def __init__(self):
        self.stage2_threshold = config.quality_engine.deduplication.stage2_fuzzy_threshold
        self.stage3_threshold = config.quality_engine.deduplication.stage3_semantic_threshold
        self.stage4_threshold = config.quality_engine.deduplication.stage4_key_facts_threshold

        self._embedding_model: Optional[SentenceTransformer] = None

    def _get_embedding_model(self) -> SentenceTransformer:
        """Lazy load embedding model"""
        if self._embedding_model is None:
            model_name = config.quality_engine.deduplication.embedding_model
            logger.info(f"Loading embedding model: {model_name}")
            self._embedding_model = SentenceTransformer(model_name)
        return self._embedding_model

    def _generate_hash(self, title: str, content: str = "") -> str:
        """Generate hash for exact matching"""
        title = (title or "").strip().lower()
        content = (content or "").strip().lower()[:500]
        combined = f"{title}|{content}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _extract_key_facts(self, article: Article) -> Dict[str, Any]:
        """Extract key facts from article for comparison"""
        text = f"{article.title or ''} {article.content or ''}"

        facts = {
            "entities": [],
            "numbers": [],
            "dates": [],
            "quotes": [],
            "proper_nouns": [],
        }

        # Extract numbers with context
        import re
        number_pattern = r'(\$?[\d,]+\.?\d*\s*[%$€£]?|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4})'
        for match in re.finditer(number_pattern, text, re.IGNORECASE):
            facts["numbers"].append(match.group().strip())

        # Extract proper nouns (capitalized words)
        proper_nouns = re.findall(r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b', text)
        facts["proper_nouns"] = list(set(proper_nouns))[:20]

        # Extract quoted text
        quotes = re.findall(r'"([^"]{10,})"', text)
        facts["quotes"] = quotes[:5]

        return facts

    def _compare_key_facts(self, facts1: Dict[str, Any], facts2: Dict[str, Any]) -> float:
        """Compare key facts between two articles"""
        scores = []

        # Compare proper nouns (entities)
        nouns1 = set(facts1.get("proper_nouns", []))
        nouns2 = set(facts2.get("proper_nouns", []))
        if nouns1 or nouns2:
            overlap = len(nouns1 & nouns2)
            union = len(nouns1 | nouns2)
            scores.append(overlap / union if union > 0 else 0)

        # Compare numbers
        nums1 = set(facts1.get("numbers", []))
        nums2 = set(facts2.get("numbers", []))
        if nums1 or nums2:
            overlap = len(nums1 & nums2)
            union = len(nums1 | nums2)
            scores.append(overlap / union if union > 0 else 0)

        # Compare quotes
        quotes1 = set(facts1.get("quotes", []))
        quotes2 = set(facts2.get("quotes", []))
        if quotes1 or quotes2:
            overlap = len(quotes1 & quotes2)
            union = len(quotes1 | quotes2)
            scores.append(overlap / union if union > 0 else 0)

        return np.mean(scores) if scores else 0.0

    def check_exact_match(self, article: Article, existing_hashes: Dict[str, int]) -> Optional[DedupResult]:
        """Stage 1: Exact match using hash"""
        article_hash = self._generate_hash(article.title, article.content or "")

        if article_hash in existing_hashes:
            return DedupResult(
                action=DedupAction.REJECT,
                matched_article_id=existing_hashes[article_hash],
                similarity_score=1.0,
                stage=DedupStage.EXACT_MATCH,
                details={"hash": article_hash},
            )
        return None

    def check_fuzzy_match(self, article: Article, existing_articles: List[Article]) -> Optional[DedupResult]:
        """Stage 2: Fuzzy matching on title and content"""
        best_match = None
        best_score = 0.0
        best_title_score = 0.0
        best_content_score = 0.0

        art_title = (article.title or "").lower()
        art_content = (article.content or "").lower()[:1000]

        for existing in existing_articles:
            # Compare titles
            title_score = fuzz.ratio(art_title, (existing.title or "").lower()) / 100.0

            # Compare content if available
            content_score = 0.0
            if art_content and existing.content:
                content_score = fuzz.token_set_ratio(
                    art_content,
                    existing.content.lower()[:1000]
                ) / 100.0

            # Weighted combination (title more important)
            combined_score = title_score * 0.7 + content_score * 0.3

            if combined_score > best_score and combined_score >= self.stage2_threshold:
                best_score = combined_score
                best_match = existing
                best_title_score = title_score
                best_content_score = content_score

        if best_match:
            return DedupResult(
                action=DedupAction.MERGE,
                matched_article_id=best_match.id,
                similarity_score=best_score,
                stage=DedupStage.FUZZY_MATCH,
                details={"title_score": best_title_score, "content_score": best_content_score},
            )
        return None

    def check_semantic_similarity(self, article: Article, existing_articles: List[Article]) -> Optional[DedupResult]:
        """Stage 3: Semantic similarity using embeddings (batched + cached)"""
        if not existing_articles:
            return None

        model = self._get_embedding_model()

        # Generate embedding for new article
        new_text = f"{article.title or ''} {article.content or ''}"
        new_embedding = model.encode(new_text, normalize_embeddings=True)

        # Batch-encode existing articles ONCE and cache on the engine instance.
        # Avoids O(N*M) re-encoding (was re-encoding every existing article
        # for every new article -> thousands of redundant encode() calls).
        existing_matrix, id_list = self._get_existing_embeddings(existing_articles)
        if existing_matrix is None:
            return None

        # Vectorized cosine similarity (embeddings already normalized)
        sims = existing_matrix @ new_embedding
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score >= self.stage3_threshold:
            return DedupResult(
                action=DedupAction.REJECT,
                matched_article_id=id_list[best_idx],
                similarity_score=best_score,
                stage=DedupStage.SEMANTIC_SIMILARITY,
                details={"embedding_similarity": best_score},
            )
        return None

    def _get_existing_embeddings(self, existing_articles: List[Article]):
        """Batch-encode and cache existing-article embeddings per engine instance."""
        cache = getattr(self, "_existing_emb_cache", None)
        if cache is not None and cache[0] == len(existing_articles):
            return cache[1], cache[2]

        model = self._get_embedding_model()
        texts = [f"{ex.title or ''} {ex.content or ''}" for ex in existing_articles]
        id_list = [ex.id for ex in existing_articles]
        if not texts:
            return None, []
        matrix = model.encode(
            texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False
        )
        matrix = np.asarray(matrix, dtype=np.float32)
        self._existing_emb_cache = (len(existing_articles), matrix, id_list)
        return matrix, id_list

    def check_key_facts(self, article: Article, existing_articles: List[Article]) -> Optional[DedupResult]:
        """Stage 4: Key facts extraction and comparison"""
        if not existing_articles:
            return None

        new_facts = self._extract_key_facts(article)

        best_match = None
        best_score = 0.0

        # Cache existing-article facts per engine instance (avoid O(N*M) re-extraction)
        facts_cache = getattr(self, "_existing_facts_cache", None)
        if facts_cache is None or facts_cache[0] != len(existing_articles):
            facts_cache = (
                len(existing_articles),
                [(ex.id, self._extract_key_facts(ex)) for ex in existing_articles],
            )
            self._existing_facts_cache = facts_cache

        for ex_id, existing_facts in facts_cache[1]:
            similarity = self._compare_key_facts(new_facts, existing_facts)

            if similarity > best_score and similarity >= self.stage4_threshold:
                best_score = similarity
                best_match = ex_id

        if best_match is not None:
            return DedupResult(
                action=DedupAction.REJECT,
                matched_article_id=best_match,
                similarity_score=best_score,
                stage=DedupStage.KEY_FACTS,
                details={"key_facts_overlap": best_score},
            )
        return None

    def check_duplicate(
        self,
        article: Article,
        existing_articles: List[Article],
        existing_hashes: Optional[Dict[str, int]] = None
    ) -> Tuple[List[DuplicateCheck], Optional[DedupResult]]:
        """Run all 4 stages of deduplication"""
        checks = []
        final_result = None

        # Stage 1: Exact match
        if existing_hashes is None:
            existing_hashes = {}
            for ex in existing_articles:
                h = self._generate_hash(ex.title, ex.content or "")
                existing_hashes[h] = ex.id

        result = self.check_exact_match(article, existing_hashes)
        if result:
            checks.append(DuplicateCheck(
                article_id=article.id,
                hash=self._generate_hash(article.title, article.content or ""),
                checked_against=result.matched_article_id,
                similarity_score=str(result.similarity_score),
                stage=result.stage.value,
                action_taken=result.action.value,
            ))
            return checks, result

        checks.append(DuplicateCheck(
            article_id=article.id,
            hash=self._generate_hash(article.title, article.content or ""),
            similarity_score="0.0",
            stage=DedupStage.EXACT_MATCH.value,
            action_taken="none",
        ))

        # Stage 2: Fuzzy match
        result = self.check_fuzzy_match(article, existing_articles)
        if result:
            checks.append(DuplicateCheck(
                article_id=article.id,
                hash=self._generate_hash(article.title, article.content or ""),
                checked_against=result.matched_article_id,
                similarity_score=str(result.similarity_score),
                stage=result.stage.value,
                action_taken=result.action.value,
            ))
            return checks, result

        checks.append(DuplicateCheck(
            article_id=article.id,
            hash=self._generate_hash(article.title, article.content or ""),
            similarity_score="0.0",
            stage=DedupStage.FUZZY_MATCH.value,
            action_taken="none",
        ))

        # Stage 3: Semantic similarity
        result = self.check_semantic_similarity(article, existing_articles)
        stage3_result = result
        if result:
            checks.append(DuplicateCheck(
                article_id=article.id,
                hash=self._generate_hash(article.title, article.content or ""),
                checked_against=result.matched_article_id,
                similarity_score=str(result.similarity_score),
                stage=result.stage.value,
                action_taken=result.action.value,
            ))
            # Don't return yet, continue to stage 4

        checks.append(DuplicateCheck(
            article_id=article.id,
            hash=self._generate_hash(article.title, article.content or ""),
            similarity_score="0.0",
            stage=DedupStage.SEMANTIC_SIMILARITY.value,
            action_taken="none" if not result else "continue",
        ))

        # Stage 4: Key facts
        result = self.check_key_facts(article, existing_articles)
        if result:
            checks.append(DuplicateCheck(
                article_id=article.id,
                hash=self._generate_hash(article.title, article.content or ""),
                checked_against=result.matched_article_id,
                similarity_score=str(result.similarity_score),
                stage=result.stage.value,
                action_taken=result.action.value,
            ))
            return checks, result

        # Return stage 3 result if stage 4 didn't find anything
        if stage3_result:
            return checks, stage3_result

        checks.append(DuplicateCheck(
            article_id=article.id,
            hash=self._generate_hash(article.title, article.content or ""),
            similarity_score="0.0",
            stage=DedupStage.KEY_FACTS.value,
            action_taken="none",
        ))

        return checks, None


async def deduplicate_articles(
    new_articles: List[Article],
    existing_articles: List[Article]
) -> Tuple[List[Article], List[DuplicateCheck]]:
    """Deduplicate a batch of new articles against existing"""
    engine = DeduplicationEngine()

    # Build hash map for stage 1
    existing_hashes = {}
    for ex in existing_articles:
        h = engine._generate_hash(ex.title, ex.content or "")
        existing_hashes[h] = ex.id

    unique_articles = []
    all_checks = []

    for article in new_articles:
        checks, result = engine.check_duplicate(article, existing_articles, existing_hashes)
        all_checks.extend(checks)

        if result:
            logger.info(f"Article {article.id} duplicate detected at stage {result.stage}: {result.action}")
            # ALL duplicate stages result in rejection
            if not hasattr(article, "metadata") or not isinstance(article.metadata, dict):
                article.metadata = {}
            article.metadata["dedup_action"] = "reject"
            article.metadata["dedup_matched_id"] = result.matched_article_id
            article.metadata["dedup_stage"] = result.stage.value
            article.metadata["dedup_score"] = str(result.similarity_score)
            continue  # Skip this article

        unique_articles.append(article)

    logger.info(f"Deduplication: {len(new_articles)} -> {len(unique_articles)} articles")
    return unique_articles, all_checks