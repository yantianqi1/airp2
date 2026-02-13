import { useMutation, useQuery } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { ChatComposer } from '../features/chat/ChatComposer';
import { ChatMessageList } from '../features/chat/ChatMessageList';
import { DebugPanel } from '../features/debug/DebugPanel';
import { CitationPanel } from '../features/evidence/CitationPanel';
import { AppShellGlass } from '../features/layout/AppShellGlass';
import { SessionConfigPanel } from '../features/session/SessionConfigPanel';
import { DebugIcon, MenuIcon, PanelIcon } from '../shared/components/icons';
import { getSession, queryContext, respond } from '../shared/api/rp';
import type { QueryContextResponse, RecentMessage, WorldbookContext } from '../shared/types/rp';
import { useChatStore } from '../store/chatStore';

function normalizeError(error: unknown): string {
  if (error instanceof AxiosError) {
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail;
    if (detail) {
      return detail;
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return '请求失败，请稍后重试。';
}

export function ChatPage() {
  const { sessionId: routeSessionId } = useParams<{ sessionId: string }>();
  const sessionId = routeSessionId?.trim() || '';
  const hydratedRef = useRef(false);
  const [mobilePanel, setMobilePanel] = useState<'session' | 'evidence' | 'debug' | null>(null);

  const {
    unlockedChapter,
    activeCharacters,
    debugMode,
    messages,
    latestWorldbookContext,
    latestCitations,
    latestDebugScores,
    latestQueryUnderstanding,
    isSending,
    errorMessage,
    setSessionId,
    setUnlockedChapter,
    addActiveCharacter,
    removeActiveCharacter,
    setDebugMode,
    hydrateSession,
    appendUserMessage,
    appendAssistantMessage,
    setLatestEvidence,
    setDebugPayload,
    setSending,
    setError,
  } = useChatStore((state) => state);

  useEffect(() => {
    if (!sessionId) {
      return;
    }
    hydratedRef.current = false;
    setSessionId(sessionId);
  }, [sessionId, setSessionId]);

  const sessionQuery = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => getSession(sessionId),
    enabled: Boolean(sessionId),
    retry: 1,
  });

  useEffect(() => {
    if (!sessionQuery.data || hydratedRef.current) {
      return;
    }
    hydrateSession(sessionQuery.data);
    hydratedRef.current = true;
  }, [sessionQuery.data, hydrateSession]);

  const recentMessages = useMemo<RecentMessage[]>(
    () => messages.slice(-10).map((item) => ({ role: item.role, content: item.content })),
    [messages],
  );

  const retrieveOnlyMutation = useMutation({
    mutationFn: async (message: string) => {
      return queryContext({
        message,
        session_id: sessionId,
        unlocked_chapter: unlockedChapter,
        active_characters: activeCharacters,
        recent_messages: [...recentMessages, { role: 'user', content: message }],
      });
    },
    onMutate: () => {
      setSending(true);
      setError(null);
    },
    onSuccess: (data: QueryContextResponse) => {
      setLatestEvidence(data.worldbook_context, data.citations);
      setDebugPayload(data.debug_scores, data.query_understanding);
    },
    onError: (error) => {
      setError(normalizeError(error));
    },
    onSettled: () => {
      setSending(false);
    },
  });

  const respondMutation = useMutation({
    mutationFn: async ({
      message,
      recent,
    }: {
      message: string;
      recent: RecentMessage[];
    }) => {
      let context: WorldbookContext | undefined;
      let citations = latestCitations;
      let debugScores = latestDebugScores;
      let queryUnderstanding = latestQueryUnderstanding;

      if (debugMode) {
        const contextResult = await queryContext({
          message,
          session_id: sessionId,
          unlocked_chapter: unlockedChapter,
          active_characters: activeCharacters,
          recent_messages: recent,
        });
        context = contextResult.worldbook_context;
        citations = contextResult.citations;
        debugScores = contextResult.debug_scores;
        queryUnderstanding = contextResult.query_understanding;
      }

      const response = await respond({
        message,
        session_id: sessionId,
        unlocked_chapter: unlockedChapter,
        active_characters: activeCharacters,
        recent_messages: recent,
        worldbook_context: context,
        citations,
      });

      return {
        assistantReply: response.assistant_reply,
        citations: response.citations,
        worldbookContext: response.worldbook_context,
        debugScores,
        queryUnderstanding,
      };
    },
    onMutate: () => {
      setSending(true);
      setError(null);
    },
    onSuccess: (data) => {
      appendAssistantMessage(data.assistantReply, data.citations);
      setLatestEvidence(data.worldbookContext, data.citations);
      setDebugPayload(data.debugScores, data.queryUnderstanding);
    },
    onError: (error) => {
      setError(normalizeError(error));
    },
    onSettled: () => {
      setSending(false);
    },
  });

  if (!sessionId) {
    return <Navigate to="/" replace />;
  }

  const busy = isSending || retrieveOnlyMutation.isPending || respondMutation.isPending;

  const onSend = (message: string) => {
    appendUserMessage(message);
    const recent: RecentMessage[] = [...recentMessages, { role: 'user', content: message }].slice(-10);
    respondMutation.mutate({ message, recent });
  };

  const onRetrieveOnly = (message: string) => {
    retrieveOnlyMutation.mutate(message);
  };

  const refreshSession = () => {
    hydratedRef.current = false;
    sessionQuery.refetch();
  };

  return (
    <div className="chat-page">
      <AppShellGlass
        topBar={
          <>
            <button
              className="soft-button mobile-only"
              type="button"
              onClick={() => setMobilePanel('session')}
            >
              <MenuIcon aria-hidden="true" />
              会话
            </button>
            <button
              className="soft-button mobile-only"
              type="button"
              onClick={() => setMobilePanel('evidence')}
            >
              <PanelIcon aria-hidden="true" />
              证据
            </button>
            <button
              className="soft-button mobile-only"
              type="button"
              onClick={() => setMobilePanel('debug')}
            >
              <DebugIcon aria-hidden="true" />
              调试
            </button>
          </>
        }
        left={
          <SessionConfigPanel
            sessionId={sessionId}
            unlockedChapter={unlockedChapter}
            activeCharacters={activeCharacters}
            debugMode={debugMode}
            onUnlockedChapterChange={setUnlockedChapter}
            onAddCharacter={addActiveCharacter}
            onRemoveCharacter={removeActiveCharacter}
            onDebugModeChange={setDebugMode}
            onRefreshSession={refreshSession}
          />
        }
        right={
          <div className="stack-panels">
            <CitationPanel citations={latestCitations} context={latestWorldbookContext} />
            <DebugPanel debugScores={latestDebugScores} queryUnderstanding={latestQueryUnderstanding} />
          </div>
        }
      >
        <section className="chat-main stack-panels">
          <header className="glass-panel chat-head">
            <p className="label">AIRP RP Chat</p>
            <h1>会话：{sessionId}</h1>
            <p className="muted">模式：{debugMode ? '调试模式（检索 + 回答）' : '生产模式（直接回答）'}</p>
          </header>

          <ChatMessageList messages={messages} isSending={busy} />

          {errorMessage ? (
            <div className="glass-panel error-box" role="alert">
              {errorMessage}
            </div>
          ) : null}

          {sessionQuery.isPending ? (
            <div className="glass-panel muted">正在加载会话历史...</div>
          ) : null}

          <ChatComposer busy={busy} debugMode={debugMode} onSend={onSend} onRetrieveOnly={onRetrieveOnly} />
        </section>
      </AppShellGlass>

      {mobilePanel ? (
        <div className="mobile-drawer-wrap" role="dialog" aria-modal="true">
          <button className="mobile-backdrop" type="button" onClick={() => setMobilePanel(null)} aria-label="关闭" />
          <div className="mobile-drawer glass-panel">
            <div className="drawer-head">
              <p className="panel-title">
                {mobilePanel === 'session' ? '会话设置' : mobilePanel === 'evidence' ? '证据面板' : '调试面板'}
              </p>
              <button className="soft-button" type="button" onClick={() => setMobilePanel(null)}>
                关闭
              </button>
            </div>
            {mobilePanel === 'session' ? (
              <SessionConfigPanel
                sessionId={sessionId}
                unlockedChapter={unlockedChapter}
                activeCharacters={activeCharacters}
                debugMode={debugMode}
                onUnlockedChapterChange={setUnlockedChapter}
                onAddCharacter={addActiveCharacter}
                onRemoveCharacter={removeActiveCharacter}
                onDebugModeChange={setDebugMode}
                onRefreshSession={refreshSession}
              />
            ) : null}
            {mobilePanel === 'evidence' ? (
              <CitationPanel citations={latestCitations} context={latestWorldbookContext} />
            ) : null}
            {mobilePanel === 'debug' ? (
              <DebugPanel debugScores={latestDebugScores} queryUnderstanding={latestQueryUnderstanding} />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
