export interface RecentMessage {
  role: string;
  content: string;
}

export interface Citation {
  source_type: string;
  source_id: string;
  chapter: string | null;
  scene_index: number | null;
  chapter_title?: string;
  excerpt: string;
}

export interface WorldbookFact {
  fact_text: string;
  source_chapter: string | null;
  source_scene: number | null;
  excerpt: string;
  confidence: number;
}

export interface WorldbookCharacterState {
  character: string;
  summary: string;
  confidence: number;
}

export interface WorldbookTimelineNote {
  chapter: string | null;
  scene_index: number | null;
  event: string;
}

export interface WorldbookContext {
  facts: WorldbookFact[];
  character_state: WorldbookCharacterState[];
  timeline_notes: WorldbookTimelineNote[];
  forbidden: string[];
}

export interface QueryContextResponse {
  session_id: string;
  worldbook_context: WorldbookContext;
  citations: Citation[];
  debug_scores: Record<string, unknown>;
  query_understanding: Record<string, unknown>;
}

export interface RespondResponse {
  assistant_reply: string;
  citations: Citation[];
  worldbook_context: WorldbookContext;
}

export interface SessionTurn {
  role: string;
  content: string;
  ts?: string;
}

export interface SessionResponse {
  session_id: string;
  max_unlocked_chapter: number;
  active_characters: string[];
  current_scene: string;
  long_term_summary: string;
  turns: SessionTurn[];
  recent_entities: string[];
  updated_at: string;
}

export interface RpRequestBase {
  message: string;
  session_id: string;
  novel_id?: string;
  unlocked_chapter?: number;
  active_characters?: string[];
  recent_messages?: RecentMessage[];
}

export interface QueryContextPayload extends RpRequestBase {}

export interface RespondPayload extends RpRequestBase {
  worldbook_context?: WorldbookContext;
  citations?: Citation[];
}
