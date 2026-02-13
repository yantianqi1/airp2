import { Navigate } from 'react-router-dom';

const LAST_CHAT_KEY = 'airp:lastChatPath';

function safeInternalPath(raw: string | null): string | null {
  const value = String(raw || '').trim();
  if (!value) {
    return null;
  }
  if (!value.startsWith('/')) {
    return null;
  }
  if (value.startsWith('//') || value.includes('://')) {
    return null;
  }
  if (value === '/chat') {
    return null;
  }
  return value;
}

export function ChatResumePage() {
  const lastPath =
    typeof window === 'undefined' ? null : safeInternalPath(window.localStorage.getItem(LAST_CHAT_KEY));

  if (lastPath) {
    return <Navigate to={lastPath} replace />;
  }
  return <Navigate to="/session" replace />;
}

export { LAST_CHAT_KEY };

