import { createBrowserRouter, Outlet } from 'react-router';
import { AuthProvider } from './context/AuthContext';
import LoginSignup from './pages/LoginSignup';
import Dashboard from './pages/Dashboard';
import ResumeUpload from './pages/ResumeUpload';
import ResumeFeedback from './pages/ResumeFeedback';
import Quiz from './pages/Quiz';
import Interview from './pages/Interview';
import ProgressReport from './pages/ProgressReport';
import ProfilePublication from './pages/ProfilePublication';
import EmployerDashboard from './pages/EmployerDashboard';
import ProfileAccess from './pages/ProfileAccess';
import NotFound from './pages/NotFound';
import ProtectedRoute from './components/ProtectedRoute';
import QuizReport from './pages/QuizReport';
import InterviewReport from './pages/InterviewReport';

// Root layout: AuthProvider lives HERE (inside the router) so that
// useNavigate / useLocation are available inside AuthContext.
function RootLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}

export const router = createBrowserRouter([
  {
    path: '/',
    Component: RootLayout,
    children: [
      { index: true, Component: LoginSignup },

      {
        element: <ProtectedRoute allowedRoles={['jobseeker']} />,
        children: [
          { path: 'dashboard', Component: Dashboard },
          { path: 'resume-upload', Component: ResumeUpload },
          { path: 'resume-feedback', Component: ResumeFeedback },
          { path: 'quiz', Component: Quiz },
          { path: 'quiz-report', Component: QuizReport },
          { path: 'interview', Component: Interview },
          { path: 'interview-report', Component: InterviewReport },
          { path: 'progress-report', Component: ProgressReport },
          { path: 'profile-publication', Component: ProfilePublication },
        ],
      },
      {
        element: <ProtectedRoute allowedRoles={['employer']} />,
        children: [
          { path: 'employer-dashboard', Component: EmployerDashboard },
          { path: 'profile-access', Component: ProfileAccess },
        ],
      },

      { path: '*', Component: NotFound },
    ],
  },
]);
