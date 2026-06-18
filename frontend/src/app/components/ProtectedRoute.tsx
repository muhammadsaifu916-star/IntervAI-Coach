import { Navigate, Outlet } from 'react-router';
import { useAuth, type UserRole } from '../context/AuthContext';

interface ProtectedRouteProps {
  allowedRoles?: UserRole[];
}

export default function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, user } = useAuth();

  if (isLoading) return null;

  if (!isAuthenticated || !user) {
    return <Navigate to="/" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    const redirectPath =
      user.role === 'jobseeker' ? '/dashboard' : '/employer-dashboard';

    return <Navigate to={redirectPath} replace />;
  }

  return <Outlet />;
}