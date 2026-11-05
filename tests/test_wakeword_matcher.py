"""Comprehensive tests for the high-precision phonetic WakeWordMatcher."""
import pytest
from app.voice.wakeword_matcher import WakeWordMatcher


def test_standard_wake_phrase_variations():
    """Verifies that clean and punctuated standard wake phrases are correctly identified."""
    test_cases = [
        ("Hey Dadus", True, ""),
        ("Hey, Dadus", True, ""),
        ("Hey, Dadus.", True, ""),
        ("hi dadus", True, ""),
        ("hello dadus", True, ""),
        ("ok dadus", True, ""),
        ("okay dadus", True, ""),
        ("Dadus", True, ""),
        ("dadus.", True, ""),
    ]
    for text, expected_match, expected_cmd in test_cases:
        matched, cmd = WakeWordMatcher.match(text)
        assert matched is expected_match, f"Failed match for '{text}'"
        assert cmd == expected_cmd, f"Expected cmd '{expected_cmd}' for '{text}', got '{cmd}'"


def test_inline_commands_with_wake_word():
    """Verifies that commands appended directly to the wake phrase are extracted accurately."""
    test_cases = [
        ("Hey Dadus open Chrome", True, "open Chrome"),
        ("Hey, Dadus, open VS Code and play music", True, "open VS Code and play music"),
        ("Dadus what time is it", True, "what time is it"),
        ("Hey Dadus, set an alarm for 7am", True, "set an alarm for 7am"),
        ("ok dadus lock my computer", True, "lock my computer"),
    ]
    for text, expected_match, expected_cmd in test_cases:
        matched, cmd = WakeWordMatcher.match(text)
        assert matched is expected_match, f"Failed match for '{text}'"
        assert cmd == expected_cmd, f"Expected cmd '{expected_cmd}' for '{text}', got '{cmd}'"


def test_phonetic_variations_of_assistant_name():
    """Verifies that common speech recognition phonetic mishearings of 'Dadus' match cleanly."""
    phonetic_cases = [
        ("Hey dadas", True, ""),
        ("Hey datus", True, ""),
        ("Hey dadu", True, ""),
        ("Hey daddus", True, ""),
        ("Hey dadis", True, ""),
        ("Hey deedus", True, ""),
        ("dadas open chrome", True, "open chrome"),
        ("Hey dad is here", True, "here"),  # Two-token compound split: 'dad is'
    ]
    for text, expected_match, expected_cmd in phonetic_cases:
        matched, cmd = WakeWordMatcher.match(text)
        assert matched is expected_match, f"Failed phonetic match for '{text}'"
        assert cmd == expected_cmd, f"Unexpected cmd for '{text}': got '{cmd}'"


def test_non_wake_phrases_rejected():
    """Verifies that general speech, similar-sounding words, or questions do not false-trigger."""
    reject_cases = [
        "Open Chrome",
        "What is the weather today?",
        "I have a headache",
        "Call the doctor",
        "What is your address?",
        "Clean the dust on the table",
        "Hey",
        "Hi there",
        "Okay let's go",
    ]
    for text in reject_cases:
        matched, _ = WakeWordMatcher.match(text)
        assert not matched, f"False trigger on '{text}'"


def test_lone_greeting_detection():
    """Verifies that standalone greeting words are identified for multi-chunk buffer stitching."""
    assert WakeWordMatcher.is_lone_greeting("Hey") is True
    assert WakeWordMatcher.is_lone_greeting("Hey,") is True
    assert WakeWordMatcher.is_lone_greeting("Hi") is True
    assert WakeWordMatcher.is_lone_greeting("Hello.") is True
    assert WakeWordMatcher.is_lone_greeting("Hey Dadus") is False
    assert WakeWordMatcher.is_lone_greeting("Open Chrome") is False
