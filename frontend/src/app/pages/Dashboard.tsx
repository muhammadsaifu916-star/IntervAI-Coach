import React from 'react';
import { useNavigate } from 'react-router';
import { motion } from 'motion/react';
import {
  FileText, ClipboardList, Video, Award, Upload, TrendingUp,
  CheckCircle2, Clock, XCircle, BookOpen, LogOut, User,
  Eye, Briefcase,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import { useAuth } from '../context/AuthContext';
import { getExperienceDisplay } from '../utils/experienceDisplay';

// ── Helpers ───────────────────────────────────────────────────────────────────
const PASS_SCORE = 70;

/** Formats a future Date as a short cooldown remainder ("3d", "5h", "12m"). */
function formatCooldownRemaining(end: Date | null | undefined): string | null {
  if (!end) return null;
  const ms = end.getTime() - Date.now();
  if (ms <= 0) return null;
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));
  const hours = Math.floor(ms / (1000 * 60 * 60));
  const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
  if (days >= 1) return `${days}d`;
  if (hours >= 1) return `${hours}h`;
  return `${Math.max(1, minutes)}m`;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate();
  const { user, profile, logout, canTakeQuiz, canTakeInterview } = useAuth();

  // ── Resume ─────────────────────────────────────────────────────────────────
  const hasResumeScore = profile?.resume_score != null;
  const resumePassed = (profile?.resume_score ?? 0) >= PASS_SCORE;

  // ── Quiz ───────────────────────────────────────────────────────────────────
  const hasQuizScore = profile?.quiz_score != null;
  const quizPassed = (profile?.quiz_score ?? 0) >= PASS_SCORE;
  const quizAccess = canTakeQuiz();
  const quizCooldownActive = !!quizAccess.cooldownEnd && quizAccess.cooldownEnd > new Date();
  const quizCooldownLabel = formatCooldownRemaining(quizAccess.cooldownEnd);

  // ── Interview ──────────────────────────────────────────────────────────────
  const hasInterviewScore = profile?.interview_score != null;
  const interviewPassed = (profile?.interview_score ?? 0) >= PASS_SCORE;
  const interviewAccess = canTakeInterview();
  const interviewCooldownActive = !!interviewAccess.cooldownEnd
    && interviewAccess.cooldownEnd > new Date();
  const interviewCooldownLabel = formatCooldownRemaining(interviewAccess.cooldownEnd);

  // ── Publish ────────────────────────────────────────────────────────────────
  const isPublished = !!profile?.published;

  // ── Re-render every minute while ANY cooldown is active ─────────────────────
  const [, tick] = React.useReducer((x: number) => x + 1, 0);
  React.useEffect(() => {
    if (!quizCooldownActive && !interviewCooldownActive) return;
    const interval = setInterval(tick, 60_000);
    return () => clearInterval(interval);
  }, [quizCooldownActive, interviewCooldownActive]);

  // ── Build the pipeline ─────────────────────────────────────────────────────
  type StepStatus = 'completed' | 'available' | 'cooldown' | 'locked' | 'pending';
  interface Step {
    id: number;
    title: string;
    description: string;
    icon: any;
    status: StepStatus;
    score?: number | null;
    path: string;
    badgeLabel?: string;   // override for cooldown badge
    cta?: string;   // override for button label
  }

  const steps: Step[] = [
    // 1 — Resume
    // 1 — Resume
    {
      id: 1,
      title: 'Resume Review',
      description: resumePassed
        ? 'View your AI resume analysis report'
        : hasResumeScore
          ? 'Score below 70% — review suggestions and re-upload'
          : 'Upload your resume for AI analysis',
      icon: Upload,
      status: resumePassed ? 'completed'
        : hasResumeScore ? 'pending'
          : 'available',
      score: profile?.resume_score,
      path: hasResumeScore ? '/resume-feedback' : '/resume-upload',
      badgeLabel: hasResumeScore && !resumePassed ? 'Below 70%' : undefined,
      cta: resumePassed ? 'View Report'
        : hasResumeScore ? 'Improve Resume'
          : 'Start',
    },

    // 2 — Quiz
    {
      id: 2, title: 'Take Quiz', description: 'Complete the technical quiz', icon: ClipboardList,
      status: quizPassed ? 'completed'
        : quizCooldownActive ? 'cooldown'
          : quizAccess.allowed ? 'available'
            : 'locked',
      score: profile?.quiz_score,
      path: quizPassed || (hasQuizScore && quizCooldownActive) ? '/quiz-report' : '/quiz',
      badgeLabel: quizCooldownActive && quizCooldownLabel ? `Retry in ${quizCooldownLabel}` : undefined,
      cta: quizPassed ? 'View Report'
        : quizCooldownActive ? 'View Report'
          : hasQuizScore && !quizPassed ? 'Retake Quiz'
            : 'Start',
    },

    // 3 — Interview
    {
      id: 3, title: 'AI Interview', description: 'Complete the AI-powered interview', icon: Video,
      status: interviewPassed ? 'completed'
        : interviewCooldownActive ? 'cooldown'
          : quizPassed ? 'available'
            : 'locked',
      score: profile?.interview_score,
      path: interviewPassed || interviewCooldownActive
        ? '/interview-report'
        : '/interview',
      badgeLabel: interviewCooldownActive && interviewCooldownLabel ? `Retry in ${interviewCooldownLabel}` : undefined,
      cta: interviewPassed ? 'View Report'
        : interviewCooldownActive ? 'View Report'
          : hasInterviewScore ? 'Retake'
            : 'Start',
    },

    // 4 — Publish
    {
      id: 4, title: 'Publish Profile', description: 'Make your profile visible to employers', icon: Award,
      status: isPublished ? 'completed'
        : interviewPassed ? 'available'
          : 'locked',
      path: '/profile-publication',
      cta: isPublished ? 'Manage' : 'Publish',
    },
  ];

  // ── UI helpers ─────────────────────────────────────────────────────────────
  const getStatusIcon = (status: StepStatus) => ({
    completed: <CheckCircle2 className="w-5 h-5 text-green-600" />,
    available: <Clock className="w-5 h-5 text-blue-600" />,
    cooldown: <Clock className="w-5 h-5 text-amber-600" />,
    locked: <XCircle className="w-5 h-5 text-gray-400" />,
    pending: <Clock className="w-5 h-5 text-orange-600" />,
  })[status];

  const getStatusBadge = (status: StepStatus, label?: string) => ({
    completed: <Badge className="bg-green-100 text-green-700 hover:bg-green-100">Completed</Badge>,
    available: <Badge className="bg-blue-100  text-blue-700  hover:bg-blue-100">Available</Badge>,
    cooldown: <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100">{label ?? 'Cooldown'}</Badge>,
    locked: <Badge className="bg-gray-100  text-gray-600  hover:bg-gray-100">Locked</Badge>,
    pending: <Badge className="bg-orange-100 text-orange-700 hover:bg-orange-100">{label ?? 'Pending'}</Badge>,
  })[status];

  const completedSteps = steps.filter(s => s.status === 'completed').length;
  const progressPercentage = (completedSteps / steps.length) * 100;

  const handleLogout = () => { logout(); navigate('/'); };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
              <Award className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">IntervAI Coach</h1>
              <p className="text-sm text-gray-600">Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-gray-900">{user?.full_name}</p>
              <p className="text-xs text-gray-600">{user?.email}</p>
            </div>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4 mr-2" />Logout
            </Button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Welcome */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mb-8">
          <h2 className="text-3xl font-bold text-gray-900 mb-2">
            Welcome {user?.full_name?.split(' ')[0]}! 👋
          </h2>
          <p className="text-gray-600">Track your progress and continue your journey to landing your dream job.</p>
        </motion.div>

        {/* Published banner */}
        {isPublished && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
            <Card className="border-0 shadow-lg bg-gradient-to-r from-green-600 to-emerald-600 text-white">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-white/20 rounded-full flex items-center justify-center">
                      <CheckCircle2 className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="font-bold text-lg">Your profile is live!</p>
                      <p className="text-sm opacity-90">Employers can now discover you in the talent pool.</p>
                    </div>
                  </div>
                  <Button variant="secondary" size="sm" onClick={() => navigate('/profile-publication')}>
                    Manage Profile
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* Overall Progress */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}>
          <Card className="mb-8 border-0 shadow-lg">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Overall Progress</CardTitle>
                  <CardDescription>Complete all steps to publish your profile</CardDescription>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-bold text-blue-600">{completedSteps}/{steps.length}</div>
                  <div className="text-sm text-gray-600">Steps Completed</div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Progress value={progressPercentage} className="h-3" />
              <p className="text-sm text-gray-600 mt-2">{Math.round(progressPercentage)}% Complete</p>
            </CardContent>
          </Card>
        </motion.div>

        {/* Steps Grid */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          {steps.map((step, index) => {
            const tone =
              step.status === 'completed'
                ? 'green'
                : step.status === 'available'
                  ? 'blue'
                  : step.status === 'cooldown'
                    ? 'amber'
                    : step.status === 'pending'
                      ? 'orange'
                      : 'gray';

            const stepToneClasses: Record<string, { bg: string; text: string }> = {
              green: { bg: 'bg-green-100', text: 'text-green-600' },
              blue: { bg: 'bg-blue-100', text: 'text-blue-600' },
              amber: { bg: 'bg-amber-100', text: 'text-amber-600' },
              orange: { bg: 'bg-orange-100', text: 'text-orange-600' },
              gray: { bg: 'bg-gray-100', text: 'text-gray-400' },
            };

            const toneClass = stepToneClasses[tone];

            return (
              <motion.div
                key={step.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.2 + index * 0.1 }}
              >
                <Card className="border-0 shadow-lg hover:shadow-xl transition-shadow duration-300">
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-4">
                        <div
                          className={`w-12 h-12 rounded-lg flex items-center justify-center ${toneClass.bg}`}
                        >
                          <step.icon className={`w-6 h-6 ${toneClass.text}`} />
                        </div>

                        <div>
                          <CardTitle className="text-lg">{step.title}</CardTitle>
                          <CardDescription>{step.description}</CardDescription>
                        </div>
                      </div>

                      {getStatusIcon(step.status)}
                    </div>
                  </CardHeader>

                  <CardContent>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {getStatusBadge(step.status, step.badgeLabel)}

                        {step.score != null && (
                          <Badge variant="outline" className="font-semibold">
                            Score: {Math.round(step.score)}%
                          </Badge>
                        )}
                      </div>

                      {step.status !== 'locked' && (
                        <Button size="sm" onClick={() => navigate(step.path)}>
                          {step.cta ?? 'Start'}
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>

        {/* Quick Actions */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.6 }}>
          <Card className="border-0 shadow-lg">
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
              <CardDescription>Jump directly to important sections</CardDescription>
            </CardHeader>
            <CardContent>
              <div className={`grid sm:grid-cols-2 ${isPublished ? 'lg:grid-cols-4' : 'lg:grid-cols-3'} gap-4`}>
                <Button variant="outline" className="h-auto py-4 flex-col gap-2" onClick={() => navigate(hasResumeScore ? '/resume-feedback' : '/resume-upload')}>
                  <FileText className="w-5 h-5" /><span>View Resume</span>
                </Button>
                <Button variant="outline" className="h-auto py-4 flex-col gap-2" onClick={() => navigate('/progress-report', { state: { tab: 'resources' } })}>
                  <BookOpen className="w-5 h-5" /><span>Learning Resources</span>
                </Button>
                <Button variant="outline" className="h-auto py-4 flex-col gap-2" onClick={() => navigate('/progress-report')}>
                  <TrendingUp className="w-5 h-5" /><span>Progress Report</span>
                </Button>
                {isPublished && (
                  <Button variant="outline" className="h-auto py-4 flex-col gap-2 border-green-300 text-green-700 hover:bg-green-50" onClick={() => navigate('/profile-publication')}>
                    <Eye className="w-5 h-5" /><span>My Public Profile</span>
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Profile Stats */}
        {profile && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.7 }} className="mt-8">
            <Card className="border-0 shadow-lg">
              <CardHeader>
                <CardTitle>Profile Summary</CardTitle>
                <CardDescription>Your current profile information</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center p-4 bg-purple-50 rounded-lg">
                    <Briefcase className="w-6 h-6 text-purple-600 mx-auto mb-2" />
                    <div
                      className="text-xl font-bold text-purple-600 truncate"
                      title={profile.job_role || undefined}
                    >
                      {profile.job_role || '—'}
                    </div>
                    <div className="text-sm text-gray-600">Job Role</div>
                  </div>

                  <div className="text-center p-4 bg-blue-50 rounded-lg">
                    <User className="w-6 h-6 text-blue-600 mx-auto mb-2" />
                    <div className="text-xl font-bold text-blue-600 truncate">
                      {getExperienceDisplay(profile.years_experience, profile.experience_tier)}
                    </div>
                    <div className="text-sm text-gray-600">Experience Level</div>
                  </div>

                  <div className="text-center p-4 bg-green-50 rounded-lg">
                    <Award className="w-6 h-6 text-green-600 mx-auto mb-2" />
                    <div className="text-2xl font-bold text-green-600">
                      {Math.round(profile.final_score || 0)}%
                    </div>
                    <div className="text-sm text-gray-600">Final Score</div>
                  </div>

                  <div className={`text-center p-4 rounded-lg ${isPublished ? 'bg-emerald-50' : 'bg-orange-50'}`}>
                    {isPublished ? (
                      <CheckCircle2 className="w-6 h-6 text-emerald-600 mx-auto mb-2" />
                    ) : (
                      <Briefcase className="w-6 h-6 text-orange-600 mx-auto mb-2" />
                    )}

                    <div className={`text-2xl font-bold ${isPublished ? 'text-emerald-600' : 'text-orange-600'}`}>
                      {isPublished ? 'Live' : 'Draft'}
                    </div>

                    <div className="text-sm text-gray-600">Profile Status</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>
    </div >
  );
}
