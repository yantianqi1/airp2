import { create } from 'zustand';
import { normalizeCharacterList } from '../shared/lib/session';
import type { Citation, SessionResponse, WorldbookContext } from '../shared/types/rp';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  ts: string;
  citations: Citation[];
}

interface ChatState {
  sessionId: string;
  unlockedChapter: number;
  activeCharacters: string[];
  debugMode: boolean;
  messages: ChatMessage[];
  latestWorldbookContext: WorldbookContext | null;
  latestCitations: Citation[];
  latestDebugScores: Record<string, unknown> | null;
  latestQueryUnderstanding: Record<string, unknown> | null;
  isSending: boolean;
  errorMessage: string | null;
  beginSession: (sessionId: string) => void;
  setSessionId: (sessionId: string) => void;
  setUnlockedChapter: (chapter: number) => void;
  setActiveCharacters: (characters: string[]) => void;
  addActiveCharacter: (character: string) => void;
  removeActiveCharacter: (character: string) => void;
  setDebugMode: (enabled: boolean) => void;
  hydrateSession: (session: SessionResponse) => void;
  appendUserMessage: (content: string) => void;
  appendAssistantMessage: (content: string, citations?: Citation[]) => void;
  setLatestEvidence: (context: WorldbookContext, citations: Citation[]) => void;
  setDebugPayload: (
    debugScores: Record<string, unknown> | null,
    queryUnderstanding: Record<string, unknown> | null,
  ) => void;
  setSending: (isSending: boolean) => void;
  setError: (message: string | null) => void;
}

function createMessageId(prefix: 'u' | 'a'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function mapTurnRole(role: string): 'user' | 'assistant' {
  return role === 'user' ? 'user' : 'assistant';
}

export const useChatStore = create<ChatState>((set) => ({
  sessionId: '',
  unlockedChapter: 0,
  activeCharacters: [],
  debugMode: true,
  messages: [],
  latestWorldbookContext: null,
  latestCitations: [],
  latestDebugScores: null,
  latestQueryUnderstanding: null,
  isSending: false,
  errorMessage: null,
  beginSession: (sessionId) =>
    set({
      sessionId,
      unlockedChapter: 0,
      activeCharacters: [],
      messages: [],
      latestWorldbookContext: null,
      latestCitations: [],
      latestDebugScores: null,
      latestQueryUnderstanding: null,
      isSending: false,
      errorMessage: null,
    }),
  setSessionId: (sessionId) => set({ sessionId }),
  setUnlockedChapter: (chapter) => set({ unlockedChapter: Math.max(0, Math.floor(chapter || 0)) }),
  setActiveCharacters: (characters) => set({ activeCharacters: normalizeCharacterList(characters) }),
  addActiveCharacter: (character) =>
    set((state) => ({
      activeCharacters: normalizeCharacterList([...state.activeCharacters, character]),
    })),
  removeActiveCharacter: (character) =>
    set((state) => ({
      activeCharacters: state.activeCharacters.filter((item) => item !== character),
    })),
  setDebugMode: (enabled) => set({ debugMode: enabled }),
  hydrateSession: (session) =>
    set({
      sessionId: session.session_id,
      unlockedChapter: session.max_unlocked_chapter,
      activeCharacters: normalizeCharacterList(session.active_characters || []),
      messages: (session.turns || []).map((turn) => ({
        id: createMessageId(turn.role === 'user' ? 'u' : 'a'),
        role: mapTurnRole(turn.role),
        content: turn.content,
        ts: turn.ts || new Date().toISOString(),
        citations: [],
      })),
    }),
  appendUserMessage: (content) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: createMessageId('u'),
          role: 'user',
          content,
          ts: new Date().toISOString(),
          citations: [],
        },
      ],
    })),
  appendAssistantMessage: (content, citations = []) =>
    set((state) => ({
      messages: [
        ...state.messages,
        {
          id: createMessageId('a'),
          role: 'assistant',
          content,
          ts: new Date().toISOString(),
          citations,
        },
      ],
    })),
  setLatestEvidence: (context, citations) =>
    set({
      latestWorldbookContext: context,
      latestCitations: citations,
    }),
  setDebugPayload: (debugScores, queryUnderstanding) =>
    set({
      latestDebugScores: debugScores,
      latestQueryUnderstanding: queryUnderstanding,
    }),
  setSending: (isSending) => set({ isSending }),
  setError: (errorMessage) => set({ errorMessage }),
}));
