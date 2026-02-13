import type { ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ChatBubbleIcon, LibraryIcon, PipelineIcon, PlusIcon } from '../../shared/components/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getMe, logout } from '../../shared/api/auth';

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
  const queryClient = useQueryClient();
  const meQuery = useQuery({ queryKey: ['me'], queryFn: getMe, retry: 0 });
  const mode = meQuery.data?.mode || 'guest';

  const libraryActive = pathname === '/library' || pathname.startsWith('/library/');
  const chatActive = isChatRoute(pathname);
  const pipelineActive = isPipelineRoute(pathname);

  const startNewSession = () => navigate('/session');

  const logoutMutation = useMutation({
    mutationFn: async () => logout(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['me'] });
      navigate('/library');
    },
  });

  return (
    <>
      <nav className="app-sidebar glass-panel" aria-label="Primary">
        <Link to="/library" className="app-brand" aria-label="AIRP Console">
          <span className="app-brand-mark" aria-hidden="true" />
        </Link>

        <div className="app-nav-stack">
          <NavItem to="/library" active={libraryActive} label="书库" icon={<LibraryIcon />} />
          <NavItem to="/chat" active={chatActive} label="聊天" icon={<ChatBubbleIcon />} />
          {mode === 'user' ? (
            <NavItem to="/pipeline" active={pipelineActive} label="流水线" icon={<PipelineIcon />} />
          ) : null}
        </div>

        <div className="app-sidebar-bottom">
          <div className="app-sidebar-auth">
            {mode === 'user' ? (
              <>
                <p className="muted mono">{meQuery.data?.user?.username || 'user'}</p>
                <button
                  type="button"
                  className="soft-button"
                  onClick={() => logoutMutation.mutate()}
                  disabled={logoutMutation.isPending}
                >
                  退出
                </button>
              </>
            ) : (
              <Link className="soft-button" to="/login">
                登录
              </Link>
            )}
          </div>
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
        {mode === 'user' ? (
          <NavItem to="/pipeline" active={pipelineActive} label="流水线" icon={<PipelineIcon />} />
        ) : null}
      </nav>
    </>
  );
}
