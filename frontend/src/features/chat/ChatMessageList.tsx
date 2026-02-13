import { motion, useReducedMotion } from 'framer-motion';
import type { ChatMessage } from '../../store/chatStore';

interface ChatMessageListProps {
  messages: ChatMessage[];
  isSending: boolean;
}

function citationLabel(chapter: string | null, scene: number | null): string {
  if (!chapter) {
    return 'unknown';
  }
  if (scene === null || scene === undefined) {
    return chapter;
  }
  return `${chapter} / scene ${scene}`;
}

export function ChatMessageList({ messages, isSending }: ChatMessageListProps) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <div className="message-list glass-panel">
      {messages.length === 0 ? (
        <div className="empty-state">
          <p>输入你的剧情问题，系统会按会话进度检索证据并生成回答。</p>
        </div>
      ) : null}

      {messages.map((message, index) => (
        <motion.article
          key={message.id}
          className={`message-row ${message.role === 'user' ? 'is-user' : 'is-assistant'}`}
          initial={
            shouldReduceMotion
              ? false
              : {
                  opacity: 0,
                  y: 10,
                }
          }
          animate={
            shouldReduceMotion
              ? undefined
              : {
                  opacity: 1,
                  y: 0,
                }
          }
          transition={{ duration: 0.18, delay: index * 0.02 }}
        >
          <div className={`bubble ${message.role === 'user' ? 'bubble-user' : 'bubble-assistant'}`}>
            <p>{message.content}</p>
            {message.citations.length > 0 ? (
              <div className="citation-inline-list">
                {message.citations.slice(0, 3).map((item) => (
                  <span key={`${message.id}-${item.source_id}-${item.scene_index}`} className="citation-pill">
                    {citationLabel(item.chapter, item.scene_index)}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </motion.article>
      ))}

      {isSending ? (
        <div className="message-row is-assistant">
          <div className="bubble bubble-assistant loading-bubble" aria-live="polite">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        </div>
      ) : null}
    </div>
  );
}
