import { motion, useReducedMotion } from 'framer-motion';
import type { PropsWithChildren, ReactNode } from 'react';

interface AppShellGlassProps extends PropsWithChildren {
  left: ReactNode;
  right: ReactNode;
  topBar?: ReactNode;
}

export function AppShellGlass({ left, right, topBar, children }: AppShellGlassProps) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <div className="app-shell-wrap">
      {topBar ? <div className="mobile-top-bar glass-panel">{topBar}</div> : null}
      <motion.main
        className="app-shell-grid"
        initial={shouldReduceMotion ? false : { opacity: 0, y: 18 }}
        animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: [0.2, 0.9, 0.2, 1] }}
      >
        <aside className="shell-side shell-left">{left}</aside>
        <section className="shell-main">{children}</section>
        <aside className="shell-side shell-right">{right}</aside>
      </motion.main>
    </div>
  );
}
