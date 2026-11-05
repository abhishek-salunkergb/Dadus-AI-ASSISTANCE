"""High-precision, principled phonetic wake-phrase analyzer for DADUS.
Replaces fragile ad-hoc regexes with principled tokenization, phonetic
distance, and greeting-name grammatical structure.
"""
import re
from typing import Tuple, Set


class WakeWordMatcher:
    """Principled phonetic and acoustic classifier for DADUS wake-word detection."""

    GREETINGS: Set[str] = {"hey", "hi", "hello", "ok", "okay", "yo"}
    ASSISTANT_NAME: str = "dadus"
    PHONETIC_CANONICAL: Set[str] = {
        "dadus", "dadas", "datus", "dadu", "daddus", "dadis", "deedus", "daydus", "tatus"
    }

    @classmethod
    def is_name_token(cls, token: str) -> bool:
        """Determines if a word matches 'Dadus' phonetically or within Levenshtein distance 1."""
        clean = re.sub(r"[^\w]", "", token.lower())
        if not clean:
            return False
        if clean in cls.PHONETIC_CANONICAL:
            return True
        if len(clean) >= 4 and cls._levenshtein(clean, cls.ASSISTANT_NAME) <= 1:
            return True
        return False

    @classmethod
    def match(cls, text: str) -> Tuple[bool, str]:
        """
        Analyzes utterance for wake phrase:
        1. [Greeting] + [Dadus] + [Inline Command...]
        2. [Dadus] + [Inline Command...]
        3. 'Hey Dad is...' compound split
        Returns (is_wake_detected, inline_command).
        """
        clean = text.strip()
        tokens = re.sub(r"[,.?!\'\"]", " ", clean).lower().split()
        if not tokens:
            return False, ""

        # Pattern 1: Greeting + Name
        if tokens[0] in cls.GREETINGS:
            if len(tokens) >= 2 and cls.is_name_token(tokens[1]):
                rest_pattern = re.compile(rf"^\s*{re.escape(tokens[0])}\W+{re.escape(tokens[1])}\W*", re.IGNORECASE)
                cmd = rest_pattern.sub("", clean).strip(" ,.?!")
                return True, cmd

            # Two-token split: e.g. "hey dad is" or "hey dad us"
            if len(tokens) >= 3 and tokens[1] == "dad" and tokens[2] in ["is", "us"]:
                rest_pattern = re.compile(rf"^\s*{re.escape(tokens[0])}\W+dad\W+{re.escape(tokens[2])}\W*", re.IGNORECASE)
                cmd = rest_pattern.sub("", clean).strip(" ,.?!")
                return True, cmd

        # Pattern 2: Standalone Name
        if cls.is_name_token(tokens[0]):
            rest_pattern = re.compile(rf"^\s*{re.escape(tokens[0])}\W*", re.IGNORECASE)
            cmd = rest_pattern.sub("", clean).strip(" ,.?!")
            return True, cmd

        # Pattern 3: Standalone two-token split: "dad is" or "dad us"
        if len(tokens) >= 2 and tokens[0] == "dad" and tokens[1] in ["is", "us"]:
            rest_pattern = re.compile(r"^\s*dad\W+(?:is|us)\W*", re.IGNORECASE)
            cmd = rest_pattern.sub("", clean).strip(" ,.?!")
            return True, cmd

        return False, ""

    @classmethod
    def is_lone_greeting(cls, text: str) -> bool:
        """Checks if utterance is solely an isolated greeting like 'Hey,' or 'Hi'."""
        tokens = re.sub(r"[^\w\s]", "", text.lower()).split()
        return len(tokens) == 1 and tokens[0] in cls.GREETINGS

    @staticmethod
    def _levenshtein(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return WakeWordMatcher._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                ins = prev[j + 1] + 1
                dels = curr[j] + 1
                sub = prev[j] + (c1 != c2)
                curr.append(min(ins, dels, sub))
            prev = curr
        return prev[-1]
