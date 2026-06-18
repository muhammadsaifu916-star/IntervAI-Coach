import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { motion, AnimatePresence } from 'motion/react';
import {
  Clock,
  CheckCircle2,
  ArrowLeft,
  ArrowRight,
  AlertTriangle,
  Trophy,
  XCircle,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { RadioGroup, RadioGroupItem } from '../components/ui/radio-group';
import { Label } from '../components/ui/label';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { API_BASE_URL } from '../config';

interface Question {
  id: number;
  text: string;
  type: 'mcq' | 'scenario';
  options: string[];
  difficulty: string;
}

// Human-friendly "time remaining" until a cooldown ends (e.g. "2 days 5 hours",
// "3 hours 12 minutes"). Used instead of a calendar date so short cooldowns read
// correctly rather than collapsing to "today". Kept identical to Interview.tsx.
function formatTimeRemaining(end: Date): string {
  const ms = end.getTime() - Date.now();
  if (ms <= 0) return 'Available now';

  const totalMinutes = Math.floor(ms / 60000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;

  const parts: string[] = [];
  if (days) parts.push(`${days} ${days === 1 ? 'day' : 'days'}`);
  if (hours) parts.push(`${hours} ${hours === 1 ? 'hour' : 'hours'}`);
  if (!days && minutes) parts.push(`${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`);

  return parts.length ? `Available in ${parts.join(' ')}` : 'Available in less than a minute';
}

export default function Quiz() {
  const navigate = useNavigate();
  const { profile, updateProfile, authFetch, refreshUser } = useAuth();
  const [showWarningPage, setShowWarningPage] = useState(true);
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [answers, setAnswers] = useState<{ [key: number]: number }>({});
  const answersRef = useRef<{ [key: number]: number }>({});
  const isSubmittingRef = useRef(false);
  const [timeLeft, setTimeLeft] = useState(0);
  const [isLocked, setIsLocked] = useState(false);
  const [cooldownEnd, setCooldownEnd] = useState<Date | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [showEndConfirm, setShowEndConfirm] = useState(false);
  const [attemptNumber, setAttemptNumber] = useState<number | null>(null);
  const [jobRole, setJobRole] = useState<string | null>(null);
  const isUnloadingRef = useRef(false);

  useEffect(() => {
    const handleBeforeUnload = () => {
      isUnloadingRef.current = true;
    };

    const handlePageHide = () => {
      isUnloadingRef.current = true;
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('pagehide', handlePageHide);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('pagehide', handlePageHide);
    };
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    sessionStorage.setItem(
      `quiz:${sessionId}`,
      JSON.stringify({ answers, currentQuestion })
    );
  }, [answers, currentQuestion, sessionId]);

  const startQuiz = async () => {
    document.documentElement.requestFullscreen?.().catch(() => { });
    setShowWarningPage(false);
    setIsLoading(true);
    setApiError(null);

    try {
      const res = await authFetch(`${API_BASE_URL}/api/quizzes/start/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_role: profile?.job_role ?? 'Software Engineer' }),
      });

      const data = await res.json();

      if (res.status === 403) {
        if (data.already_passed || data.cooldown_until) {
          toast.info(data.already_passed ? 'You have already passed the quiz.' : 'Quiz is on cooldown.');
          navigate('/quiz-report', { replace: true });
          return;
        }

        setIsLocked(true);
        if (data.cooldown_until) setCooldownEnd(new Date(data.cooldown_until));
        setApiError(data.error);
        return;
      }

      if (!res.ok) throw new Error('Failed to start quiz.');

      setSessionId(data.session_id);
      setTimeLeft(data.time_limit_seconds ?? 1200);
      setAttemptNumber(data.attempt_number ?? null);
      setJobRole(data.job_role ?? null);

      setQuestions(
        data.questions.map((q: any) => ({
          id: q.id,
          text: q.question_text,
          type: q.question_type,
          options: q.options,
          difficulty: q.difficulty,
        }))
      );

      const saved = sessionStorage.getItem(`quiz:${data.session_id}`);

      if (saved) {
        try {
          const { answers: savedAnswers, currentQuestion: savedIdx } = JSON.parse(saved);
          answersRef.current = savedAnswers || {};
          setAnswers(savedAnswers || {});
          setCurrentQuestion(savedIdx ?? 0);
        } catch {
          sessionStorage.removeItem(`quiz:${data.session_id}`);
          answersRef.current = {};
          setAnswers({});
          setCurrentQuestion(0);
        }
      } else {
        answersRef.current = {};
        setAnswers({});
        setCurrentQuestion(0);
      }

      if (data.resumed) {
        toast.info('Quiz resumed. Continue where you left off.');
      }
    } catch {
      setApiError('Could not load the quiz. Please try again.');
      toast.error('Could not load quiz.');
    } finally {
      setIsLoading(false);
    }
  };

  // Timer countdown
  useEffect(() => {
    if (showWarningPage || isLocked || isLoading || !sessionId) return;

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          handleSubmit(answersRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [showWarningPage, isLocked, isLoading, sessionId]);

  // Tab / focus / fullscreen violation detection
  useEffect(() => {
    let violationTimer: number | undefined;

    const clearViolationTimer = () => {
      if (violationTimer) {
        window.clearTimeout(violationTimer);
        violationTimer = undefined;
      }
    };

    const runViolation = () => {
      if (
        !showWarningPage &&
        !isLoading &&
        !isLocked &&
        sessionId &&
        !isSubmittingRef.current &&
        !isUnloadingRef.current
      ) {
        handleSubmit(answersRef.current, true);
      }
    };

    const scheduleViolation = () => {
      clearViolationTimer();
      violationTimer = window.setTimeout(runViolation, 150);
    };

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        clearViolationTimer();
        return;
      }

      scheduleViolation();
    };

    const handleWindowBlur = () => {
      scheduleViolation();
    };

    const handleWindowFocus = () => {
      clearViolationTimer();
    };

    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        runViolation();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleWindowBlur);
    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('fullscreenchange', handleFullscreenChange);

    return () => {
      clearViolationTimer();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleWindowBlur);
      window.removeEventListener('focus', handleWindowFocus);
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
    };
  }, [showWarningPage, isLoading, isLocked, sessionId]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleAnswerSelect = (questionId: number, answerIndex: number) => {
    const updated = { ...answersRef.current, [questionId]: answerIndex };
    answersRef.current = updated;
    setAnswers(updated);
  };

  // Opens the in-app confirmation modal.
  // NOTE: we intentionally avoid window.confirm() here — a native dialog forces
  // the browser to leave fullscreen / blur the window, which trips the violation
  // detector and auto-submits the quiz even when the user clicks "Cancel".
  const handleEndQuiz = () => {
    setShowEndConfirm(true);
  };

  const confirmEndQuiz = () => {
    setShowEndConfirm(false);
    handleSubmit();
  };

  const cancelEndQuiz = () => {
    setShowEndConfirm(false);
  };

  const handleSubmit = async (
    answersOverride?: { [key: number]: number },
    terminatedByTabSwitch = false
  ) => {
    if (isLocked || !sessionId || isSubmittingRef.current) return;
    isSubmittingRef.current = true;

    const source = answersOverride ?? answersRef.current;

    // Build payload: { "42": 1, "43": 2, ... }
    const answersPayload: Record<string, number> = {};
    Object.entries(source).forEach(([qId, idx]) => {
      answersPayload[String(qId)] = idx;
    });

    try {
      const res = await authFetch(`${API_BASE_URL}/api/quizzes/submit/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ session_id: sessionId, answers: answersPayload }),
      });

      if (!res.ok) throw new Error('Submission failed.');

      const data = await res.json();
      const calculatedScore: number = data.score;

      sessionStorage.removeItem(`quiz:${sessionId}`);

      updateProfile({
        quiz_score: calculatedScore,
        quiz_cooldown_until: data.cooldown_until ?? null,
        quiz_last_attempt: new Date().toISOString(),
        quiz_attempts: (profile?.quiz_attempts || 0) + 1,
      });

      await refreshUser();

      if (data.passed) {
        toast.success('Congratulations! You passed the quiz!');
      } else if (terminatedByTabSwitch) {
        toast.error('Security violation detected! Quiz was submitted.');
      } else {
        toast.error('Quiz not passed. View your report for feedback and cooldown details.');
      }

      navigate('/quiz-report', { replace: true });
      return;
    } catch {
      isSubmittingRef.current = false;
      toast.error('Failed to submit quiz. Please try again.');
    }
  };

  const progressPercentage =
    questions.length > 0 ? ((currentQuestion + 1) / questions.length) * 100 : 0;
  const renderQuestionText = (text: string) => {
    const blankLineIdx = text.indexOf('\n\n');
    if (blankLineIdx === -1) return <span>{text}</span>;

    const prose = text.slice(0, blankLineIdx).trim();
    const code = text.slice(blankLineIdx + 2).trim();

    return (
      <>
        <span>{prose}</span>
        <pre className="mt-3 bg-gray-50 text-gray-800 rounded-lg p-4 text-sm font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed border border-gray-200">
          <code>{code}</code>
        </pre>
      </>
    );
  };

  if (apiError && !isLocked) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-500">{apiError}</p>
      </div>
    );
  }

  if (isLocked) {
    const timeUntilUnlock = cooldownEnd ? Math.ceil((cooldownEnd.getTime() - new Date().getTime()) / (1000 * 60 * 60 * 24)) : 0;
    const previousScore = profile?.quiz_score || 0;

    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="max-w-2xl w-full"
        >
          <Card className="border-0 shadow-2xl">
            <CardHeader className="text-center pb-0">
              <div className="w-20 h-20 mx-auto mb-4 bg-gradient-to-br from-orange-600 to-red-600 rounded-full flex items-center justify-center">
                <Clock className="w-10 h-10 text-white" />
              </div>
              <CardTitle className="text-3xl mb-2">Quiz Locked</CardTitle>
              <CardDescription>You're in a cooldown period</CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-6 mb-6">
                <div className="text-center">
                  <p className="text-lg font-semibold text-orange-900 mb-2">Cooldown Period Active</p>
                  <div className="text-4xl font-bold text-orange-600 mb-2">
                    {timeUntilUnlock} {timeUntilUnlock === 1 ? 'Day' : 'Days'}
                  </div>
                  <p className="text-sm text-orange-700">
                    Time remaining until you can retake the quiz
                  </p>
                  <p className="text-xs text-orange-600 mt-2">
                    Available on: {cooldownEnd?.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
                  </p>
                </div>
              </div>

              <div className="bg-gray-50 rounded-lg p-4 mb-6">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-medium text-gray-600">Your Previous Score</span>
                  <span className="font-bold text-gray-900">{previousScore}%</span>
                </div>
                <Progress value={previousScore} className="h-2" />
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-blue-900 mb-1">Why is this locked?</p>
                    <p className="text-sm text-blue-700">
                      You scored below 70% on your previous attempt. Use this time to review the learning resources and improve your skills before retrying.
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Button
                  variant="outline"
                  onClick={() => navigate('/progress-report', { state: { tab: 'resources' } })}
                >
                  View Resources
                </Button>
                <Button onClick={() => navigate('/dashboard')}>
                  Back to Dashboard
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    );
  }

  // Quiz Instruction Page
  if (showWarningPage) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="max-w-3xl w-full"
        >
          <Card className="border-0 shadow-2xl">
            <CardHeader className="text-center pb-0">
              <div className="w-20 h-20 mx-auto mb-4 bg-gradient-to-br from-blue-600 to-purple-600 rounded-full flex items-center justify-center">
                <AlertTriangle className="w-10 h-10 text-white" />
              </div>
              <CardTitle className="text-3xl mb-2">Quiz Instructions</CardTitle>
              <CardDescription>Please read carefully before starting</CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="space-y-6">
                {/* Important Rules */}
                <div className="bg-red-50 border-2 border-red-200 rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertTriangle className="w-6 h-6 text-red-600 flex-shrink-0 mt-1" />
                    <div>
                      <h3 className="font-bold text-red-900 text-lg mb-3">Critical Rules</h3>
                      <ul className="space-y-3 text-red-800">
                        <li className="flex items-start gap-2">
                          <span className="text-red-600 font-bold leading-none mt-[2px]">•</span>
                          <span><strong>Stay in fullscreen and focused on this screen</strong> - Switching tabs, opening other windows, using split screen, or leaving fullscreen may submit your attempt</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <span className="text-red-600 font-bold leading-none mt-[2px]">•</span>

                          <span><strong>Complete within the time limit</strong> - The quiz will auto-submit when time expires</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Quiz Details */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
                  <h3 className="font-bold text-blue-900 text-lg mb-3">Quiz Details</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-blue-800">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
                        <CheckCircle2 className="w-6 h-6 text-white" />
                      </div>
                      <div>
                        <p className="text-sm text-blue-600">Total Questions</p>
                        <p className="font-bold text-blue-900">
                          {questions.length || 15} Questions
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Clock className="w-6 h-6 text-white" />
                      </div>
                      <div>
                        <p className="text-sm text-blue-600">Time Limit</p>
                        <p className="font-bold text-blue-900">20 Minutes</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Trophy className="w-6 h-6 text-white" />
                      </div>
                      <div>
                        <p className="text-sm text-blue-600">Passing Score</p>
                        <p className="font-bold text-blue-900">70% or Higher</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
                        <AlertTriangle className="w-6 h-6 text-white" />
                      </div>
                      <div>
                        <p className="text-sm text-blue-600">Question Types</p>
                        <p className="font-bold text-blue-900">MCQ & Scenario</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Tips */}
                <div className="bg-green-50 border border-green-200 rounded-lg p-6">
                  <h3 className="font-bold text-green-900 text-lg mb-3">Tips for Success</h3>
                  <ul className="space-y-2 text-green-800">
                    <li className="flex items-start gap-2">
                      <span className="text-green-600 mt-1">✓</span>
                      <span>Read each question carefully before selecting your answer</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-green-600 mt-1">✓</span>
                      <span>You can navigate between questions using Previous/Next buttons</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-green-600 mt-1">✓</span>
                      <span>Use the question overview panel to track your progress</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-green-600 mt-1">✓</span>
                      <span>Ensure stable internet connection before starting</span>
                    </li>
                  </ul>
                </div>

                {/* Consequences */}
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <Clock className="w-5 h-5 text-orange-600 flex-shrink-0 mt-0.5" />
                    <div className="text-sm">
                      <p className="font-semibold text-orange-900 mb-1">Retake Policy</p>
                      <p className="text-orange-700">
                        If you score below 70%, you'll enter a cooldown period before you can retake the quiz. Use this time to review learning materials.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="grid grid-cols-2 gap-4 mt-8">
                <Button
                  variant="outline"
                  onClick={() => navigate('/dashboard')}
                  className="h-12"
                >
                  Cancel
                </Button>
                <Button
                  onClick={startQuiz}
                  className="h-12 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700"
                >
                  I Understand, Start Quiz
                  <ArrowRight className="w-5 h-5 ml-2" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500 text-lg">Loading your quiz…</p>
      </div>
    );
  }

  const question = questions[currentQuestion];

  if (!question) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="max-w-md w-full"
        >
          <Card className="border-0 shadow-2xl">
            <CardHeader className="text-center">
              <div className="w-16 h-16 mx-auto mb-4 bg-yellow-100 rounded-full flex items-center justify-center">
                <AlertTriangle className="w-8 h-8 text-yellow-600" />
              </div>
              <CardTitle>No Questions Available</CardTitle>
              <CardDescription>
                No questions are available right now. Please go back to your dashboard and try again later.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={() => navigate('/dashboard')} className="w-full">
                Back to Dashboard
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* ── End Quiz confirmation modal (in-app, so it never leaves fullscreen) ── */}
      <AnimatePresence>
        {showEndConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
            onClick={cancelEndQuiz}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.2 }}
              className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                  <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
                <div className="flex-1">
                  <h3 className="text-lg font-bold text-gray-900 mb-1">End quiz?</h3>
                  <p className="text-sm text-gray-600">
                    Your current answers will be submitted and this attempt will count.
                    This cannot be undone.
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-6">
                <Button variant="outline" onClick={cancelEndQuiz}>
                  Cancel
                </Button>
                <Button
                  onClick={confirmEndQuiz}
                  className="bg-red-600 hover:bg-red-700 text-white"
                >
                  End Quiz
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                  <CheckCircle2 className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-gray-900">
                    {jobRole ? jobRole : 'Technical Quiz'}
                  </h1>
                  <p className="text-sm text-gray-600">
                    {attemptNumber ? `Attempt #${attemptNumber} · ` : ''}Question {currentQuestion + 1} of {questions.length}
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="bg-orange-50 border border-orange-200 rounded-lg px-4 py-2 flex items-center gap-2">
                <Clock className="w-5 h-5 text-orange-600" />
                <span className="font-mono font-bold text-orange-900">{formatTime(timeLeft)}</span>
              </div>
              {/* ── End Quiz Button: confirms, submits answers, then shows results screen ── */}
              <button
                onClick={handleEndQuiz}
                className="group bg-red-600 hover:bg-red-700 active:bg-red-800 text-white font-semibold px-4 py-2 rounded-lg flex items-center gap-2 shadow-md hover:shadow-lg hover:shadow-red-200 transition-all duration-200 hover:scale-105 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-2"
                aria-label="End quiz early"
              >
                <XCircle className="w-5 h-5 transition-transform duration-200 group-hover:rotate-90" />
                <span className="hidden sm:inline">End Quiz</span>
              </button>
            </div>
          </div>
          <div className="mt-4">
            <Progress value={progressPercentage} className="h-2" />
          </div>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentQuestion}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
          >
            <Card className="border-0 shadow-2xl">
              <CardHeader>
                <div className="flex items-start justify-between mb-2">
                  <CardTitle className="text-lg font-semibold flex-1 leading-relaxed text-gray-900 min-w-0">
                    {renderQuestionText(question.text)}
                  </CardTitle>
                  <div className={`px-3 py-1 rounded-full text-xs font-semibold ${question.difficulty === 'easy' ? 'bg-green-100 text-green-700' :
                    question.difficulty === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                    {question.difficulty.toUpperCase()}
                  </div>
                </div>
                <CardDescription>
                  {question.type === 'scenario' ? 'Scenario-based Question' : 'Multiple Choice Question'}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <RadioGroup
                  value={answers[question.id]?.toString()}
                  onValueChange={(value) => handleAnswerSelect(question.id, parseInt(value))}
                >
                  <div className="space-y-3">
                    {question.options.map((option, index) => (
                      <motion.div
                        key={index}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <div
                          className={`group border-2 rounded-lg p-4 cursor-pointer transition-all ${answers[question.id] === index
                            ? 'border-blue-600 bg-blue-50'
                            : 'border-gray-200 hover:border-blue-400 hover:bg-blue-50'
                            }`}
                          onClick={() => handleAnswerSelect(question.id, index)}
                        >
                          {/* A/B/C/D label with hover effect */}
                          <div className="flex items-center gap-3">
                            <span
                              className={`text-sm font-bold w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${answers[question.id] === index
                                ? 'bg-blue-600 text-white scale-110'
                                : 'bg-gray-100 text-gray-600 group-hover:bg-blue-200'
                                }`}
                            >
                              {['A', 'B', 'C', 'D'][index]}
                            </span>
                            <RadioGroupItem
                              value={index.toString()}
                              id={`option-${index}`}
                              className="sr-only"
                            />
                            <Label
                              htmlFor={`option-${index}`}
                              className="flex-1 cursor-pointer text-gray-800"
                            >
                              {option}
                            </Label>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </RadioGroup>

                <div className="flex items-center justify-between mt-8 pt-6 border-t">
                  <Button
                    variant="outline"
                    onClick={() => setCurrentQuestion(Math.max(0, currentQuestion - 1))}
                    disabled={currentQuestion === 0}
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Previous
                  </Button>

                  {currentQuestion === questions.length - 1 ? (
                    <Button onClick={() => handleSubmit()} size="lg">
                      Submit Quiz
                      <CheckCircle2 className="w-4 h-4 ml-2" />
                    </Button>
                  ) : (
                    <Button
                      onClick={() => setCurrentQuestion(currentQuestion + 1)}
                      disabled={answers[question.id] === undefined}
                    >
                      Next
                      <ArrowRight className="w-4 h-4 ml-2" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Warning */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
              className="mt-6"
            >
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-red-800">
                  <p className="font-semibold mb-1">Important Warnings:</p>
                  <ul className="list-disc list-inside space-y-1 text-red-700">
                    <li>Do not switch tabs or open other windows - quiz will be automatically terminated</li>

                    <li>Complete the quiz within the time limit</li>
                  </ul>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </AnimatePresence>

        {/* Question Overview */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mt-6"
        >
          <Card className="border-0 shadow-lg">
            <CardHeader>
              <CardTitle className="text-lg">Question Overview</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
                {questions.map((q, index) => (
                  <button
                    key={q.id}
                    onClick={() => setCurrentQuestion(index)}
                    className={`w-10 h-10 rounded-lg flex items-center justify-center font-semibold transition-all ${currentQuestion === index
                      ? 'bg-blue-600 text-white'
                      : answers[q.id] !== undefined
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      }`}
                  >
                    {index + 1}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-4 mt-4 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 bg-blue-600 rounded"></div>
                  <span className="text-gray-600">Current</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 bg-green-100 border-2 border-green-700 rounded"></div>
                  <span className="text-gray-600">Answered</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 bg-gray-100 rounded"></div>
                  <span className="text-gray-600">Not Answered</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
