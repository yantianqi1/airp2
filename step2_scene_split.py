"""Step 2: Split chapters into scenes using LLM."""
import os
import json
import logging
from utils.llm_client import LLMClient
from utils.text_utils import read_text_file, find_sentence_end
from utils.fuzzy_match import fuzzy_find_text, validate_marker_order
from utils.validation import (
    validate_scene_coverage,
    validate_scene_overlap,
    validate_scene_lengths,
    validate_scene_order,
)


logger = logging.getLogger(__name__)


def should_run_step2(status, force=False, redo=False):
    """Decide whether step2 should process a chapter."""
    if force or redo:
        return True

    # scenes_done means split already done; annotated/vectorized are downstream
    # states and should not be regressed by default reruns.
    return status not in {'scenes_done', 'annotated_done', 'vectorized'}


class SceneSplitter:
    """Split chapters into scenes using LLM."""

    def __init__(self, config):
        """Initialize with config."""
        self.config = config
        self.llm_client = LLMClient(config)

        self.min_length = config['scene_split']['min_length']
        self.max_length = config['scene_split']['max_length']
        self.target_length = config['scene_split']['target_length']
        self.coverage_threshold = config['scene_split']['coverage_threshold']

        self.scenes_dir = config['paths']['scenes_dir']
        os.makedirs(self.scenes_dir, exist_ok=True)

    def split_chapter(self, chapter_file, chapter_id, chapter_title):
        """
        Split a single chapter into scenes.

        Returns:
            Path to scenes JSON file
        """
        logger.info(f"Processing chapter: {chapter_id} - {chapter_title}")

        # Read chapter text
        chapter_text = read_text_file(chapter_file)
        chapter_length = len(chapter_text)

        logger.info(f"Chapter length: {chapter_length} characters")

        # Estimate number of scenes needed
        estimated_scenes = max(1, chapter_length // self.target_length)

        # Call LLM to get scene markers
        scene_markers = self._get_scene_markers(chapter_text, estimated_scenes)

        # Locate and extract scenes based on markers
        scenes = self._extract_scenes(chapter_text, scene_markers)

        # Validate coverage
        coverage, missing = validate_scene_coverage(
            chapter_text, scenes, self.coverage_threshold
        )
        if missing:
            logger.warning(f"Coverage issues for {chapter_id}: {missing}")

        logger.info(f"Coverage: {coverage:.1%}")

        # Handle missing segments
        if coverage < self.coverage_threshold:
            logger.warning(f"Coverage below threshold, adding missing segments")
            scenes = self._fill_missing_segments(chapter_text, scenes)
            coverage, _ = validate_scene_coverage(chapter_text, scenes, 0)
            logger.info(f"Coverage after filling: {coverage:.1%}")

        # Validate and fix scene lengths
        scenes = self._validate_and_fix_lengths(scenes)
        order_issues = validate_scene_order(scenes)
        overlap_warnings = validate_scene_overlap(scenes)
        if order_issues:
            logger.warning(f"Scene order issues for {chapter_id}: {order_issues}")
        if overlap_warnings:
            logger.warning(f"Scene overlap warnings for {chapter_id}: {overlap_warnings}")

        # Prepare output
        output = {
            'source_file': os.path.basename(chapter_file),
            'chapter_id': chapter_id,
            'chapter_title': chapter_title,
            'total_scenes': len(scenes),
            'coverage_rate': coverage,
            'scenes': scenes
        }

        # Save to file
        output_file = os.path.join(self.scenes_dir, f"{chapter_id}_scenes.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(scenes)} scenes to {output_file}")

        return output_file

    def _get_scene_markers(self, text, estimated_scenes):
        """Call LLM to get scene split markers."""
        prompt = f"""请将以下章节文本按场景切分，返回每个场景的起止标记。

切分标准：
1. 地点变化
2. 时间跳跃
3. 人物组合变化
4. 事件转换

目标：每个场景约 {self.target_length} 字，最少 {self.min_length} 字，最多 {self.max_length} 字。
预估需要切分成 {estimated_scenes} 个左右的场景。

文本：
{text}

返回 JSON 格式，包含 scenes 数组，每个场景包含：
- start_marker: 场景开头的一句原文（15-30字）
- end_marker: 场景结尾的一句原文（15-30字）
- scene_summary: 一句话概括场景内容

示例：
{{
  "scenes": [
    {{
      "start_marker": "这里是场景开头的原文",
      "end_marker": "这里是场景结尾的原文",
      "scene_summary": "简短概括场景内容"
    }}
  ]
}}
"""

        try:
            response = self.llm_client.call(
                prompt=prompt,
                response_format={"type": "json_object"}
            )

            if isinstance(response, dict) and 'scenes' in response:
                return response['scenes']
            else:
                logger.error(f"Unexpected response format: {response}")
                return []

        except Exception as e:
            logger.error(f"Failed to get scene markers: {e}")
            # Fallback: split by length
            return self._fallback_split_by_length(text)

    def _fallback_split_by_length(self, text):
        """Fallback: simple split by target length."""
        scenes = []
        pos = 0

        while pos < len(text):
            # Find next split point
            next_pos = min(pos + self.target_length, len(text))

            # Extend to sentence end
            if next_pos < len(text):
                next_pos = find_sentence_end(text, next_pos)

            # Extract markers
            segment = text[pos:next_pos]
            lines = [l.strip() for l in segment.split('\n') if l.strip()]

            start_marker = lines[0][:30] if lines else ""
            end_marker = lines[-1][-30:] if lines else ""

            scenes.append({
                'start_marker': start_marker,
                'end_marker': end_marker,
                'scene_summary': f'场景片段 {len(scenes) + 1}'
            })

            pos = next_pos

        logger.warning(f"Using fallback split: {len(scenes)} scenes")
        return scenes

    def _extract_scenes(self, text, markers):
        """Extract scene text based on markers."""
        scenes = []

        for i, marker in enumerate(markers):
            start_marker = marker.get('start_marker', '')
            end_marker = marker.get('end_marker', '')
            summary = marker.get('scene_summary', '')

            start_pos = -1
            end_pos = -1

            # Prefer validated marker order when both markers are available.
            if start_marker and end_marker:
                validated_start, validated_end, is_valid = validate_marker_order(
                    text, start_marker, end_marker, threshold=0.7
                )
                if is_valid:
                    start_pos = validated_start
                    end_pos = validated_end

            if start_pos == -1:
                start_pos = fuzzy_find_text(text, start_marker, threshold=0.7)
            if end_pos == -1:
                end_pos = fuzzy_find_text(text, end_marker, threshold=0.7)

            if start_pos == -1:
                logger.warning(f"Could not find start marker for scene {i}: {start_marker[:50]}")
                continue

            if end_pos == -1:
                logger.warning(f"Could not find end marker for scene {i}: {end_marker[:50]}")
                # Try to use next scene's start as this scene's end
                if i < len(markers) - 1:
                    next_start = markers[i + 1].get('start_marker', '')
                    end_pos = fuzzy_find_text(text, next_start, threshold=0.7)
                    if end_pos != -1:
                        end_pos = end_pos - 1
                    else:
                        continue
                else:
                    end_pos = len(text)

            # Ensure start before end
            if start_pos >= end_pos:
                logger.warning(f"Invalid marker positions for scene {i}")
                continue

            # Extend end to sentence boundary
            end_pos = find_sentence_end(text, end_pos)

            # Extract text
            scene_text = text[start_pos:end_pos].strip()

            scenes.append({
                'scene_index': len(scenes),
                'text': scene_text,
                'char_count': len(scene_text),
                'scene_summary': summary
            })

        return scenes

    def _fill_missing_segments(self, text, scenes):
        """Find and add missing text segments."""
        if not scenes:
            # No scenes at all, return entire text as one scene
            return [{
                'scene_index': 0,
                'text': text,
                'char_count': len(text),
                'scene_summary': '完整章节'
            }]

        # Sort scenes by position in text
        scenes_with_pos = []
        for scene in scenes:
            pos = text.find(scene['text'][:50])
            if pos != -1:
                scenes_with_pos.append((pos, scene))

        scenes_with_pos.sort(key=lambda x: x[0])

        # Find gaps
        filled_scenes = []
        current_pos = 0

        for pos, scene in scenes_with_pos:
            # Check for gap before this scene
            if pos > current_pos + 50:
                gap_text = text[current_pos:pos].strip()
                if len(gap_text) > self.min_length // 2:
                    filled_scenes.append({
                        'scene_index': len(filled_scenes),
                        'text': gap_text,
                        'char_count': len(gap_text),
                        'scene_summary': f'补充片段 {len(filled_scenes)}'
                    })

            # Add the scene
            scene['scene_index'] = len(filled_scenes)
            filled_scenes.append(scene)
            current_pos = pos + len(scene['text'])

        # Check for gap after last scene
        if current_pos < len(text) - 50:
            gap_text = text[current_pos:].strip()
            if len(gap_text) > self.min_length // 2:
                filled_scenes.append({
                    'scene_index': len(filled_scenes),
                    'text': gap_text,
                    'char_count': len(gap_text),
                    'scene_summary': f'补充片段 {len(filled_scenes)}'
                })

        return filled_scenes

    def _validate_and_fix_lengths(self, scenes):
        """Validate and fix scene lengths."""
        issues = validate_scene_lengths(scenes, self.min_length, self.max_length)

        if not issues:
            return scenes

        # Fix issues
        fixed_scenes = []

        for i, scene in enumerate(scenes):
            char_count = scene['char_count']

            # Too long - split it
            if char_count > self.max_length * 1.5:
                logger.warning(f"Scene {i} too long ({char_count}), splitting")
                sub_scenes = self._split_long_scene(scene)
                fixed_scenes.extend(sub_scenes)

            # Too short - try to merge with adjacent
            elif char_count < self.min_length * 0.5 and i > 0 and i < len(scenes) - 1:
                logger.warning(f"Scene {i} too short ({char_count}), merging with previous")
                if fixed_scenes:
                    prev_scene = fixed_scenes[-1]
                    prev_scene['text'] += '\n' + scene['text']
                    prev_scene['char_count'] = len(prev_scene['text'])
                    prev_scene['scene_summary'] += '; ' + scene['scene_summary']
                else:
                    fixed_scenes.append(scene)

            else:
                fixed_scenes.append(scene)

        # Reindex
        for i, scene in enumerate(fixed_scenes):
            scene['scene_index'] = i

        return fixed_scenes

    def _split_long_scene(self, scene):
        """Split a scene that's too long."""
        text = scene['text']
        target = self.target_length

        # Split by paragraphs first
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        sub_scenes = []
        current_text = []
        current_length = 0

        for para in paragraphs:
            para_len = len(para)

            if current_length + para_len > target and current_text:
                # Save current sub-scene
                sub_text = '\n\n'.join(current_text)
                sub_scenes.append({
                    'scene_index': len(sub_scenes),
                    'text': sub_text,
                    'char_count': len(sub_text),
                    'scene_summary': f"{scene['scene_summary']} (部分{len(sub_scenes)+1})"
                })

                current_text = [para]
                current_length = para_len
            else:
                current_text.append(para)
                current_length += para_len

        # Add remaining
        if current_text:
            sub_text = '\n\n'.join(current_text)
            sub_scenes.append({
                'scene_index': len(sub_scenes),
                'text': sub_text,
                'char_count': len(sub_text),
                'scene_summary': f"{scene['scene_summary']} (部分{len(sub_scenes)+1})"
            })

        return sub_scenes if sub_scenes else [scene]


def run_step2(config, force=False, redo_chapter=None):
    """Run step 2: scene splitting."""
    chapters_dir = config['paths']['chapters_dir']
    index_file = os.path.join(chapters_dir, 'chapter_index.json')

    if not os.path.exists(index_file):
        logger.error("Chapter index not found. Run step 1 first.")
        return

    # Load chapter index
    with open(index_file, 'r', encoding='utf-8') as f:
        index_data = json.load(f)

    splitter = SceneSplitter(config)

    # Process each chapter
    chapters = index_data['chapters']
    for chapter_info in chapters:
        chapter_id = chapter_info['chapter_id']
        current_status = chapter_info.get('status')

        # Check if should process this chapter
        if redo_chapter is not None and chapter_id != f"chapter_{redo_chapter:04d}":
            continue

        if not should_run_step2(
            current_status,
            force=force,
            redo=redo_chapter is not None
        ):
            logger.info(f"Chapter {chapter_id} already processed, skipping")
            continue

        # Process chapter
        chapter_file = os.path.join(chapters_dir, chapter_info['file'])

        try:
            scenes_file = splitter.split_chapter(
                chapter_file,
                chapter_id,
                chapter_info['title']
            )

            # Update status
            chapter_info['status'] = 'scenes_done'
            chapter_info['scenes_file'] = os.path.basename(scenes_file)
            # Downstream outputs become stale after re-splitting.
            chapter_info.pop('annotated_file', None)

        except Exception as e:
            logger.error(f"Failed to process chapter {chapter_id}: {e}")
            chapter_info['status'] = 'scenes_failed'

    # Save updated index
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    logger.info("Step 2 complete")


if __name__ == '__main__':
    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    run_step2(config, force=True)
