"""Step 3: Annotate scenes with metadata using LLM."""
import os
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.llm_client import LLMClient
from utils.validation import validate_metadata


logger = logging.getLogger(__name__)


def should_run_step3(status, force=False, redo=False):
    """Decide whether step3 should process a chapter."""
    if force or redo:
        return status in {
            'scenes_done',
            'annotated_done',
            'annotation_failed',
            'vectorized',
            'vectorize_failed',
        }

    return status == 'scenes_done'


class SceneAnnotator:
    """Annotate scenes with metadata."""

    def __init__(self, config):
        """Initialize with config."""
        self.config = config
        self.llm_client = LLMClient(config)
        self.concurrent_requests = max(
            1,
            int(config.get('llm', {}).get('concurrent_requests', 1) or 1),
        )
        self._thread_local = threading.local()

        self.batch_size = config['annotation']['batch_size']
        self.short_scene_threshold = config['annotation']['short_scene_threshold']

        self.annotated_dir = config['paths']['annotated_dir']
        os.makedirs(self.annotated_dir, exist_ok=True)

    def _get_thread_llm_client(self):
        """Get (or create) a per-thread LLM client for concurrent calls."""
        client = getattr(self._thread_local, 'llm_client', None)
        if client is None:
            client = LLMClient(self.config)
            self._thread_local.llm_client = client
        return client

    def annotate_chapter(self, scenes_file, chapter_id):
        """
        Annotate all scenes in a chapter.

        Returns:
            Path to annotated JSON file
        """
        logger.info(f"Annotating chapter: {chapter_id}")

        # Load scenes
        with open(scenes_file, 'r', encoding='utf-8') as f:
            scenes_data = json.load(f)

        scenes = scenes_data['scenes']
        logger.info(f"Processing {len(scenes)} scenes")

        # Annotate scenes in batches
        annotated_scenes = []

        if self.concurrent_requests > 1:
            with ThreadPoolExecutor(max_workers=self.concurrent_requests) as executor:
                for i in range(0, len(scenes), self.batch_size):
                    batch = scenes[i:i + self.batch_size]
                    batch_annotations = self._annotate_batch(batch, executor=executor)

                    for scene, metadata in zip(batch, batch_annotations):
                        scene['metadata'] = metadata
                        annotated_scenes.append(scene)
        else:
            for i in range(0, len(scenes), self.batch_size):
                batch = scenes[i:i + self.batch_size]
                batch_annotations = self._annotate_batch(batch, executor=None)

                for scene, metadata in zip(batch, batch_annotations):
                    scene['metadata'] = metadata
                    annotated_scenes.append(scene)

        # Normalize character names across all scenes
        annotated_scenes = self._normalize_character_names(annotated_scenes)

        # Prepare output
        scenes_data['scenes'] = annotated_scenes

        # Save to file
        output_file = os.path.join(self.annotated_dir, f"{chapter_id}_annotated.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(scenes_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved annotated scenes to {output_file}")

        return output_file

    def _annotate_batch(self, scenes, executor=None):
        """Annotate a batch of scenes."""
        # Check if batch can be combined (all scenes are short)
        total_chars = sum(s['char_count'] for s in scenes)

        if len(scenes) > 1 and total_chars < self.short_scene_threshold * len(scenes):
            # Combine into single prompt
            return self._annotate_batch_combined(scenes)
        else:
            # Annotate individually
            if executor is None:
                return [self._annotate_single(scene) for scene in scenes]

            results = [None] * len(scenes)
            futures = {
                executor.submit(self._annotate_single, scene): idx
                for idx, scene in enumerate(scenes)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Failed to annotate scene in parallel: {e}")
                    results[idx] = self._get_empty_metadata()
            return results

    def _annotate_single(self, scene):
        """Annotate a single scene."""
        prompt = f"""请为以下场景片段提取元数据，返回 JSON 格式。

场景文本：
{scene['text']}

需要提取的字段：
- characters: 出场人物名单（数组，使用全名）
- location: 地点
- time_description: 时间描述
- event_summary: 一句话事件概括
- emotion_tone: 情感基调（如：欢快、悲伤、紧张、平静等）
- key_dialogues: 重要对白原文（数组，1-3句）
- character_relations: 人物关系描述（数组，如"张三与李四是师徒关系"）
- plot_significance: 情节重要性（high/medium/low）

返回格式示例：
{{
  "characters": ["张三", "李四"],
  "location": "书房",
  "time_description": "深夜",
  "event_summary": "张三向李四请教武功",
  "emotion_tone": "严肃",
  "key_dialogues": ["师父，这招该如何破解？"],
  "character_relations": ["张三是李四的徒弟"],
  "plot_significance": "medium"
}}
"""

        try:
            llm_client = self._get_thread_llm_client()
            metadata = llm_client.call(
                prompt=prompt,
                model=self.config['llm']['annotate_model'],
                response_format={"type": "json_object"}
            )

            # Validate
            errors = validate_metadata(metadata)
            if errors:
                logger.warning(f"Metadata validation errors: {errors}")
                # Fill in missing fields with defaults
                metadata = self._fill_default_metadata(metadata)

            return metadata

        except Exception as e:
            logger.error(f"Failed to annotate scene: {e}")
            return self._get_empty_metadata()

    def _annotate_batch_combined(self, scenes):
        """Annotate multiple short scenes in one call."""
        scenes_text = ""
        for i, scene in enumerate(scenes):
            scenes_text += f"\n\n=== 场景 {i+1} ===\n{scene['text']}"

        prompt = f"""请为以下 {len(scenes)} 个场景片段分别提取元数据，返回 JSON 格式。

场景文本：
{scenes_text}

返回格式为包含 scenes 数组的 JSON，每个场景包含：
- characters: 出场人物名单（数组）
- location: 地点
- time_description: 时间描述
- event_summary: 一句话事件概括
- emotion_tone: 情感基调
- key_dialogues: 重要对白（数组）
- character_relations: 人物关系（数组）
- plot_significance: high/medium/low

示例：
{{
  "scenes": [
    {{
      "characters": ["张三"],
      "location": "书房",
      ...
    }},
    {{
      "characters": ["李四"],
      "location": "大厅",
      ...
    }}
  ]
}}
"""

        try:
            response = self.llm_client.call(
                prompt=prompt,
                model=self.config['llm']['annotate_model'],
                response_format={"type": "json_object"}
            )

            if 'scenes' in response and len(response['scenes']) == len(scenes):
                return response['scenes']
            else:
                logger.warning(f"Batch response format incorrect, falling back to individual")
                return [self._annotate_single(scene) for scene in scenes]

        except Exception as e:
            logger.error(f"Failed to annotate batch: {e}")
            return [self._annotate_single(scene) for scene in scenes]

    def _normalize_character_names(self, scenes):
        """Normalize character names across all scenes."""
        # Collect all character names
        all_characters = set()
        for scene in scenes:
            if 'metadata' in scene and 'characters' in scene['metadata']:
                all_characters.update(scene['metadata']['characters'])

        if not all_characters:
            return scenes

        # Call LLM to generate normalization map
        name_map = self._generate_name_normalization_map(list(all_characters))

        # Apply normalization
        for scene in scenes:
            if 'metadata' in scene and 'characters' in scene['metadata']:
                normalized = []
                for char in scene['metadata']['characters']:
                    canonical = self._find_canonical_name(char, name_map)
                    if canonical and canonical not in normalized:
                        normalized.append(canonical)
                scene['metadata']['characters'] = normalized

        return scenes

    def _generate_name_normalization_map(self, characters):
        """Generate character name normalization map using LLM."""
        prompt = f"""以下是从小说中提取的人物名称列表，请将它们归一化，把同一个人物的不同称呼合并。

人物名称：
{json.dumps(characters, ensure_ascii=False)}

返回 JSON 格式的映射表，键是规范全名，值是该人物的所有别名/简称的数组。

示例：
{{
  "贾宝玉": ["宝玉", "宝二爷", "贾宝玉"],
  "林黛玉": ["黛玉", "林姑娘", "颦儿", "林黛玉"]
}}
"""

        try:
            name_map = self.llm_client.call(
                prompt=prompt,
                model=self.config['llm']['annotate_model'],
                response_format={"type": "json_object"}
            )

            # Save name map for reference
            name_map_file = os.path.join(
                self.config['paths']['annotated_dir'],
                'character_name_map.json'
            )
            with open(name_map_file, 'w', encoding='utf-8') as f:
                json.dump(name_map, f, ensure_ascii=False, indent=2)

            logger.info(f"Character name map saved to {name_map_file}")

            return name_map

        except Exception as e:
            logger.error(f"Failed to generate name map: {e}")
            # Return identity map
            return {char: [char] for char in characters}

    def _find_canonical_name(self, name, name_map):
        """Find canonical name for a character."""
        # Check if name is already canonical
        if name in name_map:
            return name

        # Check if name is an alias
        for canonical, aliases in name_map.items():
            if name in aliases:
                return canonical

        # Not found, return original
        return name

    def _fill_default_metadata(self, metadata):
        """Fill missing metadata fields with defaults."""
        defaults = {
            'characters': [],
            'location': '未知',
            'time_description': '未知',
            'event_summary': '场景描述',
            'emotion_tone': '中性',
            'key_dialogues': [],
            'character_relations': [],
            'plot_significance': 'medium'
        }

        for key, default_value in defaults.items():
            if key not in metadata or not metadata[key]:
                metadata[key] = default_value

        return metadata

    def _get_empty_metadata(self):
        """Get empty metadata with default values."""
        return {
            'characters': [],
            'location': '未知',
            'time_description': '未知',
            'event_summary': '场景描述',
            'emotion_tone': '中性',
            'key_dialogues': [],
            'character_relations': [],
            'plot_significance': 'medium'
        }


def run_step3(config, force=False, redo_chapter=None):
    """Run step 3: metadata annotation."""
    chapters_dir = config['paths']['chapters_dir']
    scenes_dir = config['paths']['scenes_dir']
    index_file = os.path.join(chapters_dir, 'chapter_index.json')

    if not os.path.exists(index_file):
        logger.error("Chapter index not found. Run previous steps first.")
        return

    # Load chapter index
    with open(index_file, 'r', encoding='utf-8') as f:
        index_data = json.load(f)

    annotator = SceneAnnotator(config)

    # Process each chapter
    chapters = index_data['chapters']
    for chapter_info in chapters:
        chapter_id = chapter_info['chapter_id']
        current_status = chapter_info.get('status')

        # Check if should process this chapter
        if redo_chapter is not None and chapter_id != f"chapter_{redo_chapter:04d}":
            continue

        if not should_run_step3(
            current_status,
            force=force,
            redo=redo_chapter is not None
        ):
            if current_status in {'annotated_done', 'vectorized'}:
                logger.info(f"Chapter {chapter_id} already annotated, skipping")
            else:
                logger.warning(f"Chapter {chapter_id} scenes not ready, skipping")
            continue

        # Process chapter
        scenes_file = os.path.join(scenes_dir, chapter_info.get('scenes_file', ''))

        if not os.path.exists(scenes_file):
            logger.error(f"Scenes file not found: {scenes_file}")
            continue

        try:
            annotated_file = annotator.annotate_chapter(scenes_file, chapter_id)

            # Update status
            chapter_info['status'] = 'annotated_done'
            chapter_info['annotated_file'] = os.path.basename(annotated_file)

        except Exception as e:
            logger.error(f"Failed to annotate chapter {chapter_id}: {e}")
            chapter_info['status'] = 'annotation_failed'

    # Save updated index
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    logger.info("Step 3 complete")


if __name__ == '__main__':
    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    run_step3(config, force=True)
