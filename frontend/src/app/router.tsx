import { Navigate, createBrowserRouter } from 'react-router-dom';
import { AppLayout } from '../features/layout/AppLayout';
import { SessionEntryPage } from '../pages/SessionEntryPage';
import { ChatPage } from '../pages/ChatPage';
import { ChatResumePage } from '../pages/ChatResumePage';
import { LibraryPage } from '../pages/LibraryPage';
import { PipelinePage } from '../pages/PipelinePage';
import { PipelineResumePage } from '../pages/PipelineResumePage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/library" replace />,
      },
      {
        path: 'library',
        element: <LibraryPage />,
      },
      {
        path: 'session',
        element: <SessionEntryPage />,
      },
      {
        path: 'chat',
        element: <ChatResumePage />,
      },
      {
        path: 'chat/:sessionId',
        element: <ChatPage />,
      },
      {
        path: 'novels/:novelId/chat/:sessionId',
        element: <ChatPage />,
      },
      {
        path: 'pipeline',
        element: <PipelineResumePage />,
      },
      {
        path: 'novels/:novelId/pipeline',
        element: <PipelinePage />,
      },
      {
        path: '*',
        element: <Navigate to="/library" replace />,
      },
    ],
  },
]);
