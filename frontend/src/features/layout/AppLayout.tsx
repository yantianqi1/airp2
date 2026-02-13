import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AppSidebar } from './AppSidebar';

export function AppLayout() {
  const location = useLocation();
  const shouldReduceMotion = useReducedMotion();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="app-frame">
      <AppSidebar />
      <div className="app-viewport">
        <AnimatePresence initial={false} mode="wait">
          <motion.div
            key={location.pathname}
            className="app-page"
            initial={shouldReduceMotion ? false : { opacity: 0, y: 10, filter: 'blur(3px)' }}
            animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={shouldReduceMotion ? undefined : { opacity: 0, y: -8, filter: 'blur(2px)' }}
            transition={{ duration: 0.22, ease: [0.2, 0.9, 0.2, 1] }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

