import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  Award, Brain, MessageSquare, Eye, Target,
  CheckCircle2, XCircle, AlertTriangle, ArrowLeft, Sparkles, ListChecks, TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import { useAuth } from '../context/AuthContext';
import { API_BASE_URL } from '../config';
import { toast } from 'sonner';

interface WeakDetail {
  area: string;
  score: number;
  status: 'critical' | 'weak' | 'borderline' | 'acceptable' | 'strong';
}

interface InterviewProgressReport {
  overall_summary?: string;
  strong_points?: string[];
  weak_points?: string[];
  weak_details?: WeakDetail[];
  score_details?: WeakDetail[];
  recommendations?: string[];
  cooldown_days?: number;
}

interface InterviewReportData {
  session_id: number;
  job_role: string;
  attempt_number: number;
  score: number;
  passed: boolean;
  technical_score: number;
  personality_score: number;
  attentiveness_score: number;
  eye_contact_score: number;
  communication_score?: number;
  confidence_score?: number;
  filler_ratio?: number;
  cooldown_until: string | null;
  submitted_at: string;
  improvement_plan?: string;
  progress_report?: InterviewProgressReport;
  analysis_data?: {
    hard_fail_triggered?: boolean;
    fail_reason?: string;
  };
  questions: {
    question_id: number;
    question_text: string;
    question_type: string;
    category: string;
    transcript: string;
    score?: number | null;
    reference_points?: string;
    reference_match_pct?: number;
    reference_keyword_hits?: number;
    reference_keyword_total?: number;
    hit_keywords?: string[];
    missed_keywords?: string[];
  }[];
}

const scoreColor = (s: number) =>
  s >= 85 ? 'text-green-600' : s >= 70 ? 'text-blue-600' : s >= 50 ? 'text-orange-600' : 'text-red-600';

const scoreBg = (s: number) =>
  s >= 85 ? 'bg-green-50 border-green-200' : s >= 70 ? 'bg-blue-50 border-blue-200' : s >= 50 ? 'bg-orange-50 border-orange-200' : 'bg-red-50 border-red-200';

const statusBadge = (status: string) => {
  switch (status) {
    case 'critical':
      return 'bg-rose-100 text-rose-700 border-rose-200';
    case 'weak':
      return 'bg-amber-100 text-amber-700 border-amber-200';
    case 'borderline':
      return 'bg-orange-100 text-orange-700 border-orange-200';
    case 'acceptable':
      return 'bg-blue-100 text-blue-700 border-blue-200';
    case 'strong':
      return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    default:
      return 'bg-gray-100 text-gray-700 border-gray-200';
  }
};

const scoreStatus = (score: number): WeakDetail['status'] => {
  if (score < 45) return 'critical';
  if (score < 60) return 'weak';
  if (score < 70) return 'borderline';
  if (score >= 80) return 'strong';
  return 'acceptable';
};

export default function InterviewReport() {
  const navigate = useNavigate();
  const { authFetch } = useAuth();

  const [report, setReport] = useState<InterviewReportData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const cooldownActive =
    !!report?.cooldown_until && new Date(report.cooldown_until) > new Date();

  const canRetry = !!report && !report.passed && !cooldownActive;

  const getRetryTime = () => {
    if (!report?.cooldown_until) return null;
    const end = new Date(report.cooldown_until);
    const now = new Date();
    if (end <= now) return 'You can retry the interview now.';
    const diffMs = end.getTime() - now.getTime();
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs / (1000 * 60)) % 60);
    if (hours > 0) return `You can retry the interview in ${hours} hour(s) and ${minutes} minute(s).`;
    return `You can retry the interview in ${minutes} minute(s).`;
  };

  useEffect(() => {
    const load = async () => {
      try {
        const res = await authFetch(`${API_BASE_URL}/api/interviews/latest/`);
        if (!res.ok) throw new Error('No interview report found.');
        setReport(await res.json());
      } catch {
        toast.error('Could not load interview report.');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [authFetch]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500 text-lg">Loading interview report...</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-xl w-full">
          <CardHeader>
            <CardTitle>No Interview Report Found</CardTitle>
            <CardDescription>You have not completed an interview yet.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => navigate('/dashboard')}>Back to Dashboard</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const pr = report.progress_report;
  const weakDetails = (pr?.weak_details ?? []).filter((item) => item.area !== 'Grammar');
  const recommendations = (pr?.recommendations ?? []).filter((item) => !item.toLowerCase().includes('grammar score'));
  const strongPoints = (pr?.strong_points ?? []).filter((point) => point !== 'Grammar');
  const weakPoints = (pr?.weak_points ?? []).filter((point) => point !== 'Grammar');

  const subScores = [
    { label: 'Technical', value: report.technical_score, icon: Brain },
    { label: 'Behavioural', value: report.personality_score, icon: MessageSquare },
    { label: 'Attentiveness', value: report.attentiveness_score, icon: Eye },
    { label: 'Eye Contact', value: report.eye_contact_score, icon: Target },
    ...(report.communication_score != null ? [{ label: 'Communication', value: report.communication_score, icon: MessageSquare }] : []),
    ...(report.confidence_score != null ? [{ label: 'Confidence', value: report.confidence_score, icon: Target }] : []),
  ];

  const lowScoreQuestions = report.questions.filter(
    (q) => q.score != null && q.score < 70
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex justify-center items-start p-4 sm:p-6">
      <Card className="max-w-4xl w-full border-0 shadow-2xl flex flex-col max-h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-3rem)] overflow-hidden">
        <CardHeader className="text-center shrink-0 pb-5 border-b border-gray-100">
          <div className="w-16 h-16 mx-auto mb-3 rounded-full flex items-center justify-center bg-gradient-to-br from-blue-600 to-purple-600">
            <Award className="w-8 h-8 text-white" />
          </div>
          <CardTitle className="text-2xl mb-1">Interview Report</CardTitle>
          <CardDescription>
            Attempt #{report.attempt_number} · {report.job_role}
          </CardDescription>
          <div className="mt-4 flex items-center justify-center gap-4">
            <div className="text-5xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
              {Math.round(report.score)}%
            </div>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold border ${report.passed
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-rose-50 text-rose-700 border-rose-200'
                }`}
            >
              {report.passed ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
              {report.passed ? 'Passed' : 'Failed'}
            </span>
          </div>
        </CardHeader>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-6 space-y-6 [scrollbar-gutter:stable]">
          {!report.passed && (
            <div className="bg-rose-50 border border-rose-200 rounded-lg p-4 flex items-start gap-3">
              <XCircle className="w-6 h-6 text-rose-600 flex-shrink-0" />
              <div>
                <p className="font-semibold text-rose-900">Interview Not Passed</p>
                <p className="text-sm text-rose-700">You need 70% or above to publish your profile.</p>
                {report.analysis_data?.hard_fail_triggered && report.analysis_data.fail_reason && (
                  <p className="text-sm text-rose-700 mt-2">{report.analysis_data.fail_reason}</p>
                )}
                {report.cooldown_until && (
                  <p className="text-sm text-rose-700 mt-2 font-medium">{getRetryTime()}</p>
                )}
              </div>
            </div>
          )}

          {report.passed && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-start gap-3">
              <CheckCircle2 className="w-6 h-6 text-emerald-600 flex-shrink-0" />
              <div>
                <p className="font-semibold text-emerald-900">Profile Eligible for Publication</p>
                <p className="text-sm text-emerald-700">You passed the interview and can now publish your profile.</p>
              </div>
            </div>
          )}

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {subScores.map(({ label, value, icon: Icon }) => (
              <div key={label} className={`p-4 rounded-lg border ${scoreBg(value)} text-center`}>
                <Icon className={`w-5 h-5 mx-auto mb-2 ${scoreColor(value)}`} />
                <div className={`text-xl font-bold mb-1 ${scoreColor(value)}`}>{Math.round(value)}%</div>
                <div className="text-xs text-gray-600">{label}</div>
                <Badge variant="outline" className={`mt-2 capitalize ${statusBadge(scoreStatus(value))}`}>
                  {scoreStatus(value)}
                </Badge>
                <Progress value={value} className="mt-2 h-1.5" />
              </div>
            ))}
          </div>

          {/* ── AI Improvement Plan ─────────────────────────────────────── */}
          <section className="space-y-4">
            <div className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-blue-50 p-5">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-5 h-5 text-indigo-600" />
                <h3 className="text-lg font-semibold text-indigo-950">Personalized Improvement Plan</h3>
              </div>
              {pr?.overall_summary && (
                <p className="text-sm text-indigo-900/90 leading-relaxed mb-3">{pr.overall_summary}</p>
              )}
              {report.improvement_plan && (
                <p className="text-sm text-indigo-900 leading-relaxed">{report.improvement_plan}</p>
              )}
              {!report.improvement_plan && !pr?.overall_summary && (
                <p className="text-sm text-indigo-800">
                  Complete another attempt to receive a detailed AI improvement plan.
                </p>
              )}
            </div>

            {strongPoints.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold uppercase tracking-wide text-gray-500 mb-2 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" /> Strengths
                </h4>
                <div className="flex flex-wrap gap-2">
                  {strongPoints.map((point) => (
                    <Badge key={point} className="bg-emerald-100 text-emerald-800 border-emerald-200">
                      {point}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {weakDetails.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                  Priority Focus Areas
                </h4>
                <div className="grid sm:grid-cols-2 gap-3">
                  {weakDetails.map((item) => (
                    <div key={item.area} className="rounded-lg border border-gray-200 bg-white p-4">
                      <div className="flex justify-between items-center gap-2 mb-2">
                        <p className="font-semibold text-gray-900 text-sm">{item.area}</p>
                        <Badge variant="outline" className={statusBadge(item.status)}>
                          {item.status}
                        </Badge>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>Score</span>
                        <span className="font-semibold text-gray-800">
                          {item.area === 'Answer timing' ? `${item.score}s` : `${Math.round(item.score)}%`}
                        </span>
                      </div>
                      <Progress
                        value={item.area === 'Answer timing' ? Math.min(100, item.score) : item.score}
                        className="h-1.5"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {weakPoints.length > 0 && weakDetails.length === 0 && (
              <div className="flex flex-wrap gap-2">
                {weakPoints.map((point) => (
                  <Badge key={point} variant="outline" className="bg-amber-50 text-amber-800 border-amber-200">
                    {point}
                  </Badge>
                ))}
              </div>
            )}

            {recommendations.length > 0 && (
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <h4 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-indigo-600" />
                  Actionable Recommendations
                </h4>
                <ul className="space-y-3">
                  {recommendations.map((item, index) => (
                    <li key={index} className="flex gap-3 text-sm text-gray-800">
                      <span className="shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold flex items-center justify-center">
                        {index + 1}
                      </span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {lowScoreQuestions.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-4">
                <h4 className="font-semibold text-amber-900 mb-2">Answers to rework before your next attempt</h4>
                <ul className="space-y-2 text-sm text-amber-900">
                  {lowScoreQuestions.map((q) => (
                    <li key={q.question_id} className="flex justify-between gap-2">
                      <span className="line-clamp-2">{q.question_text}</span>
                      <span className="shrink-0 font-semibold">{Math.round(q.score!)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Transcript review */}
          <section className="space-y-3">
            <h3 className="text-lg font-semibold text-gray-900">Transcript Review</h3>
            {report.questions.map((q, i) => (
              <div
                key={q.question_id}
                className={`rounded-lg border p-4 ${q.question_type === 'technical' ? 'bg-blue-50/60 border-blue-200' : 'bg-purple-50/60 border-purple-200'}`}
              >
                <div className="mb-2">
                  <Badge className={`text-xs ${q.question_type === 'technical' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'}`}>
                    {q.category}
                  </Badge>
                </div>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <h4 className="font-medium text-gray-900 text-sm">Q{i + 1}. {q.question_text}</h4>
                  {q.score != null && (
                    <span className={`text-xs font-semibold shrink-0 ${q.score >= 70 ? 'text-emerald-700' : 'text-rose-700'}`}>
                      {Math.round(q.score)}%
                    </span>
                  )}
                </div>
                <div className={`rounded p-3 text-sm ${q.question_type === 'technical' ? 'bg-blue-100/80' : 'bg-purple-100/80'}`}>
                  <p className="font-medium text-gray-700 mb-1 text-xs uppercase tracking-wide">Your Answer</p>
                  <p className="text-gray-800 italic">
                    {q.transcript?.trim() || <span className="text-gray-400">No response recorded.</span>}
                  </p>
                  {q.reference_match_pct != null && (
                    <p className="text-xs text-gray-600 mt-2">
                      Concept match: {Math.round(q.reference_match_pct)}%
                      {q.reference_keyword_total != null && (
                        <> ({q.reference_keyword_hits ?? 0}/{q.reference_keyword_total} key terms)</>
                      )}
                    </p>
                  )}
                  {(q.missed_keywords?.length ?? 0) > 0 && (
                    <p className="text-xs text-amber-800 mt-1">
                      Missing concepts: {q.missed_keywords!.slice(0, 6).join(', ')}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </section>
        </div>

        <div className="shrink-0 border-t border-gray-100 px-6 py-4 bg-white">
          <div className="grid grid-cols-2 gap-4">
            <Button variant="outline" onClick={() => navigate('/dashboard')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Dashboard
            </Button>
            {report.passed ? (
              <Button
                className="w-full bg-green-500 hover:bg-green-600 text-white"
                size="lg"
                onClick={() => navigate('/profile-publication')}
              >
                Publish Profile
              </Button>
            ) : canRetry ? (
              <Button onClick={() => navigate('/interview')}>Retake Interview</Button>
            ) : (
              <Button onClick={() => navigate('/progress-report')}>View Progress</Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
