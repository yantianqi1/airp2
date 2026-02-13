import { z } from 'zod';
import { apiClient } from './client';
import type {
  ChapterIndexResponse,
  JobLogsResponse,
  NovelDetail,
  NovelEntry,
  PipelineJob,
} from '../types/novels';

const novelSourceSchema = z
  .object({
    filename: z.string().optional(),
    bytes: z.number().optional(),
    char_count: z.number().optional(),
    line_count: z.number().optional(),
  })
  .default({});

const novelEntrySchema = z.object({
  novel_id: z.string(),
  title: z.string().optional().default(''),
  status: z.string().optional().default(''),
  created_at: z.string().optional().default(''),
  updated_at: z.string().optional().default(''),
  source: novelSourceSchema.optional().default({}),
  stats: z.record(z.unknown()).optional().default({}),
  last_job_id: z.string().optional(),
  last_error: z.string().optional(),
});

const novelDetailSchema = novelEntrySchema.extend({
  paths: z.record(z.string()).optional().default({}),
});

const pipelineJobSchema = z.object({
  job_id: z.string(),
  novel_id: z.string(),
  status: z.string(),
  current_step: z.number().nullable(),
  progress: z.number(),
  started_at: z.string().optional().default(''),
  finished_at: z.string().optional().default(''),
  log_path: z.string().optional().default(''),
  error: z.string().optional().default(''),
  result: z.record(z.unknown()).optional().default({}),
});

const jobLogsSchema = z.object({
  job_id: z.string(),
  lines: z.number(),
  text: z.string(),
});

const chapterIndexEntrySchema = z.object({
  chapter_id: z.string(),
  file: z.string().optional(),
  title: z.string().optional(),
  char_count: z.number().optional(),
  status: z.string().optional(),
  scenes_file: z.string().optional(),
  annotated_file: z.string().optional(),
});

const chapterIndexSchema = z.object({
  source_file: z.string().optional(),
  total_chapters: z.number().optional(),
  chapters: z.array(chapterIndexEntrySchema).optional().default([]),
});

export async function listNovels(): Promise<NovelEntry[]> {
  const response = await apiClient.get('/api/v1/novels');
  return z.array(novelEntrySchema).parse(response.data);
}

export async function getNovel(novelId: string): Promise<NovelDetail> {
  const response = await apiClient.get(`/api/v1/novels/${encodeURIComponent(novelId)}`);
  return novelDetailSchema.parse(response.data);
}

export async function createNovel(title: string): Promise<NovelEntry> {
  const response = await apiClient.post('/api/v1/novels', { title });
  return novelEntrySchema.parse(response.data);
}

export async function deleteNovel(novelId: string, deleteVectorDb = false): Promise<void> {
  await apiClient.delete(`/api/v1/novels/${encodeURIComponent(novelId)}`, {
    params: { delete_vector_db: deleteVectorDb ? 'true' : 'false' },
  });
}

export async function uploadNovel(novelId: string, file: File): Promise<unknown> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiClient.post(`/api/v1/novels/${encodeURIComponent(novelId)}/upload`, form);
  return response.data;
}

export async function runPipeline(
  novelId: string,
  payload: { step?: number; force?: boolean; redo_chapter?: number },
): Promise<PipelineJob> {
  const response = await apiClient.post(
    `/api/v1/novels/${encodeURIComponent(novelId)}/pipeline/run`,
    payload,
  );
  return pipelineJobSchema.parse(response.data);
}

export async function getJob(jobId: string): Promise<PipelineJob> {
  const response = await apiClient.get(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
  return pipelineJobSchema.parse(response.data);
}

export async function getJobLogs(jobId: string, lines = 200): Promise<JobLogsResponse> {
  const response = await apiClient.get(`/api/v1/jobs/${encodeURIComponent(jobId)}/logs`, {
    params: { lines },
  });
  return jobLogsSchema.parse(response.data);
}

export async function getChapterIndex(novelId: string): Promise<ChapterIndexResponse> {
  const response = await apiClient.get(
    `/api/v1/novels/${encodeURIComponent(novelId)}/pipeline/chapter-index`,
  );
  return chapterIndexSchema.parse(response.data);
}
