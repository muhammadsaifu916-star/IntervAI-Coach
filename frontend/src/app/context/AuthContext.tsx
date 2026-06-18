import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';

export type UserRole = 'jobseeker' | 'employer';

export interface User {
  user_id: string;
  email: string;
  email_verified?: boolean;
  full_name: string;
  phone: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

interface SignupResponse {
  message: string;
  email: string;
  verification_required: boolean;
}

export interface CandidateProfile {
  profile_id: string;
  user_id: string;
  bio: string;
  years_experience: number;
  experience_tier: string;
  skills: string[];
  projects_summary: string;
  final_score: number;
  published: boolean;
  job_role?: string;
  resume_score?: number;
  quiz_score?: number;
  interview_score?: number;
  quiz_attempts?: number;
  quiz_last_attempt?: string;
  quiz_cooldown_until?: string | null;
  interview_attempts?: number;
  interview_last_attempt?: string;
  interview_cooldown_until?: string | null;

  resume_feedback?: {
    scores: {
      grammar: number;
      formatting: number;
      keywords: number;
      actionVerbs: number;
      length: number;
    };
    suggestions: {
      type: string;
      title: string;
      description: string;
    }[];
  };

  resume_quiz_unlocked?: boolean;
  latest_resume?: any;
}

interface AuthContextType {
  user: User | null;
  profile: CandidateProfile | null;
  login: (email: string, password: string) => Promise<User>;
  signup: (
    email: string,
    password: string,
    fullName: string,
    phone: string,
    role: UserRole
  ) => Promise<SignupResponse>;
  verifyEmailOtp: (email: string, otp: string, password: string) => Promise<User>;
  resendEmailOtp: (email: string) => Promise<void>;
  logout: () => void;
  updateProfile: (profile: Partial<CandidateProfile>) => void;
  refreshUser: () => Promise<void>;
  isAuthenticated: boolean;
  canTakeQuiz: () => { allowed: boolean; reason?: string; cooldownEnd?: Date };
  canTakeInterview: () => { allowed: boolean; reason?: string; cooldownEnd?: Date };
  isLoading: boolean;
  authFetch: (url: string, options?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const createDefaultProfile = (realUser: User): CandidateProfile => ({
  profile_id: 'profile_' + realUser.user_id,
  user_id: realUser.user_id,
  bio: '',
  years_experience: 0,
  experience_tier: 'Entry Level',
  skills: [],
  projects_summary: '',
  final_score: 0,
  published: false,
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    const storedProfile = localStorage.getItem('profile');

    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        localStorage.removeItem('user');
      }
    }

    if (storedProfile) {
      try {
        setProfile(JSON.parse(storedProfile));
      } catch {
        localStorage.removeItem('profile');
      }
    }
    setIsLoading(false);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setProfile(null);
    localStorage.removeItem('user');
    localStorage.removeItem('profile');
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
  }, []);

  const authFetch = useCallback(async (url: string, options: RequestInit = {}): Promise<Response> => {
    const token = localStorage.getItem('accessToken');

    const isFormData = options.body instanceof FormData;

    const headers = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
      Authorization: `Bearer ${token}`,
    };

    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (res.status !== 401) return res;

    // Access token expired — try to refresh
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) {
      logout();
      throw new Error('Session expired. Please log in again.');
    }

    const refreshRes = await fetch(`${API_BASE_URL}/api/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: refreshToken }),
    });

    if (!refreshRes.ok) {
      logout();
      throw new Error('Session expired. Please log in again.');
    }

    const { access } = await refreshRes.json();
    localStorage.setItem('accessToken', access);

    const retryHeaders = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
      Authorization: `Bearer ${access}`,
    };

    return fetch(url, {
      ...options,
      headers: retryHeaders,
    });
  }, [logout]);

  const applyUserData = useCallback((userData: any, realUser: User) => {
    if (realUser.role !== 'jobseeker') {
      setProfile(null);
      localStorage.removeItem('profile');
      return;
    }

    const storedProfile = localStorage.getItem('profile');
    const parsedProfile = storedProfile ? JSON.parse(storedProfile) : null;

    const backendProfileData: Partial<CandidateProfile> = {
      latest_resume: userData.latest_resume ?? undefined,
    };

    if (userData.latest_resume) {
      backendProfileData.job_role = userData.latest_resume.job_role;
      backendProfileData.years_experience = userData.latest_resume.years_experience;
      backendProfileData.experience_tier = userData.latest_resume.experience_tier;
      backendProfileData.resume_score = userData.latest_resume.score;
      backendProfileData.resume_feedback = userData.latest_resume.feedback;
      backendProfileData.resume_quiz_unlocked = userData.latest_resume.quiz_unlocked;
    } else {
      // No resume on the server (e.g. it was just deleted). Explicitly clear
      // every resume-derived field, otherwise the stale value from the cached
      // localStorage profile survives the { ...baseProfile, ...backendProfileData }
      // merge below and the dashboard keeps showing the old score as "passed".
      // Mirrors the quiz/interview else branches.
      backendProfileData.job_role = undefined;
      backendProfileData.years_experience = 0;
      backendProfileData.experience_tier = 'Entry Level';
      backendProfileData.resume_score = undefined;
      backendProfileData.resume_feedback = undefined;
      backendProfileData.resume_quiz_unlocked = undefined;
    }

    if (userData.latest_quiz) {
      backendProfileData.quiz_score = userData.latest_quiz.score;
      backendProfileData.quiz_last_attempt = userData.latest_quiz.submitted_at;
    } else {
      backendProfileData.quiz_score = undefined;
      backendProfileData.quiz_last_attempt = undefined;
    }

    // Cooldown lives on the user and survives a resume re-upload (which wipes
    // sessions), so read it from the top-level field, not from latest_quiz.
    backendProfileData.quiz_cooldown_until = userData.quiz_cooldown_until ?? null;

    backendProfileData.quiz_attempts = userData.quiz_attempts ?? 0;

    if (userData.latest_interview) {
      backendProfileData.interview_score = userData.latest_interview.score;
      backendProfileData.interview_last_attempt = userData.latest_interview.submitted_at;
    } else {
      backendProfileData.interview_score = undefined;
      backendProfileData.interview_last_attempt = undefined;
    }

    backendProfileData.interview_cooldown_until = userData.interview_cooldown_until ?? null;

    backendProfileData.interview_attempts = userData.interview_attempts ?? 0;

    if (userData.final_score !== undefined) {
      backendProfileData.final_score = userData.final_score;
    }

    if (userData.candidate_profile) {
      backendProfileData.bio = userData.candidate_profile.bio;
      backendProfileData.skills = userData.candidate_profile.skills;
      backendProfileData.projects_summary = userData.candidate_profile.projects_summary;
      backendProfileData.published = userData.candidate_profile.published;
    }

    const baseProfile =
      parsedProfile && parsedProfile.user_id === realUser.user_id
        ? parsedProfile
        : createDefaultProfile(realUser);

    const finalProfile = {
      ...baseProfile,
      ...backendProfileData,
    };

    setProfile(finalProfile);
    localStorage.setItem('profile', JSON.stringify(finalProfile));
  }, []);

  const login = async (email: string, password: string) => {
    const response = await fetch(`${API_BASE_URL}/api/token/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: email, password }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);

      let message = 'Invalid email or password';
      let emailNotVerified = false;

      if (errorData) {
        if (typeof errorData.detail === 'string') {
          message = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          message = errorData.detail[0];
        }

        if (errorData.email_not_verified) {
          emailNotVerified = true;
        }
      }

      const error = new Error(message) as Error & {
        emailNotVerified?: boolean;
        email?: string;
      };

      error.emailNotVerified = emailNotVerified;
      const rawErrorEmail = errorData?.email;

      error.email = Array.isArray(rawErrorEmail)
        ? String(rawErrorEmail[0])
        : rawErrorEmail || email;

      throw error;
    }

    const tokenData = await response.json();
    localStorage.setItem('accessToken', tokenData.access);
    localStorage.setItem('refreshToken', tokenData.refresh);

    const userResponse = await fetch(`${API_BASE_URL}/api/users/me/`, {
      headers: { Authorization: `Bearer ${tokenData.access}` },
    });

    if (!userResponse.ok) throw new Error('Failed to fetch user details');

    const userData = await userResponse.json();
    const fullName = `${userData.first_name || ''} ${userData.last_name || ''}`.trim() || userData.email;

    const realUser: User = {
      user_id: String(userData.id),
      email: userData.email,
      full_name: fullName,
      phone: userData.phone || '',
      role: userData.role,
      is_active: true,
      created_at: new Date().toISOString(),
    };

    setUser(realUser);
    localStorage.setItem('user', JSON.stringify(realUser));

    applyUserData(userData, realUser);

    return realUser;
  };

  const refreshUser = useCallback(async () => {
    if (!user) return;

    try {
      const res = await authFetch(`${API_BASE_URL}/api/users/me/`);

      if (!res.ok) return;

      const userData = await res.json();
      applyUserData(userData, user);
    } catch {
      // Do not crash page if refresh fails.
    }
  }, [user, authFetch, applyUserData]);

  useEffect(() => {
    if (!user) return;
    if (!localStorage.getItem('accessToken')) return;

    refreshUser();
  }, [user?.user_id, refreshUser]);

  const signup = async (
    email: string,
    password: string,
    fullName: string,
    phone: string,
    role: UserRole,
  ) => {
    const nameParts = fullName.trim().split(' ');
    const firstName = nameParts[0] || '';
    const lastName = nameParts.slice(1).join(' ') || '';

    const response = await fetch(`${API_BASE_URL}/api/users/register/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: email,
        email,
        password,
        role,
        phone,
        first_name: firstName,
        last_name: lastName,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);

      let message = 'Signup failed. Please try again.';

      if (errorData && typeof errorData === 'object') {
        const firstKey = Object.keys(errorData)[0];
        const firstError = errorData[firstKey];

        if (Array.isArray(firstError)) {
          message = firstError[0];
        } else if (typeof firstError === 'string') {
          message = firstError;
        }
      }

      throw new Error(message);
    }

    const data = await response.json();
    return data;
  };

  const verifyEmailOtp = async (email: string, otp: string, password: string) => {
    const response = await fetch(`${API_BASE_URL}/api/users/verify-email/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, otp }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);

      let message = 'OTP verification failed. Please try again.';

      if (errorData && typeof errorData === 'object') {
        const firstKey = Object.keys(errorData)[0];
        const firstError = errorData[firstKey];

        if (Array.isArray(firstError)) {
          message = firstError[0];
        } else if (typeof firstError === 'string') {
          message = firstError;
        }
      }

      throw new Error(message);
    }

    return login(email, password);
  };


  const resendEmailOtp = async (email: string) => {
    const response = await fetch(`${API_BASE_URL}/api/users/resend-otp/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);

      let message = 'Could not resend OTP. Please try again.';

      if (errorData && typeof errorData === 'object') {
        const firstKey = Object.keys(errorData)[0];
        const firstError = errorData[firstKey];

        if (Array.isArray(firstError)) {
          message = firstError[0];
        } else if (typeof firstError === 'string') {
          message = firstError;
        }
      }

      throw new Error(message);
    }
  };

  const updateProfile = useCallback((updatedProfile: Partial<CandidateProfile>) => {
    setProfile((currentProfile) => {
      if (!currentProfile) return currentProfile;
      const newProfile = { ...currentProfile, ...updatedProfile };
      localStorage.setItem('profile', JSON.stringify(newProfile));
      return newProfile;
    });
  }, []);

  const canTakeQuiz = useCallback((): { allowed: boolean; reason?: string; cooldownEnd?: Date } => {
    if (user?.role !== 'jobseeker') {
      return { allowed: false, reason: 'This feature is only available to job seekers.' };
    }

    if (profile?.resume_score == null || profile.resume_score < 70) {
      return {
        allowed: false,
        reason: 'You need a resume score of 70% or above to take the quiz.',
      };
    }

    if ((profile?.quiz_score ?? 0) >= 70) {
      return {
        allowed: false,
        reason: 'You have already passed the quiz.',
      };
    }

    if (profile?.quiz_cooldown_until) {
      const until = new Date(profile.quiz_cooldown_until);

      if (until > new Date()) {
        return {
          allowed: false,
          reason: 'Quiz is currently on cooldown. Please try again later.',
          cooldownEnd: until,
        };
      }
    }

    return { allowed: true };
  }, [profile, user]);

  const canTakeInterview = useCallback((): { allowed: boolean; reason?: string; cooldownEnd?: Date } => {
    if (user?.role !== 'jobseeker') {
      return { allowed: false, reason: 'This feature is only available to job seekers.' };
    }
    if (profile?.quiz_score == null || profile.quiz_score < 70) {
      return { allowed: false, reason: 'You need a quiz score of 70% or above to take the interview.' };
    }

    if ((profile?.interview_score ?? 0) >= 70) {
      return {
        allowed: false,
        reason: 'You have already passed the interview.',
      };
    }

    if (profile?.interview_cooldown_until) {
      const until = new Date(profile.interview_cooldown_until);
      if (until > new Date()) {
        return {
          allowed: false,
          reason: 'Interview is on cooldown. Please try again later.',
          cooldownEnd: until,
        };
      }
    }

    return { allowed: true };
  }, [profile, user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        login,
        signup,
        verifyEmailOtp,
        resendEmailOtp,
        logout,
        updateProfile,
        refreshUser,
        isAuthenticated: !!user,
        isLoading,
        canTakeQuiz,
        canTakeInterview,
        authFetch,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};