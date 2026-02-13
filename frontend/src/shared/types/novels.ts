export interface NovelSourceMeta {
  filename?: string;
  bytes?: number;
  char_count?: number;
  line_count?: number;
}

export interface NovelEntry {
  novel_id: string;
  title: string;
  visibility?: string;
  status: string;
  created_at: string;
  updated_at: string;
  source: NovelSourceMeta;
  stats: Record<string, unknown>;
  last_job_id?: string;
  last_error?: string;
}

export interface PublicNovelEntry {
  novel_id: string;
  title: string;
  status: string;
  updated_at: string;
}

export interface NovelDetail extends NovelEntry {
  paths?: Record<string, string>;
}

export interface PipelineJob {
  job_id: string;
  novel_id: string;
  status: string;
  current_step: number | null;
  progress: number;
  started_at: string;
  finished_at: string;
  log_path: string;
  error: string;
  result: Record<string, unknown>;
}

export interface JobLogsResponse {
  job_id: string;
  lines: number;
  text: string;
}

export interface ChapterIndexEntry {
  chapter_id: string;
  file?: string;
  title?: string;
  char_count?: number;
  status?: string;
  scenes_file?: string;
  annotated_file?: string;
}

export interface ChapterIndexResponse {
  source_file?: string;
  total_chapters?: number;
  chapters: ChapterIndexEntry[];
}
