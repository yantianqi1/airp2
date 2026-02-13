import { FormEvent, useState } from 'react';

interface SessionConfigPanelProps {
  sessionId: string;
  unlockedChapter: number;
  activeCharacters: string[];
  debugMode: boolean;
  onUnlockedChapterChange: (value: number) => void;
  onAddCharacter: (name: string) => void;
  onRemoveCharacter: (name: string) => void;
  onDebugModeChange: (enabled: boolean) => void;
  onRefreshSession: () => void;
}

export function SessionConfigPanel({
  sessionId,
  unlockedChapter,
  activeCharacters,
  debugMode,
  onUnlockedChapterChange,
  onAddCharacter,
  onRemoveCharacter,
  onDebugModeChange,
  onRefreshSession,
}: SessionConfigPanelProps) {
  const [characterDraft, setCharacterDraft] = useState('');

  const submitCharacter = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = characterDraft.trim();
    if (!value) {
      return;
    }
    onAddCharacter(value);
    setCharacterDraft('');
  };

  return (
    <section className="panel-group">
      <div className="glass-panel panel-head">
        <p className="label">Session ID</p>
        <p className="session-id">{sessionId}</p>
        <button className="soft-button" type="button" onClick={onRefreshSession}>
          刷新会话
        </button>
      </div>

      <div className="glass-panel panel-block">
        <label className="label" htmlFor="unlocked-chapter">
          已解锁章节上限
        </label>
        <input
          id="unlocked-chapter"
          type="number"
          min={0}
          value={unlockedChapter}
          onChange={(event) => onUnlockedChapterChange(Number(event.target.value || 0))}
          className="glass-input"
        />
      </div>

      <div className="glass-panel panel-block">
        <p className="label">活跃角色</p>
        <form className="inline-form" onSubmit={submitCharacter}>
          <input
            value={characterDraft}
            onChange={(event) => setCharacterDraft(event.target.value)}
            className="glass-input"
            placeholder="添加角色名"
            aria-label="添加活跃角色"
          />
          <button className="soft-button" type="submit">
            添加
          </button>
        </form>
        <div className="tag-list">
          {activeCharacters.length === 0 ? <p className="muted">暂无角色过滤</p> : null}
          {activeCharacters.map((item) => (
            <button
              key={item}
              className="tag-chip"
              type="button"
              onClick={() => onRemoveCharacter(item)}
              aria-label={`移除角色 ${item}`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="glass-panel panel-block">
        <label className="toggle-row" htmlFor="debug-mode-toggle">
          <span className="label">调试模式（先检索再回复）</span>
          <input
            id="debug-mode-toggle"
            type="checkbox"
            checked={debugMode}
            onChange={(event) => onDebugModeChange(event.target.checked)}
          />
        </label>
      </div>
    </section>
  );
}
