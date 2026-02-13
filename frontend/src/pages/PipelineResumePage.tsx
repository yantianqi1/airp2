import { Navigate } from 'react-router-dom';

const LAST_PIPELINE_KEY = 'airp:lastPipelinePath';

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
  if (value === '/pipeline') {
    return null;
  }
  return value;
}

export function PipelineResumePage() {
  const lastPath =
    typeof window === 'undefined' ? null : safeInternalPath(window.localStorage.getItem(LAST_PIPELINE_KEY));

  if (lastPath) {
    return <Navigate to={lastPath} replace />;
  }
  return <Navigate to="/library" replace />;
}

export { LAST_PIPELINE_KEY };

