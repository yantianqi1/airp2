import { z } from 'zod';
import { apiClient } from './client';
import type {
  QueryContextPayload,
  QueryContextResponse,
  RespondPayload,
  RespondResponse,
  SessionResponse,
} from '../types/rp';

const citationSchema = z.object({
  source_type: z.string(),
  source_id: z.string(),
  chapter: z.string().nullable(),
  scene_index: z.number().nullable(),
  chapter_title: z.string().optional(),
  excerpt: z.string(),
});

const worldbookContextSchema = z.object({
  facts: z.array(
    z.object({
      fact_text: z.string(),
      source_chapter: z.string().nullable(),
      source_scene: z.number().nullable(),
      excerpt: z.string(),
      confidence: z.number(),
    }),
  ),
  character_state: z.array(
    z.object({
      character: z.string(),
      summary: z.string(),
      confidence: z.number(),
    }),
  ),
  timeline_notes: z.array(
    z.object({
      chapter: z.string().nullable(),
      scene_index: z.number().nullable(),
      event: z.string(),
    }),
  ),
  forbidden: z.array(z.string()),
});

const queryContextSchema = z.object({
  session_id: z.string(),
  worldbook_context: worldbookContextSchema,
  citations: z.array(citationSchema),
  debug_scores: z.record(z.unknown()),
  query_understanding: z.record(z.unknown()),
});

const respondSchema = z.object({
  assistant_reply: z.string(),
  citations: z.array(citationSchema),
  worldbook_context: worldbookContextSchema,
});

const sessionSchema = z.object({
  session_id: z.string(),
  max_unlocked_chapter: z.number(),
  active_characters: z.array(z.string()),
  current_scene: z.string(),
  long_term_summary: z.string(),
  turns: z.array(
    z.object({
      role: z.string(),
      content: z.string(),
      ts: z.string().optional(),
    }),
  ),
  recent_entities: z.array(z.string()),
  updated_at: z.string(),
});

export async function queryContext(payload: QueryContextPayload): Promise<QueryContextResponse> {
  const response = await apiClient.post('/api/v1/rp/query-context', payload);
  return queryContextSchema.parse(response.data);
}

export async function respond(payload: RespondPayload): Promise<RespondResponse> {
  const response = await apiClient.post('/api/v1/rp/respond', payload);
  return respondSchema.parse(response.data);
}

export async function getSession(sessionId: string, novelId?: string): Promise<SessionResponse> {
  const response = await apiClient.get(`/api/v1/rp/session/${encodeURIComponent(sessionId)}`, {
    params: novelId ? { novel_id: novelId } : undefined,
  });
  return sessionSchema.parse(response.data);
}
