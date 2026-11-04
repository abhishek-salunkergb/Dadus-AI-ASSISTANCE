"""Universal disambiguation and multi-turn clarification engine for DADUS.
Eliminates hardcoded branching by resolving selections across options dynamically.
"""
import re
import logging
from typing import Optional, List, Dict, Any, Tuple
from app.agent.state import PendingClarification

logger = logging.getLogger("DADUS.ClarificationEngine")

class ClarificationEngine:
    """
    Universally resolves user choices against pending option sets.
    Handles exact names, substrings, unique distinguishing tokens (e.g. surnames),
    ordinal references ('first', '2nd', '3rd'), and relative choices ('the other one').
    """

    ORDINALS = [
        ("first", 0), ("1st", 0), ("#1", 0), (r"\b1\b", 0),
        ("second", 1), ("2nd", 1), ("#2", 1), (r"\b2\b", 1),
        ("third", 2), ("3rd", 2), ("#3", 2), (r"\b3\b", 2),
        ("fourth", 3), ("4th", 3), ("#4", 3), (r"\b4\b", 3),
        ("fifth", 4), ("5th", 4), ("#5", 4), (r"\b5\b", 4),
    ]

    @classmethod
    def is_cancellation(cls, text: str) -> bool:
        """Check if user wishes to abort the pending clarification."""
        lower = text.strip().lower()
        return bool(re.search(r"\b(?:cancel|nevermind|never\s+mind|stop|abort|don't|dont|nothing|no|drop\s+it)\b", lower))

    @classmethod
    def resolve_selection(cls, user_reply: str, options: List[str]) -> Optional[str]:
        """
        Dynamically matches user's natural reply against available options.
        Returns the matching option string if resolved, else None.
        """
        if not options:
            return None

        clean = user_reply.strip()
        lower = clean.lower()

        # 1. Exact match
        for opt in options:
            if opt.lower() == lower:
                return opt

        # 2. Relative selection ("the other one", "the other app", "the alternative", "the other option")
        if re.search(r"\b(?:the\s+other(?:\s+(?:one|app|application|option))?|alternative)\b", lower):
            if len(options) == 2:
                # If there are two options, pick the alternate option (index 1)
                return options[1]

        # 3. Substring match (e.g. user says "use Spotify please")
        for opt in options:
            if re.search(rf"\b{re.escape(opt.lower())}\b", lower):
                return opt

        # 4. Ordinal selection ("first", "second", "2nd", "the third option")
        for pattern, idx in cls.ORDINALS:
            if re.search(pattern if pattern.startswith(r"\b") else rf"\b{re.escape(pattern)}\b", lower) and idx < len(options):
                return options[idx]

        # 5. Unique token / surname matching (e.g. user just said "Chavhan")
        words = lower.split()
        token_frequencies: Dict[str, int] = {}
        for opt in options:
            for w in opt.lower().split():
                if len(w) > 2:
                    token_frequencies[w] = token_frequencies.get(w, 0) + 1

        for w in words:
            if len(w) > 2 and token_frequencies.get(w) == 1:
                for opt in options:
                    if w in opt.lower().split():
                        return opt

        return None

    @classmethod
    def apply_resolution(
        cls,
        pending: PendingClarification,
        chosen_option: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Updates the target tool's arguments with the resolved entity.
        Returns (tool_name, updated_arguments).
        """
        tool_name = pending.tool_name
        args = dict(pending.arguments)

        # Dynamic argument key assignment based on clarification type
        ctype = pending.clarification_type or ""
        if ctype == "contact_choice":
            args["contact_name"] = chosen_option
        elif ctype == "app_choice":
            args["application"] = chosen_option
        elif ctype == "file_choice":
            args["path"] = chosen_option
        elif ctype == "video_choice":
            args["query"] = chosen_option
        else:
            # Fallback: assign to primary entity argument
            if "contact_name" in args:
                args["contact_name"] = chosen_option
            elif "application" in args:
                args["application"] = chosen_option
            elif "app_name" in args:
                args["app_name"] = chosen_option
            else:
                args["selection"] = chosen_option

        return tool_name, args

    @classmethod
    def resolve_pending(
        cls,
        pending: PendingClarification,
        user_input: str
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str], bool]:
        """
        Processes a pending clarification with the user's input.
        Returns:
            (tool_name, tool_arguments, response_message, is_resolved)
            - If cancelled: (None, None, "Understood, boss. Cancelled.", False)
            - If successfully resolved: (tool_name, arguments, None, True)
            - If unresolved / ambiguous: (None, None, retry_prompt, False)
        """
        clean_text = user_input.strip().rstrip(".?!")
        lower_input = clean_text.lower()

        # 1. Cancellation
        if cls.is_cancellation(lower_input):
            return None, None, "Understood, boss. Cancelled.", False

        ctype = pending.clarification_type or "app_choice"
        target_tool = pending.tool_name

        # 2. Free-form song search prompts
        if ctype in ["song_choice", "spotify_song_choice"]:
            song_query = clean_text
            song_query = re.sub(r"^(?:ok|okay|yeah|yes|sure|hey dadus|dadus|please)[,\s]+", "", song_query, flags=re.IGNORECASE)
            song_query = re.sub(r"^(?:can you\s+)?(?:play|put on|search for|search|listen to|play the song|play song)\s+", "", song_query, flags=re.IGNORECASE)
            song_query = re.sub(r"\s+(?:song|track|video|in youtube|on youtube|in spotify|on spotify)\s*$", "", song_query, flags=re.IGNORECASE).strip(" .?!'\"")
            target_app = "Spotify" if "spotify" in ctype else "YouTube"
            if not song_query:
                song_query = pending.arguments.get("song") or "relaxing music"
            return "play_music", {"song": song_query, "application": target_app}, None, True

        # 3. Free-form video query prompts (if no fixed options matched)
        if ctype == "video_choice" and (not pending.options or not cls.resolve_selection(clean_text, pending.options)):
            show_query = clean_text
            show_query = re.sub(r"^(?:please\s+)?(?:watch|search for|search|play)\s+", "", show_query, flags=re.IGNORECASE).strip(" .?!'\"")
            args = dict(pending.arguments)
            args["query"] = show_query
            return target_tool, args, None, True

        # 4. Standard selection across options (contacts, apps, files, etc.)
        chosen = cls.resolve_selection(clean_text, pending.options)
        if chosen:
            tool_name, args = cls.apply_resolution(pending, chosen)
            return tool_name, args, None, True

        # 5. Unresolved: re-prompt user with available options
        if ctype == "contact_choice":
            retry_msg = f"Which contact did you mean, boss? {', '.join(pending.options)}."
        elif ctype == "app_choice":
            retry_msg = f"Boss, please specify: {', '.join(pending.options)}."
        else:
            retry_msg = f"Boss, which option did you mean? {', '.join(pending.options)}."

        return None, None, retry_msg, False
