import { motion, useReducedMotion } from 'framer-motion';
import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createSessionId } from '../shared/lib/session';

export function SessionEntryPage() {
  const navigate = useNavigate();
  const shouldReduceMotion = useReducedMotion();
  const [sessionId, setSessionId] = useState(createSessionId());

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = sessionId.trim();
    if (!normalized) {
      return;
    }
    navigate(`/chat/${encodeURIComponent(normalized)}`);
  };

  return (
    <div className="entry-shell">
      <motion.section
        className="entry-card glass-panel"
        initial={shouldReduceMotion ? false : { opacity: 0, y: 20 }}
        animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <p className="entry-kicker">AIRP RP Console</p>
        <h1>证据驱动的角色扮演前端</h1>
        <p className="entry-lead">
          支持会话恢复、章节防剧透边界、引用证据面板和调试检索链路。
        </p>

        <form onSubmit={submit} className="entry-form">
          <label htmlFor="session-id" className="label">
            Session ID
          </label>
          <input
            id="session-id"
            className="glass-input"
            value={sessionId}
            onChange={(event) => setSessionId(event.target.value)}
            placeholder="输入会话 ID"
          />

          <div className="entry-actions">
            <button
              type="button"
              className="soft-button"
              onClick={() => setSessionId(createSessionId())}
            >
              生成新会话
            </button>
            <button type="submit" className="primary-button">
              进入会话
            </button>
          </div>
        </form>
      </motion.section>
    </div>
  );
}
