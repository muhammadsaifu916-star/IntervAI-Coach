import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { motion } from 'motion/react';
import {
  TrendingUp, TrendingDown, FileText, Award, Brain, Target,
  CheckCircle2, AlertCircle, Share2, ArrowLeft, BookOpen,
  Youtube, Clock, Loader2, Eye, MessageSquare, ExternalLink, Dumbbell,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { API_BASE_URL } from '../config';

// ── Types ─────────────────────────────────────────────────────────────────────
interface QuizReport {
  session_id: number;
  attempt_number: number;
  score: number;
  passed: boolean;
  correct: number;
  total: number;
  cooldown_until: string | null;
  interview_unlocked: boolean;
  submitted_at: string;
  questions: {
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
  }[];
}

interface InterviewReport {
  session_id: number;
  job_role: string;
  attempt_number: number;
  score: number;
  passed: boolean;
  technical_score: number;
  personality_score: number;
  attentiveness_score: number;
  eye_contact_score: number;
  cooldown_until: string | null;
  submitted_at: string;
  questions: {
    question_id: number;
    question_text: string;
    question_type: string;
    category: string;
    transcript: string;
  }[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const scoreLabel = (s: number) =>
  s >= 85 ? 'Excellent' : s >= 70 ? 'Good' : s >= 50 ? 'Needs Work' : 'Poor';

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

// ── Plan-driven resource engine ───────────────────────────────────────────────
// Recommendations are derived from the user's weak areas (their improvement plan)
// rather than a fixed list. Each video opens a curated YouTube search so links
// never go stale, and technical topics are tailored to the user's target role.

type VideoReco = { title: string; creators: string; focus: string; query: string };
type StudyReco = { label: string; detail: string; url: string };

const ytSearch = (q: string) =>
  `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`;

const roleOrDefault = (role?: string) =>
  role && role.trim() ? role.trim() : 'software engineer';

// Maps a weak area from the improvement plan → recommended videos.
// `skills` (from the resume) sharpen technical picks; `role` tailors the rest.
function videosForArea(area: string, role?: string, skills: string[] = []): VideoReco[] {
  const r = roleOrDefault(role);
  switch (area) {
    case 'Resume Quality':
      return [
        { title: 'Write a Resume That Beats the ATS', creators: 'Jeff Su', focus: 'Resume', query: 'how to write a resume that beats the ATS' },
        { title: `${r} Resume — Examples & Breakdown`, creators: 'Self Made Millennial', focus: 'Resume', query: `${r} resume examples and tips` },
      ];
    case 'Technical Depth': {
      const skill = skills[0];
      const out: VideoReco[] = [
        { title: `${r} — System Design & Architecture`, creators: 'ByteByteGo · Gaurav Sen', focus: 'Technical Depth', query: `${r} system design interview` },
        { title: `${r} — Hard Interview Questions, Explained`, creators: 'NeetCode · Tech Dummies', focus: 'Technical Depth', query: `${r} hard interview questions explained` },
      ];
      if (skill) out.unshift({ title: `${skill} — Deep Dive & Interview Questions`, creators: 'Top community tutorials', focus: 'Technical Depth', query: `${skill} advanced interview questions tutorial` });
      return out;
    }
    case 'Technical Quiz Knowledge': {
      const skill = skills[1] ?? skills[0];
      const out: VideoReco[] = [
        { title: `${r} — Core Concepts Crash Course`, creators: 'freeCodeCamp', focus: 'Quiz Knowledge', query: `${r} full course for beginners` },
        { title: 'Data Structures & Algorithms Refresher', creators: 'CS Dojo · Abdul Bari', focus: 'Quiz Knowledge', query: `data structures and algorithms full course` },
      ];
      if (skill) out.unshift({ title: `${skill} — Fundamentals Refresher`, creators: 'Top community tutorials', focus: 'Quiz Knowledge', query: `${skill} fundamentals tutorial` });
      return out;
    }
    case 'Behavioural Responses':
      return [
        { title: 'Master the STAR Method', creators: 'Jeff H Sipe · Self Made Millennial', focus: 'Behavioural', query: `STAR method behavioral interview answers` },
        { title: '“Tell Me About Yourself” — Best Answers', creators: 'Self Made Millennial', focus: 'Behavioural', query: `tell me about yourself best interview answer examples` },
      ];
    case 'Attentiveness':
      return [
        { title: 'Active Listening in Interviews', creators: 'Communication Coach Alexander Lyon', focus: 'Attentiveness', query: `active listening skills job interview` },
        { title: 'Stay Focused & Engaged Under Pressure', creators: 'Jeff H Sipe', focus: 'Attentiveness', query: `how to stay focused and engaged during an interview` },
      ];
    case 'Eye Contact':
      return [
        { title: 'Eye Contact & Confident Body Language', creators: 'Vanessa Van Edwards', focus: 'Eye Contact', query: `eye contact body language interview tips` },
        { title: 'Look Natural on Camera (Virtual Interviews)', creators: 'Wizard of Words', focus: 'Eye Contact', query: `virtual interview eye contact camera tips` },
      ];
    default:
      return [];
  }
}

// Shown when there are no weak areas left — keep skills sharp / next steps.
function keepSharpVideos(role?: string): VideoReco[] {
  const r = roleOrDefault(role);
  return [
    { title: `Advanced ${r} Interview Prep`, creators: 'Exponent · NeetCode', focus: 'Stay sharp', query: `advanced ${r} interview preparation` },
    { title: 'Negotiating Your Job Offer', creators: 'Self Made Millennial', focus: 'Next step', query: `how to negotiate salary after job offer` },
  ];
}

// Maps a weak area → one concrete place to practise it.
function studyForArea(area: string): StudyReco | null {
  switch (area) {
    case 'Resume Quality':
      return { label: 'Resume Worded', detail: 'Free ATS resume scoring & line-by-line fixes', url: 'https://resumeworded.com/' };
    case 'Technical Depth':
    case 'Technical Quiz Knowledge':
      return { label: 'LeetCode', detail: 'Targeted DSA & problem practice', url: 'https://leetcode.com/problemset/' };
    case 'Behavioural Responses':
      return { label: 'Pramp', detail: 'Free peer mock behavioural interviews', url: 'https://www.pramp.com/' };
    case 'Attentiveness':
    case 'Eye Contact':
      return { label: 'Pramp (video)', detail: 'Record yourself & review your presence', url: 'https://www.pramp.com/' };
    default:
      return null;
  }
}

const focusColor = (focus: string) => {
  if (focus.includes('Resume')) return 'bg-amber-100 text-amber-700';
  if (focus.includes('Technical') || focus.includes('Quiz')) return 'bg-purple-100 text-purple-700';
  if (focus.includes('Behavioural')) return 'bg-blue-100 text-blue-700';
  if (focus.includes('Eye') || focus.includes('Attentiveness')) return 'bg-pink-100 text-pink-700';
  return 'bg-green-100 text-green-700';
};

// ── Component ─────────────────────────────────────────────────────────────────
export default function ProgressReport() {
  const navigate = useNavigate();
  const location = useLocation();
  const { profile, authFetch } = useAuth();

  const [tab, setTab] = useState<string>(
    (location.state as { tab?: string } | null)?.tab ?? 'analysis'
  );
  const [quiz, setQuiz] = useState<QuizReport | null>(null);
  const [interview, setInterview] = useState<InterviewReport | null>(null);
  const [loading, setLoading] = useState(true);

  const resumeScore = profile?.resume_score ?? 0;
  const quizScore = quiz?.score ?? 0;
  const interviewScore = interview?.score ?? 0;

  const completedScores = [resumeScore, quizScore, interviewScore].filter(s => s > 0);
  const overallScore = completedScores.length
    ? Math.round(completedScores.reduce((a, b) => a + b, 0) / completedScores.length)
    : 0;

  // ── Fetch both reports in parallel ──────────────────────────────────────────
  useEffect(() => {
    async function load() {
      const [qRes, iRes] = await Promise.allSettled([
        authFetch(`${API_BASE_URL}/api/quizzes/latest/`),
        authFetch(`${API_BASE_URL}/api/interviews/latest/`),
      ]);

      if (qRes.status === 'fulfilled' && qRes.value.ok) {
        setQuiz(await qRes.value.json());
      }
      if (iRes.status === 'fulfilled' && iRes.value.ok) {
        setInterview(await iRes.value.json());
      }
      setLoading(false);
    }
    load().catch(() => { toast.error('Failed to load report data.'); setLoading(false); });
  }, [authFetch]);

  // ── Derive improvement areas from real scores ─────────────────────────────
  const weakAreas: { area: string; current: number; target: number; icon: any }[] = [];
  // Resume is the first gate (quiz needs resume >= 70), so surface it first.
  if (resumeScore > 0 && resumeScore < 70) weakAreas.push({ area: 'Resume Quality', current: Math.round(resumeScore), target: 70, icon: FileText });
  if (interview) {
    if (interview.technical_score < 70) weakAreas.push({ area: 'Technical Depth', current: Math.round(interview.technical_score), target: 70, icon: Brain });
    if (interview.personality_score < 70) weakAreas.push({ area: 'Behavioural Responses', current: Math.round(interview.personality_score), target: 70, icon: Target });
    if (interview.attentiveness_score < 70) weakAreas.push({ area: 'Attentiveness', current: Math.round(interview.attentiveness_score), target: 70, icon: Eye });
    if (interview.eye_contact_score < 70) weakAreas.push({ area: 'Eye Contact', current: Math.round(interview.eye_contact_score), target: 70, icon: AlertCircle });
  }
  if (quiz && quizScore < 70) weakAreas.push({ area: 'Technical Quiz Knowledge', current: Math.round(quizScore), target: 70, icon: Brain });

  const strongAreas: { skill: string; score: number; icon: any }[] = [];
  if (resumeScore >= 70) strongAreas.push({ skill: 'Resume Quality', score: Math.round(resumeScore), icon: FileText });
  if (quizScore >= 70) strongAreas.push({ skill: 'Technical Knowledge', score: Math.round(quizScore), icon: Brain });
  if ((interview?.technical_score ?? 0) >= 70) strongAreas.push({ skill: 'Interview – Technical', score: Math.round(interview!.technical_score), icon: Target });
  if ((interview?.personality_score ?? 0) >= 70) strongAreas.push({ skill: 'Interview – Behavioural', score: Math.round(interview!.personality_score), icon: MessageSquare });
  if ((interview?.attentiveness_score ?? 0) >= 80) strongAreas.push({ skill: 'Attentiveness', score: Math.round(interview!.attentiveness_score), icon: Eye });

  // Next-attempt eligibility
  const quizCooldownActive = quiz?.cooldown_until ? new Date(quiz.cooldown_until) > new Date() : false;
  const interviewCooldownActive = interview?.cooldown_until ? new Date(interview.cooldown_until) > new Date() : false;

  const nextAttemptLabel = () => {
    if (resumeScore === 0) return 'Upload your resume first';
    if (resumeScore < 70) return 'Improve your resume to unlock the quiz';
    if (!quiz) return 'Take the quiz first';
    if (!quiz.passed) return quizCooldownActive ? `Quiz cooldown: ${fmtDate(quiz.cooldown_until!)}` : 'Quiz available now';
    if (!interview) return 'Take the interview first';
    if (!interview.passed) return interviewCooldownActive ? `Interview cooldown: ${fmtDate(interview.cooldown_until!)}` : 'Interview available now';
    return 'All assessments passed!';
  };

  // Timeline events
  const timeline = [
    { title: 'Resume Uploaded', date: 'Completed', score: resumeScore || null, done: resumeScore > 0 },
    { title: 'Quiz Completed', date: quiz ? fmtDate(quiz.submitted_at) : 'Pending', score: quiz?.score ?? null, done: !!quiz },
    { title: 'Interview Done', date: interview ? fmtDate(interview.submitted_at) : 'Pending', score: interview?.score ?? null, done: !!interview },
    { title: 'Profile Published', date: 'Pending', score: null, done: false },
  ];

  // ── Recommendations derived from the improvement plan ───────────────────────
  // Role + skills come from the resume, so they're available before the interview.
  const targetRole = profile?.job_role ?? interview?.job_role;
  const topSkills = (profile?.skills ?? []).filter(Boolean).slice(0, 2);
  const hasStarted = !!quiz || !!interview || resumeScore > 0;

  // Build the video list from weak areas (deduped). Fall back to "keep sharp"
  // content when everything is already above target.
  const recommendedVideos: VideoReco[] = (() => {
    const seen = new Set<string>();
    const list = weakAreas
      .flatMap(w => videosForArea(w.area, targetRole, topSkills))
      .filter(v => (seen.has(v.title) ? false : (seen.add(v.title), true)));
    if (list.length === 0 && hasStarted) return keepSharpVideos(targetRole);
    return list;
  })();

  const studyPlan: StudyReco[] = (() => {
    const seen = new Set<string>();
    return weakAreas
      .map(w => studyForArea(w.area))
      .filter((s): s is StudyReco => !!s)
      .filter(s => (seen.has(s.label) ? false : (seen.add(s.label), true)));
  })();

  // ── Share ───────────────────────────────────────────────────────────────────
  const handleShare = async () => {
    const shareData = {
      title: 'My Progress Report',
      text: `My overall interview-readiness score is ${overallScore}%.`,
      url: window.location.href,
    };
    try {
      if (typeof navigator !== 'undefined' && navigator.share) {
        await navigator.share(shareData);
      } else {
        await navigator.clipboard.writeText(window.location.href);
        toast.success('Report link copied to clipboard');
      }
    } catch {
      /* user dismissed the share sheet — nothing to do */
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="w-12 h-12 text-blue-600 animate-spin mx-auto" />
          <p className="text-gray-600 font-medium">Loading your progress report…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
                <ArrowLeft className="w-4 h-4 mr-2" />Back to Dashboard
              </Button>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                  <TrendingUp className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-gray-900">Progress Report</h1>
                  <p className="text-sm text-gray-600">Your comprehensive assessment</p>
                </div>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={handleShare}>
              <Share2 className="w-4 h-4 mr-2" />Share
            </Button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* ── Overall Score Card ───────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }}>
          <Card className="border-0 shadow-2xl mb-8 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 text-white p-8">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                  <h2 className="text-3xl font-bold mb-2">Overall Performance</h2>
                  <p className="text-blue-100">Aggregate score across all completed assessments</p>
                </div>
                <div className="text-center">
                  <div className="text-7xl font-bold mb-2">{overallScore}%</div>
                  <Badge className="bg-white text-purple-600 hover:bg-white text-lg px-4 py-1">
                    {scoreLabel(overallScore)}
                  </Badge>
                </div>
              </div>
            </div>
            <CardContent className="p-6">
              <div className="grid md:grid-cols-3 gap-6">
                {/* Resume */}
                <div className="text-center p-4 bg-blue-50 rounded-lg">
                  <FileText className="w-8 h-8 text-blue-600 mx-auto mb-2" />
                  <div className="text-3xl font-bold text-blue-600 mb-1">{resumeScore > 0 ? `${resumeScore}%` : '—'}</div>
                  <div className="text-sm text-gray-600">Resume Analysis</div>
                  {resumeScore > 0 && <Progress value={resumeScore} className="mt-2 h-2" />}
                </div>
                {/* Quiz */}
                <div className="text-center p-4 bg-purple-50 rounded-lg">
                  <Brain className="w-8 h-8 text-purple-600 mx-auto mb-2" />
                  <div className="text-3xl font-bold text-purple-600 mb-1">{quiz ? `${quiz.score}%` : '—'}</div>
                  <div className="text-sm text-gray-600">Technical Quiz</div>
                  {quiz && <Progress value={quiz.score} className="mt-2 h-2" />}
                  {quiz && (
                    <Badge className={`mt-2 text-xs ${quiz.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {quiz.passed ? 'Passed' : 'Failed'}
                    </Badge>
                  )}
                </div>
                {/* Interview */}
                <div className="text-center p-4 bg-pink-50 rounded-lg">
                  <Award className="w-8 h-8 text-pink-600 mx-auto mb-2" />
                  <div className="text-3xl font-bold text-pink-600 mb-1">{interview ? `${interview.score}%` : '—'}</div>
                  <div className="text-sm text-gray-600">AI Interview</div>
                  {interview && <Progress value={interview.score} className="mt-2 h-2" />}
                  {interview && (
                    <Badge className={`mt-2 text-xs ${interview.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {interview.passed ? 'Passed' : 'Failed'}
                    </Badge>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <Tabs value={tab} onValueChange={setTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
            <TabsTrigger value="analysis">Analysis</TabsTrigger>
            <TabsTrigger value="review">Results</TabsTrigger>
            <TabsTrigger value="resources">Resources</TabsTrigger>
            <TabsTrigger value="timeline">Timeline</TabsTrigger>
          </TabsList>

          {/* ── Analysis Tab ──────────────────────────────────────────────── */}
          <TabsContent value="analysis" className="space-y-6">
            <div className="grid lg:grid-cols-2 gap-6">
              {/* Strong areas */}
              <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }}>
                <Card className="border-0 shadow-lg h-full">
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-green-600" />
                      <CardTitle>Strong Areas</CardTitle>
                    </div>
                    <CardDescription>Skills where you excel</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {strongAreas.length === 0 ? (
                      <p className="text-sm text-gray-500 italic">
                        {resumeScore === 0
                          ? 'Upload your resume to start tracking your strengths.'
                          : !quiz
                          ? 'Take the quiz to start surfacing your strengths.'
                          : !interview
                          ? 'Complete the interview to surface more strengths.'
                          : 'No areas above target yet — focus on your improvement plan.'}
                      </p>
                    ) : strongAreas.map(({ skill, score, icon: Icon }) => (
                      <div key={skill} className="space-y-1">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Icon className="w-4 h-4 text-green-600" />
                            <span className="font-medium text-sm">{skill}</span>
                          </div>
                          <span className="text-sm font-bold text-green-600">{score}%</span>
                        </div>
                        <Progress value={score} className="h-2" />
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </motion.div>

              {/* Weak areas */}
              <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }}>
                <Card className="border-0 shadow-lg h-full">
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <TrendingDown className="w-5 h-5 text-orange-600" />
                      <CardTitle>Areas for Improvement</CardTitle>
                    </div>
                    <CardDescription>Focus areas to boost your profile</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {weakAreas.length === 0 ? (
                      <p className="text-sm text-gray-500 italic">
                        {resumeScore === 0
                          ? 'Upload your resume to start building your improvement plan.'
                          : !quiz
                          ? 'Take the quiz to see personalised improvement areas.'
                          : !interview
                          ? 'Complete the interview to see personalised improvement areas.'
                          : 'All scores are above target — great work!'}
                      </p>
                    ) : weakAreas.map(({ area, current, target, icon: Icon }) => (
                      <div key={area} className="space-y-1">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Icon className="w-4 h-4 text-orange-600" />
                            <span className="font-medium text-sm">{area}</span>
                          </div>
                          <span className="text-xs text-gray-500">{current}% → {target}%</span>
                        </div>
                        <div className="relative">
                          <Progress value={current} className="h-2" />
                          <div className="absolute top-0 h-2 border-r-2 border-blue-500 opacity-60" style={{ left: `${target}%` }} />
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </motion.div>
            </div>

            {/* Improvement plan */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}>
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle>Personalised Improvement Plan</CardTitle>
                  <CardDescription>Based on your real scores</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {weakAreas.length === 0 && !quiz && !interview && (
                      <p className="text-sm text-gray-500 italic">Complete your assessments to generate a plan.</p>
                    )}
                    {quiz && !quiz.passed && (
                      <div className="p-4 bg-red-50 border-l-4 border-red-600 rounded-lg">
                        <div className="flex items-center justify-between mb-1">
                          <h5 className="font-semibold text-gray-900">Retake the Technical Quiz</h5>
                          <Badge variant="destructive">High</Badge>
                        </div>
                        <p className="text-sm text-gray-700">
                          You scored {Math.round(quiz.score)}% — need 70% to unlock the interview.
                          Review {quiz.questions.filter(q => !q.is_correct).length} incorrect answers below.
                        </p>
                      </div>
                    )}
                    {weakAreas.map(({ area, current, target }) => (
                      <div key={area} className="p-4 bg-yellow-50 border-l-4 border-yellow-500 rounded-lg">
                        <div className="flex items-center justify-between mb-1">
                          <h5 className="font-semibold text-gray-900">Improve: {area}</h5>
                          <Badge className="bg-yellow-100 text-yellow-800">Medium</Badge>
                        </div>
                        <p className="text-sm text-gray-700">Current: {current}% → Target: {target}%</p>
                      </div>
                    ))}
                    {(quiz?.passed && (!interview || interview.passed)) && (
                      <div className="p-4 bg-green-50 border-l-4 border-green-600 rounded-lg flex items-center gap-3">
                        <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                        <p className="text-sm text-green-800 font-medium">All assessments passed — you're ready to publish your profile!</p>
                      </div>
                    )}
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4 mt-6">
                    <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                      <p className="text-sm text-blue-600 mb-1">Next Step</p>
                      <p className="font-bold text-blue-900 text-sm">{nextAttemptLabel()}</p>
                    </div>
                    <div className="p-4 bg-purple-50 border border-purple-200 rounded-lg">
                      <p className="text-sm text-purple-600 mb-1">Assessments Completed</p>
                      <p className="font-bold text-purple-900 text-2xl">{completedScores.length} / 3</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>

          {/* ── Results Tab ───────────────────────────────────────────────── */}
          <TabsContent value="review" className="space-y-6">
            {/* Resume summary */}
            {resumeScore > 0 ? (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                <Card className="border-0 shadow-lg">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>Resume Result</CardTitle>
                        <CardDescription>Latest resume analysis</CardDescription>
                      </div>
                      <Badge className={resumeScore >= 70 ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}>
                        {resumeScore >= 70 ? 'Strong' : 'Needs Work'}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between gap-4 p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <FileText className="w-8 h-8 text-blue-600" />
                        <div>
                          <p className="font-semibold text-gray-900">{resumeScore}% overall</p>
                          <p className="text-sm text-gray-600">
                            {profile?.resume_feedback?.suggestions?.length ?? 0} suggestion(s) to review
                          </p>
                        </div>
                      </div>
                      <Button onClick={() => navigate('/resume-feedback')}>
                        View full resume report
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ) : (
              <Card className="border-0 shadow-lg">
                <CardContent className="py-12 text-center text-gray-500">
                  <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>No resume uploaded yet.</p>
                  <Button className="mt-4" onClick={() => navigate('/resume-upload')}>Upload Resume</Button>
                </CardContent>
              </Card>
            )}

            {/* Quiz summary */}
            {quiz ? (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                <Card className="border-0 shadow-lg">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>Quiz Result</CardTitle>
                        <CardDescription>Attempt #{quiz.attempt_number}</CardDescription>
                      </div>
                      <Badge className={quiz.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
                        {quiz.passed ? 'Passed' : 'Failed'}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between gap-4 p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <Brain className="w-8 h-8 text-purple-600" />
                        <div>
                          <p className="font-semibold text-gray-900">{Math.round(quiz.score)}% overall</p>
                          <p className="text-sm text-gray-600">
                            {quiz.questions.filter(q => !q.is_correct).length} answer(s) to review
                          </p>
                        </div>
                      </div>
                      <Button onClick={() => navigate('/quiz-report')}>
                        View full quiz report
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ) : (
              <Card className="border-0 shadow-lg">
                <CardContent className="py-12 text-center text-gray-500">
                  <Brain className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>No quiz completed yet.</p>
                  {resumeScore >= 70 ? (
                    <Button className="mt-4" onClick={() => navigate('/quiz')}>Take the Quiz</Button>
                  ) : (
                    <Button
                      className="mt-4"
                      onClick={() => navigate(resumeScore === 0 ? '/resume-upload' : '/resume-feedback')}
                    >
                      {resumeScore === 0 ? 'Upload Resume' : 'Improve Resume'} to unlock the quiz
                    </Button>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Interview summary */}
            {interview ? (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                <Card className="border-0 shadow-lg">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle>Interview Result</CardTitle>
                        <CardDescription>Attempt #{interview.attempt_number}</CardDescription>
                      </div>
                      <Badge className={interview.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}>
                        {interview.passed ? 'Passed' : 'Failed'}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center justify-between gap-4 p-4 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <Award className="w-8 h-8 text-pink-600" />
                        <div>
                          <p className="font-semibold text-gray-900">{Math.round(interview.score)}% overall</p>
                          <p className="text-sm text-gray-600">
                            {interview.questions.length} question(s) · full transcript available
                          </p>
                        </div>
                      </div>
                      <Button onClick={() => navigate('/interview-report')}>
                        View full interview report
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ) : (
              <Card className="border-0 shadow-lg">
                <CardContent className="py-12 text-center text-gray-500">
                  <Award className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>No interview completed yet.</p>
                  {quiz?.passed && <Button className="mt-4" onClick={() => navigate('/interview')}>Take the Interview</Button>}
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* ── Resources Tab ─────────────────────────────────────────────── */}
          <TabsContent value="resources" className="space-y-6">
            {!hasStarted ? (
              <Card className="border-0 shadow-lg">
                <CardContent className="py-12 text-center text-gray-500">
                  <Youtube className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>Complete an assessment to unlock recommendations tailored to your results.</p>
                  <Button className="mt-4" onClick={() => navigate('/resume-upload')}>
                    Upload Resume
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="grid lg:grid-cols-2 gap-6">
                {/* Plan-driven videos */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>
                  <Card className="border-0 shadow-lg h-full">
                    <CardHeader>
                      <div className="flex items-center gap-2">
                        <Youtube className="w-5 h-5 text-red-600" />
                        <CardTitle>Recommended Videos</CardTitle>
                      </div>
                      <CardDescription>
                        {weakAreas.length > 0
                          ? `Chosen from your improvement plan${targetRole ? ` for a ${targetRole} role` : ''}`
                          : 'You\u2019re above target everywhere \u2014 content to keep you sharp'}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {recommendedVideos.map(v => (
                        <a
                          key={v.title}
                          href={ytSearch(v.query)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block p-4 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 hover:border-gray-300 transition-colors group"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h5 className="font-semibold text-gray-900 mb-1 flex items-center gap-1.5">
                                <span className="truncate">{v.title}</span>
                                <ExternalLink className="w-3.5 h-3.5 text-gray-400 group-hover:text-gray-600 flex-shrink-0" />
                              </h5>
                              <p className="text-sm text-gray-600">{v.creators}</p>
                            </div>
                            <Badge className={`${focusColor(v.focus)} flex-shrink-0`}>{v.focus}</Badge>
                          </div>
                        </a>
                      ))}
                      <p className="text-xs text-gray-400 pt-1">
                        Each link opens a curated YouTube search for that topic.
                      </p>
                    </CardContent>
                  </Card>
                </motion.div>

                {/* Targeted practice / study plan */}
                <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                  <Card className="border-0 shadow-lg h-full">
                    <CardHeader>
                      <div className="flex items-center gap-2">
                        <Dumbbell className="w-5 h-5 text-blue-600" />
                        <CardTitle>Where to Practise</CardTitle>
                      </div>
                      <CardDescription>Hands-on resources matched to your weak areas</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {studyPlan.map(s => (
                        <a
                          key={s.label}
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block p-4 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors group"
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <h5 className="font-semibold text-blue-900 flex items-center gap-1.5">
                                {s.label}
                                <ExternalLink className="w-3.5 h-3.5 text-blue-400 group-hover:text-blue-600" />
                              </h5>
                              <p className="text-sm text-blue-800">{s.detail}</p>
                            </div>
                          </div>
                        </a>
                      ))}

                      {/* Always-useful reading; shown alongside the targeted list */}
                      <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                        <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-1.5">
                          <BookOpen className="w-4 h-4 text-gray-600" /> Recommended reading
                        </h5>
                        <ul className="text-sm text-gray-700 space-y-1">
                          {(weakAreas.some(w => w.area.includes('Technical') || w.area.includes('Quiz')) || weakAreas.length === 0) && (
                            <>
                              <li>• Cracking the Coding Interview — G. McDowell</li>
                              <li>• System Design Interview — Alex Xu</li>
                            </>
                          )}
                          {weakAreas.some(w => ['Behavioural Responses', 'Attentiveness', 'Eye Contact'].includes(w.area)) && (
                            <li>• Captivate — Vanessa Van Edwards (presence & communication)</li>
                          )}
                        </ul>
                      </div>

                      {studyPlan.length === 0 && weakAreas.length === 0 && (
                        <div className="p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-2">
                          <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                          <p className="text-sm text-green-800">No gaps to drill — keep practising to stay interview-ready.</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </motion.div>
              </div>
            )}
          </TabsContent>

          {/* ── Timeline Tab ──────────────────────────────────────────────── */}
          <TabsContent value="timeline" className="space-y-6">
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle>Your Journey Timeline</CardTitle>
                  <CardDescription>Track your milestones and progress</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {timeline.map((m, i) => (
                      <div key={m.title} className="flex gap-4">
                        <div className="flex flex-col items-center">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${m.done ? 'bg-green-100' : 'bg-gray-100'}`}>
                            {m.done
                              ? <CheckCircle2 className="w-5 h-5 text-green-600" />
                              : <Clock className="w-5 h-5 text-gray-400" />}
                          </div>
                          {i < timeline.length - 1 && <div className="w-0.5 h-12 bg-gray-200 mt-1" />}
                        </div>
                        <div className="flex-1 pb-8">
                          <div className="flex items-center justify-between mb-1">
                            <h4 className="font-semibold text-gray-900">{m.title}</h4>
                            {m.score != null && <Badge variant="outline">{Math.round(m.score)}%</Badge>}
                          </div>
                          <p className="text-sm text-gray-600">{m.date}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </TabsContent>
        </Tabs>

        {/* Action Buttons */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
          className="flex justify-center gap-4 mt-8"
        >
          {interview?.passed ? (
            <Button
              className="bg-green-500 hover:bg-green-600 text-white"
              size="lg" onClick={() => navigate('/profile-publication')}>
              Publish Profile
            </Button>
          ) : quiz?.passed && !interview ? (
            <Button size="lg" onClick={() => navigate('/interview')}>
              Take the Interview
            </Button>
          ) : quiz?.passed && interview && !interview.passed && !interviewCooldownActive ? (
            <Button size="lg" onClick={() => navigate('/interview')}>
              Retake Interview
            </Button>
          ) : resumeScore === 0 ? (
            <Button size="lg" onClick={() => navigate('/resume-upload')}>
              Upload Resume
            </Button>
          ) : resumeScore < 70 ? (
            <Button size="lg" onClick={() => navigate('/resume-feedback')}>
              Improve Resume
            </Button>
          ) : !quiz ? (
            <Button size="lg" onClick={() => navigate('/quiz')}>
              Take the Quiz
            </Button>
          ) : null}
          <Button variant="outline" size="lg" onClick={() => navigate('/dashboard')}>
            Back to Dashboard
          </Button>
        </motion.div>
      </div>
    </div>
  );
}