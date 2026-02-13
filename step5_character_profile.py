"""Step 5: Generate character profiles."""
import os
import json
import logging
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.llm_client import LLMClient


logger = logging.getLogger(__name__)


class CharacterProfiler:
    """Generate character profiles from annotated scenes."""

    def __init__(self, config):
        """Initialize with config."""
        self.config = config
        self.llm_client = LLMClient(config)
        self.concurrent_requests = max(
            1,
            int(config.get('llm', {}).get('concurrent_requests', 1) or 1),
        )
        self._thread_local = threading.local()

        self.top_n = config['character_profile']['top_n_characters']
        self.min_scenes = config['character_profile']['min_scenes']

        self.profiles_dir = config['paths']['profiles_dir']
        os.makedirs(self.profiles_dir, exist_ok=True)

    def _get_thread_llm_client(self):
        """Get (or create) a per-thread LLM client for concurrent calls."""
        client = getattr(self._thread_local, 'llm_client', None)
        if client is None:
            client = LLMClient(self.config)
            self._thread_local.llm_client = client
        return client

    def generate_profiles(self, annotated_dir):
        """
        Generate character profiles from all annotated chapters.

        Returns:
            List of generated profile files
        """
        logger.info("Collecting character data from all chapters")

        # Collect all character data
        character_scenes = self._collect_character_data(annotated_dir)

        # Get top characters
        character_counts = Counter()
        for char, scenes in character_scenes.items():
            character_counts[char] = len(scenes)

        top_characters = [
            char for char, count in character_counts.most_common(self.top_n)
            if count >= self.min_scenes
        ]

        logger.info(f"Generating profiles for {len(top_characters)} characters")

        # Generate profile for each character
        profile_files = []
        if self.concurrent_requests > 1 and len(top_characters) > 1:
            with ThreadPoolExecutor(max_workers=self.concurrent_requests) as executor:
                futures = {}
                for character in top_characters:
                    scenes = character_scenes[character]
                    logger.info(f"Generating profile for {character} ({len(scenes)} scenes)")
                    futures[
                        executor.submit(self._generate_character_profile, character, scenes)
                    ] = character
                for future in as_completed(futures):
                    character = futures[future]
                    try:
                        profile_files.append(future.result())
                    except Exception as e:
                        logger.error(f"Failed to generate profile for {character}: {e}")
        else:
            for character in top_characters:
                scenes = character_scenes[character]
                logger.info(f"Generating profile for {character} ({len(scenes)} scenes)")

                try:
                    profile_file = self._generate_character_profile(character, scenes)
                    profile_files.append(profile_file)
                except Exception as e:
                    logger.error(f"Failed to generate profile for {character}: {e}")

        logger.info(f"Generated {len(profile_files)} character profiles")

        return profile_files

    def _collect_character_data(self, annotated_dir):
        """Collect all scenes for each character."""
        character_scenes = {}

        # Iterate through all annotated files
        for filename in os.listdir(annotated_dir):
            if not filename.endswith('_annotated.json'):
                continue

            filepath = os.path.join(annotated_dir, filename)

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            chapter_id = data.get('chapter_id', '')
            chapter_title = data.get('chapter_title', '')

            # Extract character scenes
            for scene in data.get('scenes', []):
                metadata = scene.get('metadata', {})
                characters = metadata.get('characters', [])

                for char in characters:
                    if char not in character_scenes:
                        character_scenes[char] = []

                    character_scenes[char].append({
                        'chapter_id': chapter_id,
                        'chapter_title': chapter_title,
                        'scene_index': scene.get('scene_index', 0),
                        'event_summary': metadata.get('event_summary', ''),
                        'emotion_tone': metadata.get('emotion_tone', ''),
                        'key_dialogues': metadata.get('key_dialogues', []),
                        'character_relations': metadata.get('character_relations', []),
                        'plot_significance': metadata.get('plot_significance', 'medium')
                    })

        return character_scenes

    def _generate_character_profile(self, character, scenes):
        """Generate profile for a single character."""
        # Prepare scene data summary
        scene_summaries = []

        for scene in scenes:
            summary = f"[{scene['chapter_title']}] {scene['event_summary']}"

            if scene['emotion_tone']:
                summary += f" (情感: {scene['emotion_tone']})"

            if scene['key_dialogues']:
                summary += f"\n  对白: {'; '.join(scene['key_dialogues'][:2])}"

            scene_summaries.append(summary)

        # Limit to avoid too long prompt
        if len(scene_summaries) > 100:
            # Sample key scenes
            high_scenes = [s for s in scenes if s['plot_significance'] == 'high']
            if len(high_scenes) < 100:
                medium_scenes = [s for s in scenes if s['plot_significance'] == 'medium']
                selected = high_scenes + medium_scenes[:100 - len(high_scenes)]
            else:
                selected = high_scenes[:100]

            scene_summaries = []
            for scene in selected:
                summary = f"[{scene['chapter_title']}] {scene['event_summary']}"
                if scene['key_dialogues']:
                    summary += f"\n  对白: {'; '.join(scene['key_dialogues'][:2])}"
                scene_summaries.append(summary)

        scenes_text = '\n\n'.join(scene_summaries)

        # Collect character relations
        all_relations = set()
        for scene in scenes:
            all_relations.update(scene.get('character_relations', []))

        relations_text = '\n'.join(all_relations) if all_relations else '无'

        prompt = f"""请为小说角色 "{character}" 生成详细的角色档案，用于后续的角色扮演。

角色在小说中的场景记录（按章节顺序）：

{scenes_text}

角色关系：
{relations_text}

请生成包含以下内容的角色档案：

1. **基本信息与身份**
   - 姓名、身份、社会地位等

2. **核心性格特征**
   - 列出3-5个主要性格特点
   - 每个特点附上原文佐证（引用具体场景）

3. **说话风格与语气**
   - 描述角色的语言习惯
   - 提供2-3个典型对白示例

4. **情感反应模式**
   - 角色在不同情境下的典型反应
   - 情绪表达方式

5. **关键经历时间线**
   - 列出角色的重要经历（按时间顺序）
   - 标注对角色影响重大的事件

6. **核心人物关系**
   - 与其他角色的关系及互动模式

7. **内心动机**
   - 角色的核心渴望
   - 角色的主要恐惧

8. **角色扮演注意事项**
   - 扮演该角色时需要注意的关键点
   - 不符合角色设定的行为

请用 Markdown 格式输出，要详细且有深度。
"""

        llm_client = self._get_thread_llm_client()
        profile_md = llm_client.call(
            prompt=prompt,
            temperature=0.7
        )

        # Save profile
        safe_name = character.replace('/', '_').replace('\\', '_')
        profile_file = os.path.join(self.profiles_dir, f"{safe_name}.md")

        with open(profile_file, 'w', encoding='utf-8') as f:
            f.write(f"# {character} - 角色档案\n\n")
            f.write(f"**出场次数**: {len(scenes)}\n\n")
            f.write("---\n\n")
            f.write(profile_md)

        logger.info(f"Saved profile to {profile_file}")

        return profile_file


def run_step5(config):
    """Run step 5: character profile generation."""
    annotated_dir = config['paths']['annotated_dir']

    if not os.path.exists(annotated_dir):
        logger.error("Annotated directory not found. Run previous steps first.")
        return

    profiler = CharacterProfiler(config)
    profile_files = profiler.generate_profiles(annotated_dir)

    logger.info("=" * 50)
    logger.info("Character Profile Generation Complete")
    logger.info(f"Generated {len(profile_files)} profiles")
    logger.info(f"Profiles saved to: {config['paths']['profiles_dir']}")
    logger.info("=" * 50)

    return profile_files


if __name__ == '__main__':
    import yaml

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    run_step5(config)
