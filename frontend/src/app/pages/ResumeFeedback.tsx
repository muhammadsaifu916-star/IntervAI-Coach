import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { motion } from 'motion/react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowLeft,
  FileText,
  Download,
  RefreshCw,
  TrendingUp,
  Brain,
  Sparkles,
  ListChecks,
  Target,
  ShieldAlert,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import { useAuth } from '../context/AuthContext';

type LegacyFeedback = {
  scores?: {
    grammar?: number;
    formatting?: number;
    keywords?: number;
    actionVerbs?: number;
    length?: number;
  };
  suggestions?: {
    type: string;
    title: string;
    description: string;
  }[];
};

type QualityDimension = {
  score: number;
  max?: number;
  note?: string;
  detail?: string;
  found?: string[];
  bullet_count?: number;
};

type QualityAnalysis = Record<string, QualityDimension>;

type PlanItem = {
  gap?: string;
  area?: string;
  issue?: string;
  impact?: string;
  recommendation?: string;
};

type ImprovementPlan = Record<string, PlanItem[]>;

type GrammarIssue = {
  original_text?: string;
  corrected_text?: string;
  original?: string;
  corrected?: string;
  error_type?: string;
  explanation?: string;
};

type ResumeFeedbackState = {
  resume_id?: number;
  score?: number;
  feedback?: string | LegacyFeedback;
  grade?: string;
  detected_role?: string;
  target_role?: string;
  selected_role?: string;
  role_alignment?: 'auto' | 'full_match' | 'related_mismatch' | 'hard_mismatch';
  role_penalty?: number;
  role_mismatch_block?: boolean;
  role_match_message?: string;
  analysis_log?: { step: string; detail: string }[];
  analysis_data?: Record<string, any>;
  strengths?: string[];
  weaknesses?: string[];
  improvement_plan?: ImprovementPlan;
  quality_analysis?: QualityAnalysis;
  grammar_issues?: GrammarIssue[];
  missing_sections?: string[];
  quiz_unlocked?: boolean;
  progress_cleared?: boolean;
};

const dimensionLabels: Record<string, string> = {
  sections_completeness: 'Resume Completeness',
  grammar_spelling: 'Grammar & Spelling',
  bullet_points: 'Bullet Formatting',
  action_verbs: 'Action Verbs',
  professional_tone: 'Professional Tone',
  readability: 'Length & Readability',
  technical_skills: 'Technical Skill Coverage',
  projects_quality: 'Projects Quality',
  quantified_achievements: 'Quantified Achievements',
};

const planSections = [
  {
    key: 'skill_gap',
    title: 'Skill Gap Analysis',
    description: 'Missing role-specific skills and how to add them.',
  },
  {
    key: 'technical',
    title: 'Technical Enhancement',
    description: 'Project, GitHub, section, and technical presentation fixes.',
  },
  {
    key: 'experience',
    title: 'Experience & Impact Upgrade',
    description: 'Action verbs, bullet points, metrics, and experience clarity.',
  },
  {
    key: 'communication',
    title: 'Communication & Clarity',
    description: 'Grammar, tone, readability, and professional writing fixes.',
  },
];

function safeArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function isLegacyFeedback(value: unknown): value is LegacyFeedback {
  return Boolean(value && typeof value === 'object');
}

function formatDimensionName(key: string) {
  return dimensionLabels[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
}

export default function ResumeFeedback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { profile, canTakeQuiz } = useAuth();
  const [selectedTemplate, setSelectedTemplate] = useState<number | null>(null);

  const state = location.state as ResumeFeedbackState | null;
  const profileAny = profile as any;
  const latestResume = profileAny?.latest_resume ?? profileAny?.latestResume ?? {};
  const profileFeedback = profileAny?.resume_feedback;

  // The full analysis is stored on the resume as `analysis_data` (a JSON field),
  // so we use it as a fallback for every field. This keeps the page populated
  // even when router state is lost (e.g. on a page refresh or direct link),
  // as long as the resume/profile endpoint returns analysis_data.
  const analysisData = (
    state?.analysis_data ??
    latestResume?.analysis_data ??
    {}
  ) as Record<string, any>;

  const feedbackSource = state?.feedback ?? latestResume?.feedback ?? profileFeedback;
  const legacyFeedback = isLegacyFeedback(feedbackSource) ? feedbackSource : undefined;
  const feedbackMessage =
    typeof feedbackSource === 'string'
      ? feedbackSource
      : (latestResume?.message ?? analysisData.message);

  const resumeScore = Number(
    state?.score ??
    latestResume?.score ??
    latestResume?.resume_score ??
    analysisData.resume_score ??
    profileAny?.resume_score ??
    0
  );

  const overallGrade =
    state?.grade ??
    latestResume?.grade ??
    analysisData.grade ??
    (
      resumeScore >= 85 ? 'Excellent' :
        resumeScore >= 70 ? 'Good' :
          resumeScore >= 50 ? 'Satisfactory' : 'Weak'
    );

  const detectedRole = state?.detected_role ?? latestResume?.detected_role ?? analysisData.detected_role;

  // --- Role match / mismatch (the role the user selected vs what the AI detected) ---
  const selectedRole =
    state?.selected_role ??
    state?.target_role ??
    (analysisData.selected_role as string | undefined) ??
    (analysisData.target_role as string | undefined) ??
    latestResume?.job_role;
  const roleAlignment =
    state?.role_alignment ??
    (analysisData.role_alignment as ResumeFeedbackState['role_alignment']) ??
    'auto';
  const roleMismatchBlock =
    state?.role_mismatch_block ??
    (analysisData.role_mismatch_block as boolean | undefined) ??
    false;
  const rolePenalty =
    state?.role_penalty ??
    (analysisData.role_penalty as number | undefined) ??
    0;
  const roleMatchMessage =
    state?.role_match_message ??
    (analysisData.role_match_message as string | undefined);
  const isRelatedMismatch = roleAlignment === 'related_mismatch';
  const isFullMatch = roleAlignment === 'full_match';

  const analysisLog = safeArray<{ step: string; detail: string }>(
    state?.analysis_log ?? (analysisData.analysis_log as { step: string; detail: string }[] | undefined)
  );

  const strengths = safeArray<string>(state?.strengths ?? latestResume?.strengths ?? analysisData.strengths);
  const weaknesses = safeArray<string>(state?.weaknesses ?? latestResume?.weaknesses ?? analysisData.weaknesses);
  const improvementPlan = (state?.improvement_plan ?? latestResume?.improvement_plan ?? analysisData.improvement_plan ?? {}) as ImprovementPlan;
  const qualityAnalysis = (state?.quality_analysis ?? latestResume?.quality_analysis ?? analysisData.quality_analysis ?? {}) as QualityAnalysis;
  const grammarIssues = safeArray<GrammarIssue>(state?.grammar_issues ?? latestResume?.grammar_issues ?? analysisData.grammar_issues);
  const missingSections = safeArray<string>(state?.missing_sections ?? latestResume?.missing_sections ?? analysisData.missing_sections);

  const quizAccess = canTakeQuiz();
  const resumeAllowsQuiz =
    !roleMismatchBlock && (state?.quiz_unlocked ?? resumeScore >= 70);

  const isQuizCooldown =
    Boolean(quizAccess.cooldownEnd && quizAccess.cooldownEnd > new Date());

  const hasPassedQuiz = (profile?.quiz_score ?? 0) >= 70;

  const iconMap: Record<string, { icon: React.ElementType; color: string; bgColor: string }> = {
    success: { icon: CheckCircle2, color: 'text-green-600', bgColor: 'bg-green-50 border-green-200' },
    warning: { icon: AlertTriangle, color: 'text-orange-600', bgColor: 'bg-orange-50 border-orange-200' },
    info: { icon: TrendingUp, color: 'text-blue-600', bgColor: 'bg-blue-50 border-blue-200' },
    error: { icon: XCircle, color: 'text-red-600', bgColor: 'bg-red-50 border-red-200' },
  };

  const legacyScores = legacyFeedback?.scores ?? {
    grammar: 0,
    formatting: 0,
    keywords: 0,
    actionVerbs: 0,
    length: 0,
  };

  const qualityItems = Object.keys(qualityAnalysis).length > 0
    ? Object.entries(qualityAnalysis).map(([key, value]) => {
      const max = value.max ?? 10;
      const score = value.score ?? 0;
      const percent = max > 0 ? Math.round((score / max) * 100) : 0;

      return {
        key,
        label: formatDimensionName(key),
        value: percent,
        displayScore: `${score}/${max}`,
        note: value.note,
      };
    })
    : Object.entries(legacyScores).map(([key, value]) => ({
      key,
      label: key.replace(/([A-Z])/g, ' $1').trim(),
      value: Number(value ?? 0),
      displayScore: `${Number(value ?? 0)}%`,
      note: '',
    }));

  const suggestions = (legacyFeedback?.suggestions ?? []).map((s) => ({
    ...s,
    ...(iconMap[s.type] ?? iconMap['info']),
  }));

  const hasImprovementPlan = planSections.some(section => {
    const items = improvementPlan?.[section.key];
    return Array.isArray(items) && items.length > 0;
  });

  const templates = [
    {
      id: 1,
      name: 'Modern Professional',
      description: 'Clean and contemporary design',
      file: '/templates/modern-professional-resume.pdf',
    },
    {
      id: 2,
      name: 'Classic Executive',
      description: 'Traditional and formal layout',
      file: '/templates/classic-executive-resume.pdf',
    },
    {
      id: 3,
      name: 'Creative Tech',
      description: 'Bold and innovative style',
      file: '/templates/creative-tech-resume.pdf',
    },
    {
      id: 4,
      name: 'Minimalist Clean',
      description: 'Simple and elegant design',
      file: '/templates/minimalist-clean-resume.pdf',
    },
  ];

  const selectedTemplateData = templates.find(
    (template) => template.id === selectedTemplate
  );

  const handleProceed = () => {
    navigate('/dashboard');
  };

  const handleUploadNew = () => {
    navigate('/resume-upload');
  };

  const handleBack = () => {
    navigate(-1);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={handleBack}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <FileText className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">AI Resume Feedback</h1>
                <p className="text-sm text-gray-600">Analysis Complete</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Overall Score */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="border-0 shadow-2xl mb-8 overflow-hidden">
            <div
              className={`text-white p-8 ${
                roleMismatchBlock
                  ? 'bg-gradient-to-r from-rose-600 to-red-700'
                  : 'bg-gradient-to-r from-blue-600 to-purple-600'
              }`}
            >
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="space-y-3">
                  <div>
                    <h2 className="text-3xl font-bold mb-1">Resume Score</h2>
                    <p className={roleMismatchBlock ? 'text-rose-100' : 'text-blue-100'}>
                      Based on comprehensive AI analysis
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedRole && (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-medium backdrop-blur-sm">
                        <Target className="w-3.5 h-3.5" />
                        Selected: <span className="font-semibold">{selectedRole}</span>
                      </span>
                    )}
                    {detectedRole && (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-medium backdrop-blur-sm">
                        <Brain className="w-3.5 h-3.5" />
                        AI detected: <span className="font-semibold">{detectedRole}</span>
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-6xl font-bold mb-2">{resumeScore}%</div>
                  {roleMismatchBlock ? (
                    <Badge className="bg-white text-red-700 hover:bg-white text-sm px-4 py-1 font-semibold">
                      Role Mismatch
                    </Badge>
                  ) : (
                    <Badge className="bg-white text-blue-600 hover:bg-white text-lg px-4 py-1">
                      {overallGrade}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <CardContent className="pt-6 space-y-4">
              {/* Role match / mismatch banner */}
              {roleMismatchBlock ? (
                <div className="bg-red-50 border-2 border-red-200 rounded-lg p-4 flex items-start gap-3">
                  <ShieldAlert className="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="font-semibold text-red-900">
                      This resume doesn&apos;t match the role you selected
                    </p>
                    <p className="text-sm text-red-800">
                      {roleMatchMessage ??
                        `Your resume looks like a ${detectedRole ?? 'different'} resume, but you selected ${selectedRole}. Because these are different fields, it was scored 0 for ${selectedRole}.`}
                    </p>
                    <p className="text-sm text-red-700">
                      Upload a resume tailored to <span className="font-semibold">{selectedRole}</span>
                      {detectedRole && (
                        <> , or re-upload and select <span className="font-semibold">{detectedRole}</span></>
                      )}
                      .
                    </p>
                  </div>
                </div>
              ) : (isRelatedMismatch || roleAlignment === 'hard_mismatch') ? (
                <div className={`${isRelatedMismatch ? 'bg-amber-50 border border-amber-200' : 'bg-red-50 border-2 border-red-200'} rounded-lg p-4 flex items-start gap-3`}>
                  <AlertTriangle className={`w-6 h-6 ${isRelatedMismatch ? 'text-amber-600' : 'text-red-600'} flex-shrink-0 mt-0.5`} />
                  <div className="space-y-1">
                    <p className={`font-semibold ${isRelatedMismatch ? 'text-amber-900' : 'text-red-900'}`}>
                      {isRelatedMismatch ? `Partial role match · −${rolePenalty} points` : 'Hard role mismatch'}
                    </p>
                    <p className={`text-sm ${isRelatedMismatch ? 'text-amber-800' : 'text-red-800'}`}>
                      {roleMatchMessage ??
                        (isRelatedMismatch
                          ? `Your resume is in the same field as ${selectedRole} but reads more like a ${detectedRole} resume. Tailor it to ${selectedRole} to score higher.`
                          : `Your resume looks like a ${detectedRole} resume, but you selected ${selectedRole}. These are different fields, so a scoring penalty applies.`)}
                    </p>
                  </div>
                </div>
              ) : isFullMatch ? (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-green-800">
                    {roleMatchMessage ?? `Your resume matches the selected role${selectedRole ? ` ‘${selectedRole}’` : ''}.`}
                  </p>
                </div>
              ) : feedbackMessage ? (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <p className="text-sm text-blue-900">{feedbackMessage}</p>
                </div>
              ) : null}

              {resumeAllowsQuiz ? (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-start gap-3">
                  <CheckCircle2 className="w-6 h-6 text-green-600 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-green-900">
                      {hasPassedQuiz ? 'Quiz Already Passed' : 'Congratulations! 🎉'}
                    </p>

                    <p className="text-sm text-green-700">
                      {hasPassedQuiz
                        ? 'Your resume score is above 70% and you have already passed the quiz.'
                        : isQuizCooldown
                          ? 'Your resume score is above 70%. You are eligible for the quiz, but your quiz is currently in cooldown. You can still upload a new resume anytime.'
                          : 'Your resume score is above 70%. You are now eligible to take the quiz!'}
                    </p>
                  </div>
                </div>
              ) : roleMismatchBlock ? (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
                  <ShieldAlert className="w-6 h-6 text-red-600 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-red-900">Quiz locked</p>
                    <p className="text-sm text-red-700">
                      The quiz unlocks once you submit a resume that matches your selected role and scores 70% or higher.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-start gap-3">
                  <AlertTriangle className="w-6 h-6 text-orange-600 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-orange-900">
                      Score Below Threshold
                    </p>

                    <p className="text-sm text-orange-700">
                      You need a minimum score of 70% to be eligible for the quiz. Please review the improvement plan below and resubmit your resume.
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <div className="grid lg:grid-cols-2 gap-8">
          {/* Left Column - Detailed Scores */}
          <div className="space-y-6">
            {analysisLog.length > 0 && (
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 }}
              >
                <Card className="border-0 shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <ListChecks className="w-5 h-5 text-blue-600" />
                      Analysis Steps
                    </CardTitle>
                    <CardDescription>How the AI engine processed your resume</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ol className="relative border-l border-gray-200 ml-2 space-y-4">
                      {analysisLog.map((entry, index) => (
                        <li key={index} className="ml-4">
                          <span className="absolute -left-[7px] flex h-3.5 w-3.5 items-center justify-center rounded-full bg-blue-600 ring-4 ring-white" />
                          <p className="text-sm font-semibold text-gray-900">{entry.step}</p>
                          <p className="text-sm text-gray-600">{entry.detail}</p>
                        </li>
                      ))}
                    </ol>
                  </CardContent>
                </Card>
              </motion.div>
            )}

            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
            >
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Brain className="w-5 h-5 text-blue-600" />
                    Detailed Analysis
                  </CardTitle>
                  <CardDescription>Breakdown of your resume evaluation</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {qualityItems.map((item) => (
                    <div key={item.key} className="border rounded-lg p-3 bg-white">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium capitalize">
                          {item.label}
                        </span>
                        <span className="text-sm font-bold">{item.displayScore}</span>
                      </div>
                      <Progress value={item.value} className="h-2" />
                      {item.note && (
                        <p className="text-xs text-gray-600 mt-2">{item.note}</p>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 }}
            >
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle>Strengths & Weaknesses</CardTitle>
                  <CardDescription>Key positives and weak areas from the AI analysis</CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div>
                    <h3 className="font-semibold text-green-900 mb-3 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-green-600" />
                      Strengths
                    </h3>
                    {strengths.length === 0 ? (
                      <p className="text-sm text-gray-500">No major strengths detected yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {strengths.map((item, index) => (
                          <div key={index} className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-900">
                            {item}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="font-semibold text-orange-900 mb-3 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-orange-600" />
                      Weaknesses
                    </h3>
                    {weaknesses.length === 0 ? (
                      <p className="text-sm text-gray-500">No major weaknesses detected.</p>
                    ) : (
                      <div className="space-y-2">
                        {weaknesses.map((item, index) => (
                          <div key={index} className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-900">
                            {item}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.35 }}
            >
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle>Grammar Issues</CardTitle>
                  <CardDescription>Detected grammar or spelling problems</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {grammarIssues.length === 0 ? (
                    <p className="text-sm text-gray-500">No grammar issues detected.</p>
                  ) : (
                    grammarIssues.slice(0, 8).map((issue, index) => (
                      <div key={index} className="bg-gray-50 border rounded-lg p-3">
                        <Badge variant="outline" className="mb-2">
                          {issue.error_type || 'grammar'}
                        </Badge>

                        {(issue.original_text || issue.original) && (
                          <p className="text-sm text-gray-700">
                            <span className="font-semibold">Original:</span>{' '}
                            {issue.original_text || issue.original}
                          </p>
                        )}

                        {(issue.corrected_text || issue.corrected) && (
                          <p className="text-sm text-gray-700 mt-1">
                            <span className="font-semibold">Corrected:</span>{' '}
                            {issue.corrected_text || issue.corrected}
                          </p>
                        )}

                        {issue.explanation && (
                          <p className="text-xs text-gray-500 mt-2">{issue.explanation}</p>
                        )}
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </div>

          {/* Right Column - Templates + Next Steps */}
          <div className="space-y-6">
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4 }}
            >
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle>Suggested Templates</CardTitle>
                  <CardDescription>Choose a professional template for your resume</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {templates.map((template) => (
                    <div
                      key={template.id}
                      className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${selectedTemplate === template.id
                        ? 'border-blue-600 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                        }`}
                      onClick={() => setSelectedTemplate(template.id)}
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-semibold text-gray-900">{template.name}</h4>
                          <p className="text-sm text-gray-600">{template.description}</p>
                        </div>
                        {selectedTemplate === template.id && (
                          <CheckCircle2 className="w-6 h-6 text-blue-600" />
                        )}
                      </div>
                    </div>
                  ))}
                  {selectedTemplateData && (
                    <Button variant="outline" className="w-full" asChild>
                      <a href={selectedTemplateData.file} download>
                        <Download className="w-4 h-4 mr-2" />
                        Download Selected Template
                      </a>
                    </Button>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.45 }}
            >
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle>Missing Sections</CardTitle>
                  <CardDescription>Important sections not found in your resume</CardDescription>
                </CardHeader>
                <CardContent>
                  {missingSections.length === 0 ? (
                    <p className="text-sm text-gray-500">No important sections are missing.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {missingSections.map((section, index) => (
                        <Badge key={index} variant="outline" className="bg-red-50 text-red-700 border-red-200">
                          {section}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {suggestions.length > 0 && (
              <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5 }}
              >
                <Card className="border-0 shadow-lg">
                  <CardHeader>
                    <CardTitle>AI Suggestions</CardTitle>
                    <CardDescription>Legacy recommendations from previous analyzer</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {suggestions.map((suggestion, index) => (
                      <div
                        key={index}
                        className={`${suggestion.bgColor} border rounded-lg p-4 flex items-start gap-3`}
                      >
                        <suggestion.icon className={`w-5 h-5 ${suggestion.color} flex-shrink-0 mt-0.5`} />
                        <div>
                          <p className={`font-semibold ${suggestion.color} mb-1`}>
                            {suggestion.title}
                          </p>
                          <p className="text-sm text-gray-700">{suggestion.description}</p>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </motion.div>
            )}

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.55 }}
            >
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle>Next Steps</CardTitle>
                  <CardDescription>Continue your journey</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {resumeAllowsQuiz && !isQuizCooldown && !hasPassedQuiz && (
                    <Button
                      className="w-full bg-green-500 hover:bg-green-600 text-white"
                      size="lg"
                      onClick={() => navigate('/quiz')}
                    >
                      Proceed to Quiz
                    </Button>
                  )}

                  <Button className="w-full" size="lg" onClick={handleProceed}>
                    {resumeAllowsQuiz ? 'Go to Dashboard' : 'Back to Dashboard'}
                  </Button>

                  <Button variant="outline" className="w-full" onClick={handleUploadNew}>
                    <RefreshCw className="w-4 h-4 mr-2" />
                    Upload New Resume
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </div>

        {/* Full Improvement Plan */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.65 }}
          className="mt-8"
        >
          <Card className="border-0 shadow-lg">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-600" />
                Improvement Plan
              </CardTitle>
              <CardDescription>
                Specific recommendations generated from your resume analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!hasImprovementPlan ? (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-green-900">No critical improvement plan needed</p>
                    <p className="text-sm text-green-700">
                      Your resume has no major weak areas according to the latest analysis.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {planSections.map((section) => {
                    const items = improvementPlan?.[section.key] || [];
                    if (!items.length) return null;

                    return (
                      <div key={section.key}>
                        <div className="mb-3">
                          <h3 className="text-lg font-bold text-gray-900">{section.title}</h3>
                          <p className="text-sm text-gray-500">{section.description}</p>
                        </div>

                        <div className="grid md:grid-cols-2 gap-4">
                          {items.map((item, index) => {
                            const title = item.gap || item.area || item.issue || `Suggestion ${index + 1}`;

                            return (
                              <div key={index} className="border rounded-lg p-4 bg-purple-50/40">
                                <div className="flex items-start gap-2 mb-3">
                                  <ListChecks className="w-4 h-4 text-purple-600 mt-1 flex-shrink-0" />
                                  <p className="font-semibold text-gray-900">{title}</p>
                                </div>

                                {item.impact && (
                                  <p className="text-sm text-gray-700 mb-2">
                                    <span className="font-semibold">Impact:</span>{' '}
                                    {item.impact}
                                  </p>
                                )}

                                {item.recommendation && (
                                  <p className="text-sm text-gray-700">
                                    <span className="font-semibold">Recommendation:</span>{' '}
                                    {item.recommendation}
                                  </p>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
