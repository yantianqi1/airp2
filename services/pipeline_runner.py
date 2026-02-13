"""Pipeline runner for per-novel workspaces.

The existing pipeline steps (step1~step5) already accept an in-memory `config`.
This runner builds a novel-scoped config (overriding `config['paths']`) and
invokes the steps in-process.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .novels_service import NovelsService
from .storage_layout import StorageLayout


logger = logging.getLogger(__name__)


def _configure_job_logging(log_path: str) -> None:
    """Attach a file handler for pipeline logs in long-running processes."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove previous file handlers to avoid cross-job log pollution.
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Keep stdout handler if present; otherwise add one.
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)


@dataclass
class PipelineRunSpec:
    step: Optional[int] = None  # None => full
    force: bool = False
    redo_chapter: Optional[int] = None


class PipelineRunner:
    def __init__(self, base_config: Dict[str, Any], novels: NovelsService, layout: StorageLayout):
        self.base_config = base_config
        self.novels = novels
        self.layout = layout

    @staticmethod
    def _count_profile_files(profiles_dir: str) -> int:
        try:
            return sum(
                1
                for name in os.listdir(profiles_dir)
                if name.lower().endswith(".md") and os.path.isfile(os.path.join(profiles_dir, name))
            )
        except Exception:
            return 0

    def build_novel_config(self, novel_id: str) -> Dict[str, Any]:
        cfg = copy.deepcopy(self.base_config)
        cfg.setdefault("paths", {})

        record = self.novels.get(novel_id)
        paths = self.layout.user_novel_paths(record.owner_user_id, record.novel_id)
        cfg["paths"]["input_file"] = paths["source_file"]
        cfg["paths"]["chapters_dir"] = paths["chapters_dir"]
        cfg["paths"]["scenes_dir"] = paths["scenes_dir"]
        cfg["paths"]["annotated_dir"] = paths["annotated_dir"]
        cfg["paths"]["profiles_dir"] = paths["profiles_dir"]
        cfg["paths"]["vector_db_path"] = paths["vector_db_path"]
        cfg["paths"]["log_dir"] = paths["log_dir"]
        return cfg

    def run(self, novel_id: str, spec: PipelineRunSpec, log_path: str) -> Dict[str, Any]:
        """Run step1~step5 for a novel; returns a small stats summary."""
        _configure_job_logging(log_path)

        cfg = self.build_novel_config(novel_id)
        start_time = time.time()

        # Validate input presence for step1/full.
        needs_input = spec.step is None or spec.step == 1
        if needs_input and not os.path.exists(cfg["paths"]["input_file"]):
            raise FileNotFoundError(f"novel source file not found: {cfg['paths']['input_file']}")

        # Validate chapter index for downstream steps to avoid silent no-op successes.
        index_file = os.path.join(cfg["paths"]["chapters_dir"], "chapter_index.json")
        if spec.step is not None and spec.step >= 2 and not os.path.exists(index_file):
            raise FileNotFoundError(f"chapter index not found: {index_file} (run step1 first)")

        if spec.step == 5 and not os.path.isdir(cfg["paths"]["annotated_dir"]):
            raise FileNotFoundError(
                f"annotated dir not found: {cfg['paths']['annotated_dir']} (run step3 first)"
            )

        stats: Dict[str, Any] = {"novel_id": novel_id}
        step = spec.step

        if step is None or step == 1:
            from step1_split_chapters import run_step1

            run_step1(cfg, cfg["paths"]["input_file"], force=spec.force)

        if step is None or step == 2:
            from step2_scene_split import run_step2

            run_step2(cfg, force=spec.force, redo_chapter=spec.redo_chapter)

        if step is None or step == 3:
            from step3_annotate import run_step3

            run_step3(cfg, force=spec.force, redo_chapter=spec.redo_chapter)

        vector_stats = None
        if step is None or step == 4:
            from step4_vectorize import run_step4

            vector_stats = run_step4(cfg, force=spec.force)

        if step is None or step == 5:
            from step5_character_profile import run_step5

            profile_files = run_step5(cfg)
            if isinstance(profile_files, list):
                stats["profiles_generated"] = len(profile_files)

        # Derive summary stats from chapter_index if present.
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
                stats["total_chapters"] = int(index_data.get("total_chapters", 0) or 0)
                chapters = list(index_data.get("chapters", []) or [])
                stats["chapters_vectorized"] = sum(
                    1 for ch in chapters if str(ch.get("status", "")) == "vectorized"
                )
                stats["chapters_failed"] = sum(
                    1 for ch in chapters if "failed" in str(ch.get("status", ""))
                )
            except Exception:
                pass

        if isinstance(vector_stats, dict):
            stats["vector_db"] = vector_stats

        profiles_dir = cfg["paths"].get("profiles_dir") or ""
        if profiles_dir:
            stats["profiles_total"] = self._count_profile_files(profiles_dir)

        stats["elapsed_s"] = round(time.time() - start_time, 2)
        logger.info("Novel pipeline finished: %s", stats)
        return stats
