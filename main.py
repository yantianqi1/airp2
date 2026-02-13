"""Main pipeline for novel vectorization."""
import os
import sys
import json
import yaml
import time
import logging
import argparse
from datetime import datetime


PLACEHOLDER_API_KEYS = {
    "sk-xxxxx",
    "sk-yyyyy",
    "your-llm-api-key",
    "your-embedding-api-key",
    "your-llm-api-key-here",
    "your-embedding-api-key-here",
}


# Setup logging
def setup_logging(config):
    """Setup logging configuration."""
    log_dir = config['paths']['log_dir']
    os.makedirs(log_dir, exist_ok=True)

    # Create log file with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'pipeline_{timestamp}.log')

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return log_file


def load_config(config_file='config.yaml'):
    """Load configuration from YAML file."""
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def print_banner():
    """Print welcome banner."""
    print("=" * 60)
    print("    小说文本向量化处理系统")
    print("    Novel Text Vectorization Pipeline")
    print("=" * 60)
    print()


def print_report(config, start_time):
    """Print processing report."""
    # Load chapter index
    chapters_dir = config['paths']['chapters_dir']
    index_file = os.path.join(chapters_dir, 'chapter_index.json')

    if not os.path.exists(index_file):
        print("No chapter index found")
        return

    with open(index_file, 'r', encoding='utf-8') as f:
        index_data = json.load(f)

    # Calculate statistics
    total_chapters = len(index_data['chapters'])
    completed_chapters = sum(
        1 for ch in index_data['chapters']
        if ch.get('status') == 'vectorized'
    )
    failed_chapters = [
        ch for ch in index_data['chapters']
        if 'failed' in ch.get('status', '')
    ]

    # Load scenes data
    total_scenes = 0
    total_chars = 0
    coverages = []

    scenes_dir = config['paths']['scenes_dir']
    for chapter in index_data['chapters']:
        scenes_relpath = chapter.get('scenes_file')
        if not scenes_relpath:
            continue

        scenes_file = os.path.join(scenes_dir, scenes_relpath)

        if os.path.isfile(scenes_file):
            with open(scenes_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                total_scenes += data['total_scenes']
                coverages.append(data['coverage_rate'])

                for scene in data['scenes']:
                    total_chars += scene.get('char_count', 0)

    avg_scenes = total_scenes / total_chapters if total_chapters > 0 else 0
    avg_length = total_chars / total_scenes if total_scenes > 0 else 0
    avg_coverage = sum(coverages) / len(coverages) if coverages else 0
    min_coverage = min(coverages) if coverages else 0

    # Get LLM and embedding stats
    llm_stats = {}
    emb_stats = {'models': {}, 'total_calls': 0, 'total_texts': 0}
    try:
        from utils.llm_client import LLMClient
        from utils.embedding_client import EmbeddingClient

        llm_stats = LLMClient.get_global_stats()
        emb_stats = EmbeddingClient.get_global_stats()
    except Exception:
        # Keep report robust for partial runs where optional deps are missing.
        pass

    # Calculate elapsed time
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)

    # Print report
    print("\n")
    print("=" * 60)
    print("    处理报告 / Processing Report")
    print("=" * 60)
    print()
    print(f"小说文件: {index_data['source_file']}")
    print(f"总章节数: {total_chapters}")
    print(f"完成章节: {completed_chapters}")
    print()
    print(f"总场景片段数: {total_scenes:,}")
    print(f"平均每章片段数: {avg_scenes:.1f}")
    print(f"平均片段长度: {avg_length:.0f} 字")
    print(f"覆盖率: 均值 {avg_coverage:.1%}, 最低 {min_coverage:.1%}")
    print()

    print("LLM 调用统计:")
    if llm_stats:
        for model, stats in llm_stats.items():
            print(f"  模型 {model}: 调用 {stats['calls']} 次, "
                  f"消耗 {stats['tokens']:,} tokens")
    else:
        print("  无调用记录")

    print()
    print("Embedding 调用统计:")
    if emb_stats['models']:
        for model, stats in emb_stats['models'].items():
            print(f"  模型 {model}: {stats['total_texts']} 条文本, "
                  f"{stats['total_calls']} 次调用")
    else:
        print("  无调用记录")

    print()
    if failed_chapters:
        print(f"失败章节: {len(failed_chapters)}")
        for ch in failed_chapters:
            print(f"  - {ch['chapter_id']}: {ch['title']} ({ch['status']})")
    else:
        print("失败章节: 无")

    print()
    print(f"总耗时: {hours}h {minutes}m {seconds}s")
    print("=" * 60)
    print()


def main():
    """Main pipeline execution."""
    # Parse arguments
    parser = argparse.ArgumentParser(description='Novel Text Vectorization Pipeline')
    parser.add_argument('--input', help='Input novel file path')
    parser.add_argument('--step', type=int, help='Run specific step only (1-5)')
    parser.add_argument('--force', action='store_true', help='Force re-process all')
    parser.add_argument('--redo-chapter', type=int, help='Re-do specific chapter')
    parser.add_argument('--config', default='config.yaml', help='Config file path')

    args = parser.parse_args()

    if args.step is not None and args.step not in {1, 2, 3, 4, 5}:
        raise ValueError("--step must be in [1, 2, 3, 4, 5]")

    # Load config
    config = load_config(args.config)

    # Validate and normalize runtime config
    validate_config(config, args)

    # Setup logging
    log_file = setup_logging(config)

    logger = logging.getLogger(__name__)
    _reset_runtime_stats()

    # Print banner
    print_banner()

    logger.info(f"Logging to: {log_file}")
    logger.info(f"Config loaded from: {args.config}")
    logger.info(f"Input file resolved to: {config['paths']['input_file']}")

    # Start timer
    start_time = time.time()

    try:
        # Step 1: Split chapters
        if args.step is None or args.step == 1:
            from step1_split_chapters import run_step1

            logger.info("=" * 60)
            logger.info("Step 1: 章节拆分 / Chapter Splitting")
            logger.info("=" * 60)

            input_file = config['paths']['input_file']
            run_step1(config, input_file, force=args.force)

        # Step 2: Scene splitting
        if args.step is None or args.step == 2:
            from step2_scene_split import run_step2

            logger.info("=" * 60)
            logger.info("Step 2: 场景切分 / Scene Splitting")
            logger.info("=" * 60)

            run_step2(config, force=args.force, redo_chapter=args.redo_chapter)

        # Step 3: Metadata annotation
        if args.step is None or args.step == 3:
            from step3_annotate import run_step3

            logger.info("=" * 60)
            logger.info("Step 3: 元数据标注 / Metadata Annotation")
            logger.info("=" * 60)

            run_step3(config, force=args.force, redo_chapter=args.redo_chapter)

        # Step 4: Vectorization
        if args.step is None or args.step == 4:
            from step4_vectorize import run_step4

            logger.info("=" * 60)
            logger.info("Step 4: 向量化入库 / Vectorization")
            logger.info("=" * 60)

            run_step4(config, force=args.force)

        # Step 5: Character profiles
        if args.step is None or args.step == 5:
            from step5_character_profile import run_step5

            logger.info("=" * 60)
            logger.info("Step 5: 角色档案生成 / Character Profiling")
            logger.info("=" * 60)

            run_step5(config)

        # Print final report
        print_report(config, start_time)

        logger.info("Pipeline completed successfully!")

    except KeyboardInterrupt:
        logger.warning("\nPipeline interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


def _is_placeholder_api_key(api_key):
    """Check whether api key is still a placeholder."""
    if not api_key:
        return True

    key = str(api_key).strip()
    if key in PLACEHOLDER_API_KEYS:
        return True

    lowered = key.lower()
    if lowered.startswith("your-") or "replace" in lowered:
        return True

    return False


def _is_local_base_url(base_url):
    """Detect local endpoints that may not require real API keys."""
    if not base_url:
        return False

    url = str(base_url).lower()
    return "localhost" in url or "127.0.0.1" in url


def _resolve_input_file(config, cli_input=None):
    """Resolve effective input file with fallback to sample file."""
    if cli_input:
        return cli_input

    configured = config['paths'].get('input_file')
    if configured and os.path.exists(configured):
        return configured

    # Prefer a sample file next to configured path (works for both local and container layouts).
    sample_candidates = []
    if configured:
        sample_candidates.append(os.path.join(os.path.dirname(configured), '示例小说.txt'))
    sample_candidates.extend(['data/input/示例小说.txt', '/app/data/input/示例小说.txt'])

    for sample in sample_candidates:
        if sample and os.path.exists(sample):
            return sample

    return configured


def validate_config(config, args):
    """Validate required config fields and runtime inputs."""
    required_root = {'llm', 'embedding', 'paths'}
    missing_root = [k for k in required_root if k not in config]
    if missing_root:
        raise ValueError(f"Missing config sections: {', '.join(missing_root)}")

    required_path_keys = {
        'chapters_dir',
        'scenes_dir',
        'annotated_dir',
        'profiles_dir',
        'vector_db_path',
        'log_dir',
    }
    missing_path_keys = [k for k in required_path_keys if k not in config['paths']]
    if missing_path_keys:
        raise ValueError(f"Missing paths config keys: {', '.join(missing_path_keys)}")

    needs_llm = args.step is None or args.step in {2, 3, 5}
    needs_embedding = args.step is None or args.step == 4

    sections_to_validate = []
    if needs_llm:
        sections_to_validate.append('llm')
    if needs_embedding:
        sections_to_validate.append('embedding')

    for section in sections_to_validate:
        base_url = config[section].get('base_url')
        api_key = config[section].get('api_key')
        if not _is_local_base_url(base_url) and _is_placeholder_api_key(api_key):
            raise ValueError(
                f"{section}.api_key is placeholder or empty. "
                f"Please update {args.config} before running."
            )

    configured_input = config['paths'].get('input_file')
    resolved_input = _resolve_input_file(config, args.input)
    config['paths']['input_file'] = resolved_input
    if not args.input and configured_input != resolved_input and resolved_input:
        print(
            f"[Config] Input file '{configured_input}' not found, "
            f"fallback to '{resolved_input}'."
        )

    needs_input_file = args.step is None or args.step == 1
    if needs_input_file and (not resolved_input or not os.path.exists(resolved_input)):
        raise FileNotFoundError(
            f"Input file not found: {resolved_input}. "
            "Pass --input <file> or update paths.input_file in config."
        )


def _reset_runtime_stats():
    """Reset in-process API call stats before each pipeline run."""
    try:
        from utils.llm_client import LLMClient
        from utils.embedding_client import EmbeddingClient
        LLMClient.reset_global_stats()
        EmbeddingClient.reset_global_stats()
    except Exception:
        pass


if __name__ == '__main__':
    main()
