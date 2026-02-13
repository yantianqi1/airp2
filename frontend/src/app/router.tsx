import { Navigate, createBrowserRouter } from 'react-router-dom';
import { SessionEntryPage } from '../pages/SessionEntryPage';
import { ChatPage } from '../pages/ChatPage';
import { LibraryPage } from '../pages/LibraryPage';
import { PipelinePage } from '../pages/PipelinePage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/library" replace />,
  },
  {
    path: '/library',
    element: <LibraryPage />,
  },
  {
    path: '/session',
    element: <SessionEntryPage />,
  },
  {
    path: '/chat/:sessionId',
    element: <ChatPage />,
  },
  {
    path: '/novels/:novelId/chat/:sessionId',
    element: <ChatPage />,
  },
  {
    path: '/novels/:novelId/pipeline',
    element: <PipelinePage />,
  },
  {
    path: '*',
    element: <Navigate to="/library" replace />,
  },
]);
