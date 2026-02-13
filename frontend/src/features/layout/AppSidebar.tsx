import type { ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ChatBubbleIcon, LibraryIcon, PipelineIcon, PlusIcon } from '../../shared/components/icons';

function isChatRoute(pathname: string): boolean {
  return pathname === '/chat' || pathname.startsWith('/chat/') || pathname.includes('/chat/');
}

function isPipelineRoute(pathname: string): boolean {
  return pathname === '/pipeline' || pathname.includes('/pipeline');
}

function NavItem({
  to,
  active,
  label,
  icon,
}: {
  to: string;
  active: boolean;
  label: string;
  icon: ReactNode;
}) {
  return (
    <Link
      to={to}
      className={`app-nav-item${active ? ' is-active' : ''}`}
      aria-current={active ? 'page' : undefined}
      title={label}
      aria-label={label}
    >
      <span className="app-nav-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="app-nav-label">{label}</span>
    </Link>
  );
}

export function AppSidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const pathname = location.pathname;

  const libraryActive = pathname === '/library' || pathname.startsWith('/library/');
  const chatActive = isChatRoute(pathname);
  const pipelineActive = isPipelineRoute(pathname);

  const startNewSession = () => navigate('/session');

  return (
    <>
      <nav className="app-sidebar glass-panel" aria-label="Primary">
        <Link to="/library" className="app-brand" aria-label="AIRP Console">
          <span className="app-brand-mark" aria-hidden="true" />
        </Link>

        <div className="app-nav-stack">
          <NavItem to="/library" active={libraryActive} label="书库" icon={<LibraryIcon />} />
          <NavItem to="/chat" active={chatActive} label="聊天" icon={<ChatBubbleIcon />} />
          <NavItem to="/pipeline" active={pipelineActive} label="流水线" icon={<PipelineIcon />} />
        </div>

        <div className="app-sidebar-bottom">
          <button
            type="button"
            className="app-sidebar-action"
            onClick={startNewSession}
            title="新会话"
            aria-label="新会话"
          >
            <PlusIcon />
          </button>
        </div>
      </nav>

      <nav className="app-bottom-nav glass-panel" aria-label="Primary">
        <NavItem to="/library" active={libraryActive} label="书库" icon={<LibraryIcon />} />
        <NavItem to="/chat" active={chatActive} label="聊天" icon={<ChatBubbleIcon />} />
        <button
          type="button"
          className="app-bottom-action"
          onClick={startNewSession}
          title="新会话"
          aria-label="新会话"
        >
          <PlusIcon />
        </button>
        <NavItem to="/pipeline" active={pipelineActive} label="流水线" icon={<PipelineIcon />} />
      </nav>
    </>
  );
}
