import { Navigate, createBrowserRouter } from 'react-router-dom';
import { SessionEntryPage } from '../pages/SessionEntryPage';
import { ChatPage } from '../pages/ChatPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <SessionEntryPage />,
  },
  {
    path: '/chat/:sessionId',
    element: <ChatPage />,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);
