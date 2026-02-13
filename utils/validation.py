"""Data validation utilities."""
import re
from typing import List, Dict, Any


def validate_scene_coverage(original_text, scenes, threshold=0.9):
    """
    Validate that scenes cover most of the original text.

    Returns:
        tuple: (coverage_ratio, missing_segments)
    """
    original_len = len(original_text)
    total_scene_len = sum(len(scene.get('text', '')) for scene in scenes)

    coverage = total_scene_len / original_len if original_len > 0 else 0

    # Simple coverage check - more sophisticated overlap detection could be added
    missing_segments = []
    if coverage < threshold:
        missing_segments.append({
            'message': f'Coverage only {coverage:.1%}, below threshold {threshold:.1%}',
            'expected': original_len,
            'actual': total_scene_len
        })

    return coverage, missing_segments


def validate_scene_overlap(scenes):
    """
    Check for significant overlap between adjacent scenes.

    Returns:
        List of warnings about overlapping scenes
    """
    warnings = []

    for i in range(len(scenes) - 1):
        text1 = scenes[i].get('text', '')
        text2 = scenes[i + 1].get('text', '')

        # Check if end of scene1 overlaps with start of scene2
        overlap_window = min(100, len(text1) // 4, len(text2) // 4)

        if overlap_window > 0:
            end_snippet = text1[-overlap_window:]
            start_snippet = text2[:overlap_window]

            # Simple overlap detection
            if end_snippet in text2 or start_snippet in text1:
                warnings.append({
                    'scene1_index': scenes[i].get('scene_index'),
                    'scene2_index': scenes[i + 1].get('scene_index'),
                    'message': 'Potential overlap detected'
                })

    return warnings


def validate_scene_lengths(scenes, min_length, max_length):
    """
    Validate scene lengths are within acceptable range.

    Returns:
        List of scenes with length issues
    """
    issues = []

    for scene in scenes:
        char_count = scene.get('char_count', 0)
        scene_index = scene.get('scene_index', -1)

        if char_count < min_length * 0.5:
            issues.append({
                'scene_index': scene_index,
                'char_count': char_count,
                'issue': 'too_short',
                'message': f'Scene is too short ({char_count} chars, min {min_length * 0.5})'
            })

        if char_count > max_length * 1.5:
            issues.append({
                'scene_index': scene_index,
                'char_count': char_count,
                'issue': 'too_long',
                'message': f'Scene is too long ({char_count} chars, max {max_length * 1.5})'
            })

    return issues


def validate_scene_order(scenes):
    """Validate scenes are in correct order."""
    issues = []

    for i, scene in enumerate(scenes):
        expected_index = i
        actual_index = scene.get('scene_index', -1)

        if actual_index != expected_index:
            issues.append({
                'position': i,
                'expected_index': expected_index,
                'actual_index': actual_index,
                'message': f'Scene index mismatch at position {i}'
            })

    return issues


def validate_metadata(metadata):
    """
    Validate metadata structure and required fields.

    Returns:
        List of validation errors
    """
    errors = []

    # Required fields
    required_fields = ['characters', 'location', 'event_summary', 'plot_significance']

    for field in required_fields:
        if field not in metadata:
            errors.append(f'Missing required field: {field}')
        elif not metadata[field]:
            errors.append(f'Empty required field: {field}')

    # Validate characters is a list
    if 'characters' in metadata:
        if not isinstance(metadata['characters'], list):
            errors.append('characters must be a list')
        elif len(metadata['characters']) == 0:
            errors.append('characters list cannot be empty')

    # Validate plot_significance
    if 'plot_significance' in metadata:
        valid_values = ['high', 'medium', 'low']
        if metadata['plot_significance'] not in valid_values:
            errors.append(f'plot_significance must be one of {valid_values}')

    # Validate key_dialogues is a list if present
    if 'key_dialogues' in metadata and not isinstance(metadata['key_dialogues'], list):
        errors.append('key_dialogues must be a list')

    # Validate character_relations is a list if present
    if 'character_relations' in metadata and not isinstance(metadata['character_relations'], list):
        errors.append('character_relations must be a list')

    return errors


def validate_json_structure(data, schema):
    """
    Validate JSON data against a simple schema.

    Args:
        data: The data to validate
        schema: Dict describing required structure

    Returns:
        List of validation errors
    """
    errors = []

    if not isinstance(data, dict):
        return ['Data must be a dictionary']

    for field, field_type in schema.items():
        if field not in data:
            errors.append(f'Missing required field: {field}')
        elif not isinstance(data[field], field_type):
            errors.append(f'Field {field} must be of type {field_type.__name__}')

    return errors


def validate_character_names(characters, name_map):
    """
    Validate that character names are in the normalization map.

    Returns:
        List of unknown character names
    """
    unknown_names = []

    all_known_names = set()
    for canonical, aliases in name_map.items():
        all_known_names.add(canonical)
        all_known_names.update(aliases)

    for char in characters:
        if char not in all_known_names:
            unknown_names.append(char)

    return unknown_names
