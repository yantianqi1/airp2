import { FormEvent, useState } from 'react';
import { SearchIcon, SendIcon } from '../../shared/components/icons';

interface ChatComposerProps {
  busy: boolean;
  debugMode: boolean;
  onSend: (message: string) => void;
  onRetrieveOnly: (message: string) => void;
}

export function ChatComposer({ busy, debugMode, onSend, onRetrieveOnly }: ChatComposerProps) {
  const [value, setValue] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const message = value.trim();
    if (!message || busy) {
      return;
    }
    onSend(message);
    setValue('');
  };

  const retrieveOnly = () => {
    const message = value.trim();
    if (!message || busy) {
      return;
    }
    onRetrieveOnly(message);
  };

  return (
    <form className="composer glass-panel" onSubmit={submit}>
      <label className="sr-only" htmlFor="chat-composer-input">
        输入消息
      </label>
      <textarea
        id="chat-composer-input"
        className="glass-input composer-input"
        value={value}
        rows={3}
        onChange={(event) => setValue(event.target.value)}
        placeholder="输入消息，例如：许七安目前和朱县令的关系如何？"
      />
      <div className="composer-actions">
        {debugMode ? (
          <button type="button" className="soft-button" onClick={retrieveOnly} disabled={busy}>
            <SearchIcon aria-hidden="true" />
            仅检索证据
          </button>
        ) : null}
        <button type="submit" className="primary-button" disabled={busy}>
          <SendIcon aria-hidden="true" />
          发送
        </button>
      </div>
    </form>
  );
}
