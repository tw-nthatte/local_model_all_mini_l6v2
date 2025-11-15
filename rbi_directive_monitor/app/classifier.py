"""
Classification module for RBI Master Directives
Uses TF-IDF vectorization and cosine similarity for intelligent filtering
"""
import json
import logging
from typing import List, Dict, Tuple, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)


class DirectiveClassifier:
    """
    Classifier for identifying IT governance and digital banking directives
    Uses NLP techniques (TF-IDF + cosine similarity) for classification
    """

    def __init__(self):
        """Initialize classifier with keywords and vectorizer"""
        self.keywords = self._load_keywords()
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 3),
            min_df=1
        )
        self.threshold = settings.SIMILARITY_THRESHOLD
        self.min_keyword_matches = settings.MIN_KEYWORD_MATCHES
        logger.info(f"Classifier initialized. Threshold: {self.threshold}")

    def _load_keywords(self) -> Dict[str, List[str]]:
        """
        Load predefined keywords from JSON file

        Returns:
            Dictionary of keyword categories
        """
        keywords_path = Path(settings.KEYWORDS_FILE)

        if keywords_path.exists():
            try:
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    keywords = json.load(f)
                    logger.info(f"Loaded {len(keywords)} keyword categories from {keywords_path}")
                    return keywords
            except Exception as e:
                logger.warning(f"Failed to load keywords from file: {e}")

        # Default keywords if file doesn't exist
        logger.info("Using default keyword set")
        return {
            "it_governance": [
                "information technology",
                "IT governance",
                "cyber security",
                "data security",
                "information security",
                "IT risk",
                "technology risk",
                "IT audit",
                "systems audit",
                "IT controls",
                "technology controls",
                "IT infrastructure",
                "cloud computing",
                "data center",
                "disaster recovery",
                "business continuity",
                "IT outsourcing",
                "technology services",
                "systems management",
                "network security",
                "encryption",
                "access control",
                "identity management",
                "IT governance framework"
            ],
            "digital_banking": [
                "digital banking",
                "internet banking",
                "mobile banking",
                "online banking",
                "digital payment",
                "payment system",
                "electronic payment",
                "UPI",
                "NEFT",
                "RTGS",
                "digital wallet",
                "fintech",
                "API banking",
                "open banking",
                "digital lending",
                "digital KYC",
                "e-KYC",
                "biometric",
                "blockchain",
                "cryptocurrency",
                "digital currency",
                "payment gateway",
                "online transaction",
                "digital onboarding",
                "e-banking"
            ],
            "compliance": [
                "compliance monitoring",
                "regulatory compliance",
                "audit trail",
                "data privacy",
                "GDPR",
                "data protection",
                "KYC",
                "AML",
                "anti-money laundering",
                "compliance framework",
                "compliance audit",
                "regulatory reporting",
                "compliance risk"
            ]
        }

    def classify(self, directive: Dict) -> Tuple[bool, float, List[str]]:
        """
        Classify a single directive as relevant or not

        Combines:
        1. TF-IDF similarity scoring
        2. Keyword matching

        Args:
            directive: Dictionary with directive metadata (title, category)

        Returns:
            Tuple of (is_relevant, similarity_score, matched_keywords)
        """
        try:
            # Combine title and category for classification
            text = f"{directive.get('title', '')} {directive.get('category', '')}"

            if not text.strip():
                logger.warning("Empty directive text for classification")
                return False, 0.0, []

            # Flatten all keywords
            all_keywords = []
            for category_keywords in self.keywords.values():
                all_keywords.extend(category_keywords)

            if not all_keywords:
                logger.warning("No keywords available for classification")
                return False, 0.0, []

            # Create reference text from all keywords
            keyword_text = " ".join(all_keywords)

            # Calculate TF-IDF similarity
            try:
                vectors = self.vectorizer.fit_transform([text.lower(), keyword_text.lower()])
                similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
            except Exception as e:
                logger.warning(f"TF-IDF vectorization failed: {e}")
                similarity = 0.0

            # Find exact keyword matches
            matched_keywords = self._find_matched_keywords(text.lower(), all_keywords)

            # Decision logic: relevant if similarity >= threshold OR multiple keywords match
            is_relevant = (
                similarity >= self.threshold or 
                len(matched_keywords) >= self.min_keyword_matches
            )

            logger.debug(
                f"Classified '{directive.get('title', '')[:50]}...': "
                f"score={similarity:.3f}, keywords={len(matched_keywords)}, "
                f"relevant={is_relevant}"
            )

            return is_relevant, float(similarity), matched_keywords

        except Exception as e:
            logger.error(f"Classification error: {e}")
            return False, 0.0, []

    def _find_matched_keywords(self, text: str, keywords: List[str]) -> List[str]:
        """
        Find which keywords appear in the directive text

        Args:
            text: Directive text (lowercase)
            keywords: List of keywords to search

        Returns:
            List of matched keywords
        """
        matched = []
        try:
            for keyword in keywords:
                # Case-insensitive substring matching
                if keyword.lower() in text:
                    matched.append(keyword)

            # Remove duplicates and sort
            matched = sorted(list(set(matched)))

        except Exception as e:
            logger.debug(f"Error in keyword matching: {e}")

        return matched

    def classify_batch(self, directives: List[Dict]) -> List[Dict]:
        """
        Classify multiple directives in batch

        Args:
            directives: List of directive dictionaries

        Returns:
            List of directives with classification results added
        """
        logger.info(f"Classifying {len(directives)} directives")

        results = []
        relevant_count = 0

        for i, directive in enumerate(directives):
            is_relevant, score, matched = self.classify(directive)

            # Add classification results to directive
            directive['is_relevant'] = is_relevant
            directive['similarity_score'] = score
            directive['keywords_matched'] = json.dumps(matched)

            results.append(directive)

            if is_relevant:
                relevant_count += 1

        logger.info(
            f"Batch classification complete: "
            f"{relevant_count}/{len(directives)} classified as relevant"
        )

        return results

    def get_stats(self) -> Dict:
        """Get classifier statistics"""
        return {
            'threshold': self.threshold,
            'min_keyword_matches': self.min_keyword_matches,
            'keyword_categories': list(self.keywords.keys()),
            'total_keywords': sum(len(v) for v in self.keywords.values())
        }
