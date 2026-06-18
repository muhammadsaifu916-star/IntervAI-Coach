import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  Trophy,
  CheckCircle2,
  XCircle,
  ArrowLeft,
  Target,
  BookOpen,
  Dumbbell,
  Link2,
  AlertTriangle,
  ChevronDown,
  Clock,
  Sparkles,
  ListChecks,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { useAuth } from '../context/AuthContext';
import { API_BASE_URL } from '../config';
import { toast } from 'sonner';

interface TopicPerformance {
  topic: string;
  correct: number;
  wrong: number;
  total: number;
  accuracy: number;
  strength: string;
  is_weak: boolean;
}

interface MistakeReview {
  question_text: string;
  selected_answer_text: string;
  correct_answer_text: string;
  explanation: string;
}

interface StudyPlanItem {
  priority: number;
  topic: string;
  key_concepts: string[];
  practice_focus: string[];
  resources: string[];
  mistakes_to_review: MistakeReview[];
  suggested_day: string;
  suggested_time: string;
}

interface ImprovementPlan {
  topic_performance: TopicPerformance[];
  weak_topics: string[];
  study_plan: StudyPlanItem[];
  summary: string;
}

interface QuizReportData {
  session_id: number;
  job_role?: string;
  attempt_number?: number;
  score: number;
  passed: boolean;
  correct: number;
  total: number;
  cooldown_until: string | null;
  interview_unlocked: boolean;
  questions: QuestionReview[];
  improvement_plan?: ImprovementPlan;
}

interface InterviewStatus {
  score: number | null;
  passed: boolean | null;
  cooldown_until: string | null;
}

interface QuestionReview {
  question_id: number;
  question_text: string;
  question_type: string;
  options: string[];
  selected_answer: number | null;
  selected_answer_text: string | null;
  correct_answer: number;
  correct_answer_text: string | null;
  is_correct: boolean;
  difficulty: string;
  topic?: string;
  subtopic?: string;
  explanation?: string;
}

/* ── Strength tier → colour tokens ─────────────────────────────────────────── */
type StrengthTone = {
  badge: string;
  bar: string;
  ring: string;
  text: string;
};

function strengthTone(strength: string, isWeak: boolean): StrengthTone {
  const s = strength.toLowerCase();
  if (s === 'strong') {
    return {
      badge: 'bg-emerald-100 text-emerald-700 border-emerald-200',
      bar: 'bg-emerald-500',
      ring: 'border-emerald-200 bg-emerald-50/60',
      text: 'text-emerald-700',
    };
  }
  if (s === 'average' && !isWeak) {
    return {
      badge: 'bg-amber-100 text-amber-700 border-amber-200',
      bar: 'bg-amber-500',
      ring: 'border-amber-200 bg-amber-50/60',
      text: 'text-amber-700',
    };
  }
  return {
    badge: 'bg-rose-100 text-rose-700 border-rose-200',
    bar: 'bg-rose-500',
    ring: 'border-rose-200 bg-rose-50/60',
    text: 'text-rose-700',
  };
}

/* A thin, self-coloured accuracy bar (so each topic can take its tier colour). */
function AccuracyBar({ value, barClass }: { value: number; barClass: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="h-2 w-full rounded-full bg-gray-200/80 overflow-hidden">
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${barClass}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export default function QuizReport() {
  const navigate = useNavigate();
  const { authFetch } = useAuth();

  const [report, setReport] = useState<QuizReportData | null>(null);
  const [interview, setInterview] = useState<InterviewStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Which study-plan cards are expanded (topic → open?). Priority #1 opens by default.
  const [openPlans, setOpenPlans] = useState<Record<string, boolean>>({});
  // Question-review filter.
  const [showIncorrectOnly, setShowIncorrectOnly] = useState(false);

  const getRetryTime = () => {
    if (!report?.cooldown_until) return null;

    const cooldownEnd = new Date(report.cooldown_until);
    const now = new Date();

    if (cooldownEnd <= now) {
      return 'You can retry the quiz now.';
    }

    const diffMs = cooldownEnd.getTime() - now.getTime();
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs / (1000 * 60)) % 60);

    if (hours > 0) {
      return `You can retry the quiz in ${hours} hour(s) and ${minutes} minute(s).`;
    }

    return `You can retry the quiz in ${minutes} minute(s).`;
  };

  const canRetryQuiz = () => {
    if (!report?.cooldown_until) return true;
    return new Date(report.cooldown_until) <= new Date();
  };

  // ── Interview gating (mirrors the resume → quiz gate in ResumeFeedback) ──
  const interviewPassed = interview?.passed === true;

  const interviewCooldownActive =
    !!interview?.cooldown_until && new Date(interview.cooldown_until) > new Date();

  // The interview is reachable only when the quiz is passed AND the interview
  // has not already been passed and is not currently on cooldown.
  const canStartInterview =
    !!report?.passed && !interviewPassed && !interviewCooldownActive;

  const getInterviewCooldownTime = () => {
    if (!interview?.cooldown_until) return null;

    const cooldownEnd = new Date(interview.cooldown_until);
    const now = new Date();

    if (cooldownEnd <= now) {
      return 'You can retry the interview now.';
    }

    const diffMs = cooldownEnd.getTime() - now.getTime();
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs / (1000 * 60)) % 60);

    if (hours > 0) {
      return `You can retry the interview in ${hours} hour(s) and ${minutes} minute(s).`;
    }

    return `You can retry the interview in ${minutes} minute(s).`;
  };

  useEffect(() => {
    const loadReport = async () => {
      try {
        const [quizRes, interviewRes] = await Promise.all([
          authFetch(`${API_BASE_URL}/api/quizzes/latest/`),
          authFetch(`${API_BASE_URL}/api/interviews/latest/`),
        ]);

        if (!quizRes.ok) {
          throw new Error('No quiz report found.');
        }

        const data: QuizReportData = await quizRes.json();
        setReport(data);

        // Open the first (highest-priority) study-plan card by default.
        const firstTopic = data.improvement_plan?.study_plan?.[0]?.topic;
        if (firstTopic) {
          setOpenPlans({ [firstTopic]: true });
        }

        // Interview is optional: a 404 simply means none has been taken yet.
        if (interviewRes.ok) {
          setInterview(await interviewRes.json());
        }
      } catch {
        toast.error('Could not load quiz report.');
      } finally {
        setIsLoading(false);
      }
    };

    loadReport();
  }, [authFetch]);

  const togglePlan = (topic: string) =>
    setOpenPlans((prev) => ({ ...prev, [topic]: !prev[topic] }));

  const renderQuestionText = (text: string, variant: 'correct' | 'incorrect' | 'neutral' = 'neutral') => {
    const blankLineIdx = text.indexOf('\n\n');
    if (blankLineIdx === -1) return <span>{text}</span>;

    const prose = text.slice(0, blankLineIdx).trim();
    const code = text.slice(blankLineIdx + 2).trim();

    const codeStyle =
      variant === 'correct'
        ? 'bg-emerald-100 text-emerald-900 border-emerald-300'
        : variant === 'incorrect'
          ? 'bg-rose-100 text-rose-900 border-rose-300'
          : 'bg-white text-gray-800 border-gray-200';

    return (
      <>
        <span>{prose}</span>
        <pre className={`mt-2 rounded-lg p-3 text-xs font-mono overflow-x-auto whitespace-pre leading-relaxed border shadow-sm ${codeStyle}`}>
          <code>{code}</code>
        </pre>
      </>
    );
  };

  const incorrectCount = useMemo(
    () => report?.questions.filter((q) => !q.is_correct).length ?? 0,
    [report],
  );

  const visibleQuestions = useMemo(() => {
    if (!report) return [];
    // Keep original numbering even when filtering.
    return report.questions
      .map((q, index) => ({ q, number: index + 1 }))
      .filter(({ q }) => (showIncorrectOnly ? !q.is_correct : true));
  }, [report, showIncorrectOnly]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500 text-lg">Loading quiz report...</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-xl w-full">
          <CardHeader>
            <CardTitle>No Quiz Report Found</CardTitle>
            <CardDescription>You have not completed a quiz yet.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => navigate('/dashboard')}>Back to Dashboard</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const passed = report.passed;
  const scoreGradient = 'from-blue-600 to-purple-600';

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex justify-center items-start p-4 sm:p-6">
      {/* Card is a fixed-height flex column: pinned header, scrolling body, pinned footer. */}
      <Card className="max-w-4xl w-full border-0 shadow-2xl flex flex-col max-h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-3rem)] overflow-hidden">
        {/* ── Pinned header: score + verdict ───────────────────────────────── */}
        <CardHeader className="text-center shrink-0 pb-5 border-b border-gray-100">
          <div className="w-16 h-16 mx-auto mb-3 rounded-full flex items-center justify-center bg-gradient-to-br from-blue-600 to-purple-600">
            <Trophy className="w-8 h-8 text-white" />
          </div>

          <CardTitle className="text-2xl mb-1">Quiz Report</CardTitle>
          <CardDescription>
            {report.attempt_number != null && report.job_role
              ? `Attempt #${report.attempt_number} · ${report.job_role}`
              : 'Your latest completed quiz result'}
          </CardDescription>

          <div className="mt-4 flex items-center justify-center gap-4">
            <div
              className={`text-5xl font-bold bg-gradient-to-r ${scoreGradient} bg-clip-text text-transparent`}
            >
              {report.score}%
            </div>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold border ${passed
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-rose-50 text-rose-700 border-rose-200'
                }`}
            >
              {passed ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
              {passed ? 'Passed' : 'Failed'}
            </span>
          </div>
        </CardHeader>

        {/* ── Scrolling body: everything detailed lives here ───────────────── */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-6 space-y-6 [scrollbar-gutter:stable]">
          {!passed && (
            <div className="bg-rose-50 border border-rose-200 rounded-lg p-4 flex items-start gap-3">
              <XCircle className="w-6 h-6 text-rose-600 flex-shrink-0" />
              <div>
                <p className="font-semibold text-rose-900">Quiz Not Passed</p>
                <p className="text-sm text-rose-700">
                  You need 70% or above to unlock the interview.
                </p>
                {report.cooldown_until && (
                  <p className="text-sm text-rose-700 mt-2 font-medium">{getRetryTime()}</p>
                )}
              </div>
            </div>
          )}

          {/* Correct-answers summary */}
          <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium text-gray-600">Correct Answers</span>
              <span className="font-bold text-gray-900">
                {report.correct} / {report.total}
              </span>
            </div>
            <Progress value={report.total > 0 ? (report.correct / report.total) * 100 : 0} />
          </div>

          {/* ── Improvement plan ──────────────────────────────────────────── */}
          {report.improvement_plan && (
            <section className="space-y-5">
              {/* Summary callout */}
              <div className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-blue-50 p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <Sparkles className="w-5 h-5 text-indigo-600" />
                  <h3 className="text-lg font-semibold text-indigo-950">Improvement Plan</h3>
                </div>
                <p className="text-sm text-indigo-900/80 leading-relaxed">
                  {report.improvement_plan.summary}
                </p>

                {report.improvement_plan.weak_topics.length > 0 && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-indigo-700/70">
                      Focus on
                    </span>
                    {report.improvement_plan.weak_topics.map((topic) => (
                      <span
                        key={topic}
                        className="inline-flex items-center gap-1 rounded-full bg-white/70 border border-indigo-200 px-2.5 py-0.5 text-xs font-medium text-indigo-800"
                      >
                        <Target className="w-3 h-3" />
                        {topic}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Topic performance */}
              {report.improvement_plan.topic_performance.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                    Topic Performance
                  </h4>
                  <div className="grid sm:grid-cols-2 gap-3">
                    {report.improvement_plan.topic_performance.map((topic) => {
                      const tone = strengthTone(topic.strength, topic.is_weak);
                      return (
                        <div
                          key={topic.topic}
                          className={`rounded-lg border p-3.5 ${tone.ring}`}
                        >
                          <div className="flex justify-between items-center gap-2 mb-2">
                            <p className="font-semibold text-gray-900 truncate">{topic.topic}</p>
                            <span
                              className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold ${tone.badge}`}
                            >
                              {topic.strength}
                            </span>
                          </div>
                          <div className="flex justify-between items-baseline mb-1.5">
                            <span className={`text-sm font-bold ${tone.text}`}>
                              {topic.accuracy}%
                            </span>
                            <span className="text-xs text-gray-500">
                              {topic.correct}/{topic.total} correct
                            </span>
                          </div>
                          <AccuracyBar value={topic.accuracy} barClass={tone.bar} />
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Personalised study roadmap — collapsible cards */}
              {report.improvement_plan.study_plan.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                    Personalized Study Roadmap
                  </h4>

                  {report.improvement_plan.study_plan.map((plan) => {
                    const isOpen = openPlans[plan.topic] ?? false;
                    return (
                      <div
                        key={plan.topic}
                        className="rounded-xl border border-gray-200 bg-white overflow-hidden transition-shadow hover:shadow-sm"
                      >
                        {/* Header / toggle */}
                        <button
                          type="button"
                          onClick={() => togglePlan(plan.topic)}
                          aria-expanded={isOpen}
                          className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="shrink-0 grid place-items-center w-7 h-7 rounded-full bg-indigo-600 text-white text-xs font-bold">
                              {plan.priority}
                            </span>
                            <div className="min-w-0">
                              <p className="font-semibold text-gray-900 truncate">{plan.topic}</p>
                              <p className="flex items-center gap-1 text-xs text-gray-500 mt-0.5">
                                <Clock className="w-3 h-3" />
                                {plan.suggested_time}
                              </p>
                            </div>
                          </div>
                          <ChevronDown
                            className={`shrink-0 w-5 h-5 text-gray-400 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''
                              }`}
                          />
                        </button>

                        {/* Body */}
                        {isOpen && (
                          <div className="px-4 pb-4 pt-1 border-t border-gray-100 space-y-4">
                            <div className="grid md:grid-cols-3 gap-4 text-sm pt-3">
                              <div>
                                <p className="flex items-center gap-1.5 font-medium text-gray-900 mb-1.5">
                                  <BookOpen className="w-4 h-4 text-indigo-500" />
                                  Key Concepts
                                </p>
                                <ul className="space-y-1 text-gray-700">
                                  {plan.key_concepts.map((item) => (
                                    <li key={item} className="flex gap-1.5">
                                      <span className="text-indigo-400">•</span>
                                      <span>{item}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              <div>
                                <p className="flex items-center gap-1.5 font-medium text-gray-900 mb-1.5">
                                  <Dumbbell className="w-4 h-4 text-indigo-500" />
                                  Practice Focus
                                </p>
                                <ul className="space-y-1 text-gray-700">
                                  {plan.practice_focus.map((item) => (
                                    <li key={item} className="flex gap-1.5">
                                      <span className="text-indigo-400">•</span>
                                      <span>{item}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>

                              <div>
                                <p className="flex items-center gap-1.5 font-medium text-gray-900 mb-1.5">
                                  <Link2 className="w-4 h-4 text-indigo-500" />
                                  Resources
                                </p>
                                <ul className="space-y-1 text-gray-700">
                                  {plan.resources.map((item) => (
                                    <li key={item} className="flex gap-1.5">
                                      <span className="text-indigo-400">•</span>
                                      <span>{item}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            </div>

                            {plan.mistakes_to_review.length > 0 && (
                              <div className="border-t border-gray-100 pt-3">
                                <p className="flex items-center gap-1.5 font-medium text-gray-900 mb-2">
                                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                                  Questions to Review
                                </p>
                                <div className="space-y-2.5">
                                  {plan.mistakes_to_review.map((mistake, index) => (
                                    <div
                                      key={`${plan.topic}-${index}`}
                                      className="rounded-lg border border-gray-100 bg-gray-50/70 p-3 text-sm"
                                    >
                                      <p className="font-medium text-gray-900">
                                        {renderQuestionText(mistake.question_text)}
                                      </p>
                                      <p className="text-rose-700 mt-1.5 flex gap-1.5">
                                        <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
                                        <span>Your answer: {mistake.selected_answer_text}</span>
                                      </p>
                                      <p className="text-emerald-700 flex gap-1.5">
                                        <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                                        <span>Correct answer: {mistake.correct_answer_text}</span>
                                      </p>
                                      {mistake.explanation && (
                                        <p className="text-gray-600 mt-1.5">{mistake.explanation}</p>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {/* ── Question review ──────────────────────────────────────────── */}
          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <ListChecks className="w-5 h-5 text-gray-500" />
                Question Review
              </h3>
              {incorrectCount > 0 && (
                <button
                  type="button"
                  onClick={() => setShowIncorrectOnly((v) => !v)}
                  className="text-xs font-medium rounded-full border border-gray-200 px-3 py-1 text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  {showIncorrectOnly
                    ? 'Show all questions'
                    : `Show incorrect only (${incorrectCount})`}
                </button>
              )}
            </div>

            {visibleQuestions.map(({ q: question, number }) => (
              <div
                key={question.question_id}
                className={`rounded-lg border p-4 ${question.is_correct
                  ? 'bg-emerald-50/60 border-emerald-200'
                  : 'bg-rose-50/60 border-rose-200'
                  }`}
              >
                <div className="flex justify-between items-start gap-4 mb-2">
                  <h4 className="font-semibold text-gray-900">
                    <h4 className="font-semibold text-gray-900">
                      Q{number}. {renderQuestionText(question.question_text, question.is_correct ? 'correct' : 'incorrect')}
                    </h4>
                  </h4>
                  <span
                    className={`shrink-0 inline-flex items-center gap-1 text-sm font-medium ${question.is_correct ? 'text-emerald-700' : 'text-rose-700'
                      }`}
                  >
                    {question.is_correct ? (
                      <CheckCircle2 className="w-4 h-4" />
                    ) : (
                      <XCircle className="w-4 h-4" />
                    )}
                    {question.is_correct ? 'Correct' : 'Incorrect'}
                  </span>
                </div>

                <div className="space-y-1.5 text-sm">
                  <p>
                    <span className="font-medium text-gray-700">Your Answer: </span>
                    <span className={question.is_correct ? 'text-emerald-700' : 'text-rose-700'}>
                      {question.selected_answer_text ?? 'Not answered'}
                    </span>
                  </p>

                  {!question.is_correct && (
                    <p>
                      <span className="font-medium text-gray-700">Correct Answer: </span>
                      <span className="text-emerald-700">
                        {question.correct_answer_text ?? 'N/A'}
                      </span>
                    </p>
                  )}

                  {question.explanation && (
                    <p className="text-gray-600">
                      <span className="font-medium text-gray-700">Explanation: </span>
                      {renderQuestionText(question.explanation, question.is_correct ? 'correct' : 'incorrect')}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </section>

          {/* Interview status banner */}
          {passed &&
            (interviewPassed ? (
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-start gap-3">
                <CheckCircle2 className="w-6 h-6 text-emerald-600 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-emerald-900">Interview Already Passed</p>
                  <p className="text-sm text-emerald-700">
                    You have already passed the AI interview. View your interview report for a full
                    breakdown.
                  </p>
                </div>
              </div>
            ) : interviewCooldownActive ? (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-start gap-3">
                <XCircle className="w-6 h-6 text-orange-600 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-orange-900">Interview on Cooldown</p>
                  <p className="text-sm text-orange-700">
                    You passed the quiz, but your interview is currently on cooldown.
                  </p>
                  <p className="text-sm text-orange-700 mt-2 font-medium">
                    {getInterviewCooldownTime()}
                  </p>
                </div>
              </div>
            ) : (
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-start gap-3">
                <CheckCircle2 className="w-6 h-6 text-emerald-600 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-emerald-900">Interview Unlocked</p>
                  <p className="text-sm text-emerald-700">
                    You passed the quiz and can now continue to the AI interview.
                  </p>
                </div>
              </div>
            ))}
        </div>

        {/* ── Pinned footer: actions ───────────────────────────────────────── */}
        <div className="shrink-0 border-t border-gray-100 px-6 py-4 bg-white">
          <div className="grid grid-cols-2 gap-4">
            <Button variant="outline" onClick={() => navigate('/dashboard')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Dashboard
            </Button>

            {passed ? (
              canStartInterview ? (
                <Button
                  className="w-full bg-green-500 hover:bg-green-600 text-white"
                  size="lg"
                  onClick={() => navigate('/interview')}
                >
                  Proceed to Interview
                </Button>
              ) : (
                <Button onClick={() => navigate('/interview-report')}>
                  {interviewPassed ? 'View Interview Report' : 'View Progress'}
                </Button>
              )
            ) : canRetryQuiz() ? (
              <Button onClick={() => navigate('/quiz')}>Retry Quiz</Button>
            ) : (
              <Button onClick={() => navigate('/progress-report', { state: { tab: 'resources' } })}>
                View Resources
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
