import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createSessionId } from '../shared/lib/session';
import { getMe } from '../shared/api/auth';
import { createNovel, deleteNovel, getJob, getJobLogs, listNovels, listPublicNovels, runPipeline, updateNovel, uploadNovel } from '../shared/api/novels';
import type { NovelEntry, PublicNovelEntry } from '../shared/types/novels';

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) {
    return '-';
  }
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function statusLabel(status: string): string {
  switch (status) {
    case 'created':
      return '已创建';
    case 'uploaded':
      return '已上传';
    case 'processing':
      return '处理中';
    case 'ready':
      return '已就绪';
    case 'failed':
      return '失败';
    default:
      return status || '未知';
  }
}

function NovelCard({
  novel,
  onUploaded,
  onJobStarted,
  onDeleted,
  onUpdated,
}: {
  novel: NovelEntry;
  onUploaded: () => void;
  onJobStarted: () => void;
  onDeleted: () => void;
  onUpdated: () => void;
}) {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [showLogs, setShowLogs] = useState(false);

  const jobId = novel.last_job_id?.trim() || '';
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'running' || status === 'queued' ? 1000 : false;
    },
  });

  const logQuery = useQuery({
    queryKey: ['jobLogs', jobId, showLogs],
    queryFn: () => getJobLogs(jobId, 140),
    enabled: Boolean(jobId && showLogs),
    refetchInterval: (query) => {
      const status = jobQuery.data?.status;
      const hasData = Boolean(query.state.data);
      if (!showLogs) {
        return false;
      }
      if (!hasData) {
        return 800;
      }
      return status === 'running' || status === 'queued' ? 1000 : false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => uploadNovel(novel.novel_id, file),
    onSuccess: () => onUploaded(),
  });

  const runMutation = useMutation({
    mutationFn: async () => runPipeline(novel.novel_id, {}),
    onSuccess: () => onJobStarted(),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => deleteNovel(novel.novel_id, false),
    onSuccess: () => onDeleted(),
  });

  const visibilityMutation = useMutation({
    mutationFn: async () => {
      const next = novel.visibility === 'public' ? 'private' : 'public';
      return updateNovel(novel.novel_id, { visibility: next });
    },
    onSuccess: () => onUpdated(),
  });

  const hasSource = Boolean(novel.source?.filename);
  const job = jobQuery.data;
  const jobStatus = job?.status || '';
  const progressPct = Math.round(Math.max(0, Math.min(1, job?.progress ?? 0)) * 100);
  const busy =
    uploadMutation.isPending || runMutation.isPending || deleteMutation.isPending || visibilityMutation.isPending;

  const openChat = () => {
    const sessionId = createSessionId();
    navigate(
      `/novels/${encodeURIComponent(novel.novel_id)}/chat/${encodeURIComponent(sessionId)}`,
    );
  };

  const openPipeline = () => {
    navigate(`/novels/${encodeURIComponent(novel.novel_id)}/pipeline`);
  };

  return (
    <article className="glass-panel novel-card">
      <header className="novel-card-head">
        <div>
          <p className="label">Novel</p>
          <h2 className="novel-title">{novel.title || novel.novel_id}</h2>
          <p className="muted novel-sub">
            <span className={`status-chip status-${novel.status || 'unknown'}`}>
              {statusLabel(novel.status)}
            </span>
            <span className={`status-chip status-${novel.visibility === 'public' ? 'ready' : 'created'}`}>
              {novel.visibility === 'public' ? '公开' : '私有'}
            </span>
            <span className="mono">ID: {novel.novel_id}</span>
          </p>
        </div>
        <div className="novel-actions">
          <button type="button" className="soft-button" onClick={openPipeline} disabled={busy}>
            流水线
          </button>
          <button type="button" className="soft-button" onClick={openChat} disabled={busy}>
            进入聊天
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => runMutation.mutate()}
            disabled={!hasSource || busy}
            title={!hasSource ? '请先上传 txt' : undefined}
          >
            一键处理
          </button>
        </div>
      </header>

      <div className="novel-meta grid-2">
        <div className="meta-box">
          <p className="label">Source</p>
          <p className="meta-line">
            <span className="mono">{novel.source?.filename || '未上传'}</span>
          </p>
          <p className="muted">
            {formatBytes(novel.source?.bytes)}，{novel.source?.char_count ?? '-'} 字，{novel.source?.line_count ?? '-'} 行
          </p>
        </div>
        <div className="meta-box">
          <p className="label">Job</p>
          <p className="meta-line">
            <span className="mono">{jobId || '-'}</span>
          </p>
          <p className="muted">
            {jobStatus ? `状态：${jobStatus}，Step：${job?.current_step ?? '-'}，进度：${progressPct}%` : '暂无作业'}
          </p>
        </div>
      </div>

      {jobStatus ? (
        <div className="progress-track" aria-label="job progress">
          <div className="progress-bar" style={{ width: `${progressPct}%` }} />
        </div>
      ) : null}

      {job?.error ? <p className="muted error-inline">错误：{job.error}</p> : null}
      {novel.last_error ? <p className="muted error-inline">记录：{novel.last_error}</p> : null}

      <div className="novel-toolbar">
        <input
          ref={fileRef}
          className="sr-only"
          type="file"
          accept=".txt,text/plain"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (!file) {
              return;
            }
            uploadMutation.mutate(file);
          }}
        />
        <button
          type="button"
          className="soft-button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
        >
          上传 txt
        </button>
        <button
          type="button"
          className="soft-button"
          onClick={() => visibilityMutation.mutate()}
          disabled={busy}
        >
          {novel.visibility === 'public' ? '设为私有' : '公开'}
        </button>
        <button
          type="button"
          className="soft-button"
          onClick={() => setShowLogs((value) => !value)}
          disabled={!jobId}
        >
          {showLogs ? '收起日志' : '查看日志'}
        </button>
        <button
          type="button"
          className="soft-button danger-button"
          onClick={() => deleteMutation.mutate()}
          disabled={busy}
        >
          删除
        </button>
      </div>

      {showLogs ? (
        <pre className="log-box">
          {logQuery.isLoading ? '加载中...' : logQuery.data?.text || '暂无日志'}
        </pre>
      ) : null}
    </article>
  );
}

function PublicNovelCard({ novel }: { novel: PublicNovelEntry }) {
  const navigate = useNavigate();
  const openChat = () => {
    const sessionId = createSessionId();
    navigate(`/novels/${encodeURIComponent(novel.novel_id)}/chat/${encodeURIComponent(sessionId)}`);
  };

  return (
    <article className="glass-panel novel-card">
      <header className="novel-card-head">
        <div>
          <p className="label">Public Novel</p>
          <h2 className="novel-title">{novel.title || novel.novel_id}</h2>
          <p className="muted novel-sub">
            <span className={`status-chip status-${novel.status || 'unknown'}`}>{statusLabel(novel.status)}</span>
            <span className="mono">ID: {novel.novel_id}</span>
          </p>
        </div>
        <div className="novel-actions">
          <button type="button" className="primary-button" onClick={openChat}>
            进入聊天
          </button>
        </div>
      </header>
      <div className="novel-meta grid-2">
        <div className="meta-box">
          <p className="label">Updated</p>
          <p className="muted mono">{novel.updated_at || '-'}</p>
        </div>
        <div className="meta-box">
          <p className="label">Access</p>
          <p className="muted">公开只读</p>
        </div>
      </div>
    </article>
  );
}

export function LibraryPage() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [tab, setTab] = useState<'mine' | 'public'>('mine');

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    retry: 0,
  });
  const mode = meQuery.data?.mode || 'guest';

  const novelsQuery = useQuery({
    queryKey: ['novels'],
    queryFn: listNovels,
    refetchInterval: 2000,
    enabled: mode === 'user',
  });

  const publicNovelsQuery = useQuery({
    queryKey: ['publicNovels'],
    queryFn: listPublicNovels,
    refetchInterval: 8000,
  });

  const createMutation = useMutation({
    mutationFn: async () => createNovel(title),
    onSuccess: () => {
      setTitle('');
      queryClient.invalidateQueries({ queryKey: ['novels'] });
    },
  });

  const novels = useMemo(() => novelsQuery.data || [], [novelsQuery.data]);
  const publicNovels = useMemo(() => publicNovelsQuery.data || [], [publicNovelsQuery.data]);

  const activeTab = mode === 'user' ? tab : 'public';

  return (
    <div className="library-wrap">
      <header className="glass-panel library-head">
        <div>
          <p className="label">Novel Library</p>
          <h1 className="library-title">多小说工作台</h1>
          <p className="muted">
            {mode === 'user'
              ? '上传 txt，启动 Step1~5 处理，并按小说进入 RP Chat。'
              : '游客模式：可聊天；登录后可导入与管理你的小说。'}
          </p>
        </div>
        {mode === 'user' ? (
          <form
            className="library-create"
            onSubmit={(event) => {
              event.preventDefault();
              createMutation.mutate();
            }}
          >
            <label className="sr-only" htmlFor="novel-title">
              Novel title
            </label>
            <input
              id="novel-title"
              className="glass-input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="输入小说标题（可选）"
            />
            <button type="submit" className="primary-button" disabled={createMutation.isPending}>
              新建
            </button>
          </form>
        ) : null}
      </header>

      {mode === 'user' && novelsQuery.isError ? (
        <section className="glass-panel error-box" role="alert">
          无法加载小说库，请检查后端是否运行在 `http://localhost:8011` 或设置 `VITE_API_BASE_URL`。
        </section>
      ) : null}

      {activeTab === 'mine' && novelsQuery.isLoading ? (
        <section className="glass-panel empty-state">加载中...</section>
      ) : null}

      {activeTab === 'mine' && !novelsQuery.isLoading && novels.length === 0 ? (
        <section className="glass-panel empty-state">还没有小说。先点右上角新建一个。</section>
      ) : null}

      {mode === 'user' ? (
        <section className="glass-panel library-tabs">
          <div className="novel-toolbar">
            <button
              type="button"
              className={`soft-button${activeTab === 'mine' ? ' is-active' : ''}`}
              onClick={() => setTab('mine')}
            >
              我的小说
            </button>
            <button
              type="button"
              className={`soft-button${activeTab === 'public' ? ' is-active' : ''}`}
              onClick={() => setTab('public')}
            >
              公共库
            </button>
          </div>
        </section>
      ) : null}

      {activeTab === 'mine' && novels.length ? (
        <section className="library-grid">
          {novels.map((novel) => (
            <NovelCard
              key={novel.novel_id}
              novel={novel}
              onUploaded={() => queryClient.invalidateQueries({ queryKey: ['novels'] })}
              onJobStarted={() => queryClient.invalidateQueries({ queryKey: ['novels'] })}
              onDeleted={() => queryClient.invalidateQueries({ queryKey: ['novels'] })}
              onUpdated={() => queryClient.invalidateQueries({ queryKey: ['novels'] })}
            />
          ))}
        </section>
      ) : null}

      {activeTab === 'public' ? (
        <>
          {publicNovelsQuery.isError ? (
            <section className="glass-panel error-box" role="alert">
              无法加载公共库，请稍后重试。
            </section>
          ) : null}
          {publicNovelsQuery.isLoading ? (
            <section className="glass-panel empty-state">加载中...</section>
          ) : null}
          {!publicNovelsQuery.isLoading && publicNovels.length === 0 ? (
            <section className="glass-panel empty-state">公共库暂无可用小说。</section>
          ) : null}
          {publicNovels.length ? (
            <section className="library-grid">
              {publicNovels.map((novel) => (
                <PublicNovelCard key={novel.novel_id} novel={novel} />
              ))}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
