import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import {
  getChapterIndex,
  getJob,
  getJobLogs,
  getNovel,
  runPipeline,
  uploadNovel,
} from '../shared/api/novels';
import { createSessionId } from '../shared/lib/session';
import type { ChapterIndexEntry, ChapterIndexResponse } from '../shared/types/novels';
import { LAST_PIPELINE_KEY } from './PipelineResumePage';

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

function chapterNoFromId(chapterId: string): number | null {
  const match = /^chapter_(\\d+)$/.exec(String(chapterId || ''));
  if (!match) {
    return null;
  }
  const value = Number.parseInt(match[1], 10);
  return Number.isFinite(value) ? value : null;
}

function chapterStatus(chapter: ChapterIndexEntry): string {
  return String(chapter.status || '').trim();
}

function stepProgress(chapters: ChapterIndexEntry[], doneSet: Set<string>, failedSet: Set<string>) {
  const total = chapters.length;
  const done = chapters.filter((ch) => doneSet.has(chapterStatus(ch))).length;
  const failed = chapters.filter((ch) => failedSet.has(chapterStatus(ch))).length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  return { total, done, failed, pct };
}

export function PipelinePage() {
  const { novelId: routeNovelId } = useParams<{ novelId: string }>();
  const novelId = routeNovelId?.trim() || '';
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [selectedStep, setSelectedStep] = useState<'full' | '1' | '2' | '3' | '4' | '5'>('full');
  const [force, setForce] = useState(false);
  const [redoChapter, setRedoChapter] = useState('');
  const [showLogs, setShowLogs] = useState(true);
  const [logLines, setLogLines] = useState('220');
  const [failedOnly, setFailedOnly] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!novelId) {
      return;
    }
    const resumePath = `/novels/${encodeURIComponent(novelId)}/pipeline`;
    try {
      window.localStorage.setItem(LAST_PIPELINE_KEY, resumePath);
    } catch {
      // ignore storage errors (private mode, etc.)
    }
  }, [novelId]);

  const novelQuery = useQuery({
    queryKey: ['novel', novelId],
    queryFn: () => getNovel(novelId),
    enabled: Boolean(novelId),
    refetchInterval: (query) => (query.state.data?.status === 'processing' ? 1000 : 5000),
  });

  const chapterIndexQuery = useQuery({
    queryKey: ['chapterIndex', novelId],
    queryFn: async (): Promise<ChapterIndexResponse | null> => {
      try {
        return await getChapterIndex(novelId);
      } catch (error) {
        if (error instanceof AxiosError && error.response?.status === 404) {
          return null;
        }
        throw error;
      }
    },
    enabled: Boolean(novelId),
    retry: false,
    refetchInterval: (query) => (novelQuery.data?.status === 'processing' ? 1200 : 6000),
  });

  const novel = novelQuery.data;
  const hasSource = Boolean(novel?.source?.filename);
  const jobId = novel?.last_job_id?.trim() || '';

  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'running' || status === 'queued' ? 1000 : false;
    },
  });

  const linesValue = useMemo(() => {
    const raw = logLines.trim();
    if (!raw) {
      return 220;
    }
    const value = Number.parseInt(raw, 10);
    if (!Number.isFinite(value) || value <= 0) {
      return 220;
    }
    return Math.max(1, Math.min(value, 2000));
  }, [logLines]);

  const logQuery = useQuery({
    queryKey: ['jobLogs', jobId, showLogs, linesValue],
    queryFn: () => getJobLogs(jobId, linesValue),
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

  const chapters = chapterIndexQuery.data?.chapters || [];
  const hasChapterIndex = chapters.length > 0;

  const job = jobQuery.data;
  const jobStatus = job?.status || '';
  const jobActive = jobStatus === 'running' || jobStatus === 'queued';
  const progressPct = Math.round(Math.max(0, Math.min(1, job?.progress ?? 0)) * 100);

  const redoChapterValue = useMemo(() => {
    const raw = redoChapter.trim();
    if (!raw) {
      return undefined;
    }
    if (!/^\\d+$/.test(raw)) {
      return NaN;
    }
    const value = Number.parseInt(raw, 10);
    if (!Number.isFinite(value) || value <= 0) {
      return NaN;
    }
    return value;
  }, [redoChapter]);

  const redoInvalid = redoChapter.trim() !== '' && !Number.isFinite(redoChapterValue as number);
  const numericSelectedStep = selectedStep === 'full' ? null : Number.parseInt(selectedStep, 10);

  const runDisabledReason = useMemo(() => {
    if (jobActive) {
      return '已有作业在运行中';
    }
    if (redoInvalid) {
      return 'redo_chapter 必须是正整数';
    }
    if (numericSelectedStep == null || numericSelectedStep === 1) {
      if (!hasSource) {
        return '请先上传 txt';
      }
      return null;
    }
    if (!hasChapterIndex) {
      return '请先运行 Step1 生成章节索引';
    }
    return null;
  }, [jobActive, redoInvalid, numericSelectedStep, hasSource, hasChapterIndex]);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => uploadNovel(novelId, file),
    onMutate: () => setActionError(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['novel', novelId] });
      queryClient.invalidateQueries({ queryKey: ['chapterIndex', novelId] });
    },
    onError: (error) => setActionError(normalizeError(error)),
  });

  const runMutation = useMutation({
    mutationFn: async () => {
      const payload: { step?: number; force?: boolean; redo_chapter?: number } = {};
      if (numericSelectedStep != null) {
        payload.step = numericSelectedStep;
      }
      if (force) {
        payload.force = true;
      }
      if (redoChapterValue && Number.isFinite(redoChapterValue)) {
        payload.redo_chapter = redoChapterValue;
      }
      return runPipeline(novelId, payload);
    },
    onMutate: () => setActionError(null),
    onSuccess: () => {
      setShowLogs(true);
      queryClient.invalidateQueries({ queryKey: ['novel', novelId] });
      queryClient.invalidateQueries({ queryKey: ['chapterIndex', novelId] });
      queryClient.invalidateQueries({ queryKey: ['novels'] });
    },
    onError: (error) => setActionError(normalizeError(error)),
  });

  const openChat = () => {
    const sessionId = createSessionId();
    navigate(`/novels/${encodeURIComponent(novelId)}/chat/${encodeURIComponent(sessionId)}`);
  };

  const failureChapters = useMemo(() => {
    const failed = chapters.filter((ch) => chapterStatus(ch).includes('failed'));
    return failed.sort((a, b) => (chapterNoFromId(a.chapter_id) || 0) - (chapterNoFromId(b.chapter_id) || 0));
  }, [chapters]);

  const step2 = useMemo(
    () =>
      stepProgress(
        chapters,
        new Set(['scenes_done', 'annotated_done', 'annotation_failed', 'vectorized', 'vectorize_failed']),
        new Set(['scenes_failed']),
      ),
    [chapters],
  );

  const step3 = useMemo(
    () =>
      stepProgress(
        chapters,
        new Set(['annotated_done', 'vectorized', 'vectorize_failed']),
        new Set(['annotation_failed']),
      ),
    [chapters],
  );

  const step4 = useMemo(
    () => stepProgress(chapters, new Set(['vectorized']), new Set(['vectorize_failed'])),
    [chapters],
  );

  const filteredChapters = useMemo(() => {
    if (!failedOnly) {
      return chapters;
    }
    return chapters.filter((ch) => chapterStatus(ch).includes('failed'));
  }, [chapters, failedOnly]);

  if (!novelId) {
    return <Navigate to="/library" replace />;
  }

  return (
    <div className="library-wrap">
      <header className="glass-panel library-head pipeline-head">
        <div>
          <p className="label">Pipeline Console</p>
          <h1 className="library-title">{novel?.title || novelId}</h1>
          <p className="muted">
            <span className={`status-chip status-${novel?.status || 'unknown'}`}>
              {statusLabel(novel?.status || '')}
            </span>{' '}
            <span className="mono">ID: {novelId}</span>
          </p>
        </div>
        <div className="novel-actions">
          <button type="button" className="soft-button" onClick={() => navigate('/library')}>
            返回库
          </button>
          <button type="button" className="soft-button" onClick={openChat} disabled={!hasSource}>
            进入聊天
          </button>
        </div>
      </header>

      {novelQuery.isError ? (
        <section className="glass-panel error-box" role="alert">
          {normalizeError(novelQuery.error)}
        </section>
      ) : null}

      {actionError ? (
        <section className="glass-panel error-box" role="alert">
          {actionError}
        </section>
      ) : null}

      {novelQuery.isLoading ? <section className="glass-panel empty-state">加载中...</section> : null}

      {novel ? (
        <section className="glass-panel pipeline-controls">
          <div className="novel-meta grid-2">
            <div className="meta-box">
              <p className="label">Source</p>
              <p className="meta-line">
                <span className="mono">{novel.source?.filename || '未上传'}</span>
              </p>
              <p className="muted">
                {formatBytes(novel.source?.bytes)}，{novel.source?.char_count ?? '-'} 字，
                {novel.source?.line_count ?? '-'} 行
              </p>
            </div>
            <div className="meta-box">
              <p className="label">Job</p>
              <p className="meta-line">
                <span className="mono">{jobId || '-'}</span>
              </p>
              <p className="muted">
                {jobStatus
                  ? `状态：${jobStatus}，Step：${job?.current_step ?? '-'}，进度：${progressPct}%`
                  : '暂无作业'}
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

          <div className="pipeline-toolbar">
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
              disabled={uploadMutation.isPending || runMutation.isPending}
            >
              上传 txt
            </button>

              <label className="pipeline-field">
                <span className="label">Step</span>
                <select
                  className="glass-input"
                  value={selectedStep}
                  onChange={(event) => setSelectedStep(event.target.value as typeof selectedStep)}
                >
                  <option value="full">Full (1~5)</option>
                  <option value="1">Step1</option>
                  <option value="2">Step2</option>
                  <option value="3">Step3</option>
                  <option value="4">Step4</option>
                  <option value="5">Step5</option>
                </select>
              </label>

              <label className="pipeline-field">
                <span className="label">Redo Chapter</span>
                <input
                  className="glass-input"
                  value={redoChapter}
                  onChange={(event) => setRedoChapter(event.target.value)}
                  placeholder="例如 12"
                  inputMode="numeric"
                />
              </label>

              <label className="toggle-row pipeline-toggle">
                <span className="label">Force</span>
                <input
                  type="checkbox"
                  checked={force}
                  onChange={(event) => setForce(event.target.checked)}
                />
              </label>

              <button
                type="button"
                className="primary-button"
                onClick={() => runMutation.mutate()}
                disabled={Boolean(runDisabledReason) || runMutation.isPending}
                title={runDisabledReason || undefined}
              >
                运行
              </button>
          </div>
        </section>
      ) : null}

        <section className="pipeline-grid">
          <article className="glass-panel step-card">
            <p className="label">Step1</p>
            <h2 className="step-title">章节拆分</h2>
            <p className="muted">
              {hasChapterIndex
                ? `已生成索引，章节数：${chapters.length}`
                : '尚未生成 chapter_index.json'}
            </p>
          </article>

          <article className="glass-panel step-card">
            <p className="label">Step2</p>
            <h2 className="step-title">场景切分</h2>
            <p className="muted">
              {step2.total ? (
                <>
                  完成 {step2.done}/{step2.total}，失败 {step2.failed}，进度 {step2.pct}%
                </>
              ) : (
                '等待 Step1'
              )}
            </p>
          </article>

          <article className="glass-panel step-card">
            <p className="label">Step3</p>
            <h2 className="step-title">场景标注</h2>
            <p className="muted">
              {step3.total ? (
                <>
                  完成 {step3.done}/{step3.total}，失败 {step3.failed}，进度 {step3.pct}%
                </>
              ) : (
                '等待 Step2'
              )}
            </p>
          </article>

          <article className="glass-panel step-card">
            <p className="label">Step4</p>
            <h2 className="step-title">向量化</h2>
            <p className="muted">
              {step4.total ? (
                <>
                  完成 {step4.done}/{step4.total}，失败 {step4.failed}，进度 {step4.pct}%
                </>
              ) : (
                '等待 Step3'
              )}
            </p>
            <p className="muted">
              {typeof (novel?.stats as Record<string, unknown> | undefined)?.vector_db === 'object'
                ? `向量库点数：${
                    (novel?.stats as Record<string, any>)?.vector_db?.total_points ?? '-'
                  }`
                : null}
            </p>
          </article>

          <article className="glass-panel step-card">
            <p className="label">Step5</p>
            <h2 className="step-title">角色档案</h2>
            <p className="muted">
              已生成：{(novel?.stats as Record<string, any>)?.profiles_total ?? '-'} 个（本次：
              {(novel?.stats as Record<string, any>)?.profiles_generated ?? '-'}）
            </p>
          </article>
        </section>

        {failureChapters.length ? (
          <section className="glass-panel pipeline-failures">
            <p className="label">Failures</p>
            <h2 className="panel-title">失败章节</h2>
            <div className="tag-list">
              {failureChapters.slice(0, 24).map((ch) => (
                <span key={ch.chapter_id} className="tag-chip">
                  {chapterNoFromId(ch.chapter_id) ?? ch.chapter_id}:{' '}
                  {String(ch.title || '').trim() || ch.chapter_id} ({chapterStatus(ch) || 'failed'})
                </span>
              ))}
              {failureChapters.length > 24 ? (
                <span className="tag-chip">... +{failureChapters.length - 24}</span>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="glass-panel pipeline-chapters">
          <div className="pipeline-section-head">
            <div>
              <p className="label">Chapters</p>
              <h2 className="panel-title">章节状态</h2>
              <p className="muted">
                {chapters.length ? `共 ${chapters.length} 章` : '暂无章节索引（先运行 Step1）'}
              </p>
            </div>
            <label className="toggle-row">
              <span className="label">只看失败</span>
              <input
                type="checkbox"
                checked={failedOnly}
                onChange={(event) => setFailedOnly(event.target.checked)}
              />
            </label>
          </div>

          {filteredChapters.length ? (
            <div className="chapter-table-wrap">
              <table className="chapter-table">
                <thead>
                  <tr>
                    <th scope="col">#</th>
                    <th scope="col">Title</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="mono">
                      Chars
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredChapters.map((ch) => {
                    const status = chapterStatus(ch);
                    const failed = status.includes('failed');
                    return (
                      <tr key={ch.chapter_id} className={failed ? 'chapter-row-failed' : undefined}>
                        <td className="mono">{chapterNoFromId(ch.chapter_id) ?? '-'}</td>
                        <td>{String(ch.title || '').trim() || ch.chapter_id}</td>
                        <td className="mono">{status || '-'}</td>
                        <td className="mono">{ch.char_count ?? '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">暂无数据</div>
          )}
        </section>

        {jobId ? (
          <section className="glass-panel pipeline-logs">
            <div className="pipeline-section-head">
              <div>
                <p className="label">Logs</p>
                <h2 className="panel-title">作业日志</h2>
                <p className="muted mono">{jobId}</p>
              </div>
              <div className="pipeline-log-controls">
                <label className="pipeline-field">
                  <span className="label">Lines</span>
                  <input
                    className="glass-input"
                    value={logLines}
                    onChange={(event) => setLogLines(event.target.value)}
                    inputMode="numeric"
                  />
                </label>
                <button
                  type="button"
                  className="soft-button"
                  onClick={() => setShowLogs((v) => !v)}
                >
                  {showLogs ? '收起日志' : '查看日志'}
                </button>
              </div>
            </div>

            {showLogs ? (
              <pre className="log-box">
                {logQuery.isLoading ? '加载中...' : logQuery.data?.text || '暂无日志'}
              </pre>
            ) : null}

            {job?.result ? (
              <div className="pipeline-result">
                <p className="label">Result</p>
                <pre className="json-box">{JSON.stringify(job.result, null, 2)}</pre>
              </div>
            ) : null}
          </section>
        ) : null}
    </div>
  );
}
