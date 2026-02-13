"""Step 1: Split novel into chapters."""
import os
import re
import json
import logging
from pathlib import Path
from utils.text_utils import read_text_file, clean_text


logger = logging.getLogger(__name__)


class ChapterSplitter:
    """Split novel into chapters."""

    def __init__(self, config):
        """Initialize with config."""
        self.config = config
        self.patterns = config['chapter_split']['patterns']
        self.min_chapter_length = config['chapter_split']['min_chapter_length']
        self.chapters_dir = config['paths']['chapters_dir']

        # Create output directory
        os.makedirs(self.chapters_dir, exist_ok=True)

    def split(self, input_file):
        """
        Split novel file into chapters.

        Returns:
            Path to chapter index file
        """
        logger.info(f"Reading input file: {input_file}")
        text = read_text_file(input_file)
        text = clean_text(text)

        logger.info(f"Total text length: {len(text)} characters")

        # Find all chapter boundaries
        chapters = self._find_chapters(text)

        if not chapters:
            logger.warning("No chapters found, treating entire text as one chapter")
            chapters = [{
                'title': '全文',
                'start': 0,
                'end': len(text),
                'index': 1
            }]

        logger.info(f"Found {len(chapters)} chapters")

        # Save chapters
        chapter_files = []
        for i, chapter_info in enumerate(chapters):
            chapter_file = self._save_chapter(chapter_info, text)
            chapter_files.append({
                'chapter_id': f"chapter_{i+1:04d}",
                'file': chapter_file,
                'title': chapter_info['title'],
                'char_count': chapter_info['end'] - chapter_info['start'],
                'status': 'pending'
            })

        # Save chapter index
        index_file = os.path.join(self.chapters_dir, 'chapter_index.json')
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump({
                'source_file': os.path.basename(input_file),
                'total_chapters': len(chapter_files),
                'chapters': chapter_files
            }, f, ensure_ascii=False, indent=2)

        logger.info(f"Chapter index saved to: {index_file}")

        return index_file

    def _find_chapters(self, text):
        """Find all chapter boundaries in text."""
        chapters = []
        chapter_matches = []

        # Try each pattern
        for pattern in self.patterns:
            matches = list(re.finditer(pattern, text, re.MULTILINE))
            chapter_matches.extend([(m.start(), m.group(0)) for m in matches])

        # Sort by position
        chapter_matches.sort(key=lambda x: x[0])

        # Remove duplicates (same position)
        unique_matches = []
        last_pos = -1
        for pos, title in chapter_matches:
            if pos != last_pos:
                unique_matches.append((pos, title))
                last_pos = pos

        # Build chapter info
        for i, (start_pos, title) in enumerate(unique_matches):
            # Find end position
            if i < len(unique_matches) - 1:
                end_pos = unique_matches[i + 1][0]
            else:
                end_pos = len(text)

            # Extract clean title
            title_clean = title.strip()

            # Skip if chapter is too short
            chapter_length = end_pos - start_pos
            if chapter_length < self.min_chapter_length:
                logger.warning(
                    f"Skipping short chapter '{title_clean}' ({chapter_length} chars)"
                )
                continue

            chapters.append({
                'title': title_clean,
                'start': start_pos,
                'end': end_pos,
                'index': len(chapters) + 1
            })

        return chapters

    def _save_chapter(self, chapter_info, full_text):
        """Save individual chapter to file."""
        chapter_text = full_text[chapter_info['start']:chapter_info['end']]
        chapter_text = clean_text(chapter_text)

        # Generate filename
        chapter_id = f"chapter_{chapter_info['index']:04d}"
        filename = f"{chapter_id}.txt"
        filepath = os.path.join(self.chapters_dir, filename)

        # Save file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(chapter_text)

        logger.info(
            f"Saved chapter {chapter_info['index']}: {chapter_info['title']} "
            f"({len(chapter_text)} chars) to {filename}"
        )

        return filename


def run_step1(config, input_file=None, force=False):
    """Run step 1: chapter splitting."""
    if input_file is None:
        input_file = config['paths']['input_file']

    # Check if already done
    chapters_dir = config['paths']['chapters_dir']
    index_file = os.path.join(chapters_dir, 'chapter_index.json')

    if os.path.exists(index_file) and not force:
        logger.info("Chapter index already exists, skipping step 1")
        return index_file

    # Run splitting
    splitter = ChapterSplitter(config)
    return splitter.split(input_file)


if __name__ == '__main__':
    import yaml
    import sys

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load config
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # Get input file from command line or config
    input_file = sys.argv[1] if len(sys.argv) > 1 else config['paths']['input_file']

    # Run
    run_step1(config, input_file, force=True)
