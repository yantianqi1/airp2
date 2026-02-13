import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion, useReducedMotion } from 'framer-motion';
import { FormEvent, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import { getMe, login } from '../shared/api/auth';

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

export function LoginPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const shouldReduceMotion = useReducedMotion();
  const meQuery = useQuery({ queryKey: ['me'], queryFn: getMe, retry: 0 });

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: async () => login(username, password),
    onMutate: () => setError(null),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['me'] });
      navigate('/library');
    },
    onError: (err) => setError(normalizeError(err)),
  });

  if (meQuery.data?.mode === 'user') {
    return <Navigate to="/library" replace />;
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    loginMutation.mutate();
  };

  return (
    <div className="entry-shell">
      <motion.section
        className="entry-card glass-panel"
        initial={shouldReduceMotion ? false : { opacity: 0, y: 20 }}
        animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <p className="entry-kicker">AIRP Console</p>
        <h1>登录</h1>
        <p className="muted">游客可以聊天。登录后可导入与管理你的小说。</p>

        {error ? (
          <div className="glass-panel error-box" role="alert">
            {error}
          </div>
        ) : null}

        <form onSubmit={submit} className="entry-form">
          <label htmlFor="username" className="label">
            Username
          </label>
          <input
            id="username"
            className="glass-input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            placeholder="例如 user_01"
            autoComplete="username"
          />

          <label htmlFor="password" className="label">
            Password
          </label>
          <input
            id="password"
            className="glass-input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="至少 8 位"
            autoComplete="current-password"
          />

          <div className="entry-actions">
            <button type="submit" className="primary-button" disabled={loginMutation.isPending}>
              登录
            </button>
            <Link className="soft-button" to="/register">
              去注册
            </Link>
          </div>
        </form>
      </motion.section>
    </div>
  );
}

