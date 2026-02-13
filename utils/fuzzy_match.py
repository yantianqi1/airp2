"""Fuzzy matching utilities."""
from thefuzz import fuzz
import re


def fuzzy_find_text(full_text, marker, threshold=0.7, context_window=50):
    """
    Find text marker in full text using fuzzy matching.

    Args:
        full_text: The full text to search in
        marker: The text marker to find
        threshold: Similarity threshold (0-1)
        context_window: Number of characters to use as sliding window

    Returns:
        Position of best match, or -1 if no match found
    """
    if not marker or not full_text:
        return -1

    marker_len = len(marker)
    best_ratio = 0
    best_pos = -1

    # Try exact match first
    exact_pos = full_text.find(marker)
    if exact_pos != -1:
        return exact_pos

    # Normalize marker for comparison
    marker_normalized = normalize_for_matching(marker)

    # Sliding window fuzzy search
    step = max(1, marker_len // 4)  # Overlap windows for better coverage

    for i in range(0, len(full_text) - marker_len + 1, step):
        window = full_text[i:i + marker_len]
        window_normalized = normalize_for_matching(window)

        # Use partial ratio for better matching
        ratio = fuzz.partial_ratio(marker_normalized, window_normalized) / 100.0

        if ratio > best_ratio:
            best_ratio = ratio
            best_pos = i

    if best_ratio >= threshold:
        return best_pos

    return -1


def normalize_for_matching(text):
    """Normalize text for fuzzy matching."""
    # Remove extra whitespace
    text = re.sub(r'\s+', '', text)

    # Convert to lowercase for better matching
    text = text.lower()

    return text


def find_best_match_position(full_text, marker, threshold=0.7):
    """
    Find the best matching position for a marker in full text.

    Returns:
        tuple: (position, confidence_score)
    """
    pos = fuzzy_find_text(full_text, marker, threshold)

    if pos == -1:
        return -1, 0.0

    # Calculate confidence
    window = full_text[pos:pos + len(marker)]
    confidence = fuzz.ratio(normalize_for_matching(marker),
                           normalize_for_matching(window)) / 100.0

    return pos, confidence


def validate_marker_order(full_text, start_marker, end_marker, threshold=0.7):
    """
    Validate that start_marker appears before end_marker in text.

    Returns:
        tuple: (start_pos, end_pos, is_valid)
    """
    start_pos, start_conf = find_best_match_position(full_text, start_marker, threshold)
    end_pos, end_conf = find_best_match_position(full_text, end_marker, threshold)

    if start_pos == -1 or end_pos == -1:
        return start_pos, end_pos, False

    # Start must come before end
    is_valid = start_pos < end_pos

    return start_pos, end_pos, is_valid
