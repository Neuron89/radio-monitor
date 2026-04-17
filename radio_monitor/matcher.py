"""Keyword matching with fuzzy support for handling Whisper misheard words."""
import logging
from rapidfuzz import fuzz

log = logging.getLogger(__name__)


class KeywordMatcher:
    """Matches transcribed text against configured keywords."""

    def __init__(self, config: dict):
        self.keywords = [kw.lower() for kw in config["keywords"]]
        self.threshold = config.get("match_threshold", 70)

    def check(self, text: str) -> list[dict]:
        """Check text for keyword matches. Returns list of match dicts."""
        if not text:
            return []

        text_lower = text.lower()
        words = text_lower.split()
        matches = []

        for keyword in self.keywords:
            # Exact substring match
            if keyword in text_lower:
                matches.append({
                    "keyword": keyword,
                    "matched_text": keyword,
                    "score": 100,
                    "method": "exact",
                })
                continue

            # Fuzzy match against individual words
            for word in words:
                score = fuzz.ratio(keyword, word)
                if score >= self.threshold:
                    matches.append({
                        "keyword": keyword,
                        "matched_text": word,
                        "score": score,
                        "method": "fuzzy",
                    })
                    break

            # Fuzzy match against word pairs (for two-word keywords)
            if len(keyword.split()) > 1:
                for i in range(len(words) - 1):
                    pair = f"{words[i]} {words[i + 1]}"
                    score = fuzz.ratio(keyword, pair)
                    if score >= self.threshold:
                        matches.append({
                            "keyword": keyword,
                            "matched_text": pair,
                            "score": score,
                            "method": "fuzzy_pair",
                        })
                        break

        if matches:
            log.info(f"Matches found: {matches}")

        return matches
