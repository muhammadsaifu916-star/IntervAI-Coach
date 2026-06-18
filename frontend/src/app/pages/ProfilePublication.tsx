import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { motion } from 'motion/react';
import {
  User, Mail, Phone, MapPin, Briefcase, Award, Code, Eye, EyeOff,
  ArrowLeft, CheckCircle2, Edit, Globe, Linkedin, Github, Loader2,
  Lock, AlertTriangle, X, Star,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Badge } from '../components/ui/badge';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { API_BASE_URL } from '../config';
import { getExperienceDisplay } from '../utils/experienceDisplay';

// ── Types matching the backend serializer ─────────────────────────────────────
interface RemoteProfile {
  bio: string;
  location: string;
  skills: string[];
  projects_summary: string;
  website: string;
  linkedin: string;
  github: string;
  show_contact: boolean;
  show_full_name: boolean;
  published: boolean;
  published_at: string | null;
  updated_at: string;
}

const EMPTY: RemoteProfile = {
  bio: '', location: '', skills: [], projects_summary: '',
  website: '', linkedin: '', github: '',
  show_contact: true, show_full_name: true,
  published: false, published_at: null, updated_at: '',
};


const PLACEHOLDER_HANDLES = new Set([
  'username', 'yourusername', 'your-username', 'your_name', 'yourname',
  'name', 'profile', 'example', 'sample', 'user', 'handle', 'linkedin',
]);

const normalizeProfileUrl = (value: string | null | undefined, type?: 'linkedin' | 'github' | 'website') => {
  const raw = (value || '').trim();
  if (!raw) return '';

  let cleaned = raw.replace(/[),.;\s]+$/g, '');
  if (type === 'linkedin') {
    const match = cleaned.match(/linkedin\.com\/(?:in|pub)\/([^/?#]+)/i);
    const handle = match?.[1]?.toLowerCase();
    if (handle && PLACEHOLDER_HANDLES.has(handle)) return '';
  }
  if (type === 'github') {
    const match = cleaned.match(/github\.com\/([^/?#]+)/i);
    const handle = match?.[1]?.toLowerCase();
    if (handle && PLACEHOLDER_HANDLES.has(handle)) return '';
  }

  if (!/^https?:\/\//i.test(cleaned)) {
    cleaned = `https://${cleaned.replace(/^www\./i, 'www.')}`;
  }
  return cleaned;
};

const sanitizeProfile = (data: RemoteProfile): RemoteProfile => ({
  ...EMPTY,
  ...data,
  skills: Array.from(new Set((data.skills || []).map(s => String(s).trim()).filter(Boolean))),
  website: normalizeProfileUrl(data.website, 'website'),
  linkedin: normalizeProfileUrl(data.linkedin, 'linkedin'),
  github: normalizeProfileUrl(data.github, 'github'),
});

// ── Component ─────────────────────────────────────────────────────────────────
export default function ProfilePublication() {
  const navigate = useNavigate();
  const { user, profile: authProfile, updateProfile, authFetch } = useAuth();

  const [remote, setRemote] = useState<RemoteProfile>(EMPTY);
  const [form, setForm] = useState<RemoteProfile>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [skillInput, setSkillInput] = useState('');

  const [interviewPassed, setInterviewPassed] = useState(false);
  const [latestInterviewScore, setLatestInterviewScore] = useState(authProfile?.interview_score ?? 0);
  const [interviewBreakdown, setInterviewBreakdown] = useState<{
    technical: number; personality: number; attentiveness: number; eye_contact: number;
  } | null>(null);

  // ── Fetch profile from backend on mount ────────────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        const interviewRes = await authFetch(`${API_BASE_URL}/api/interviews/latest/`);

        if (interviewRes.ok) {
          const interviewData = await interviewRes.json();
          const score = Number(interviewData.score ?? 0);

          setLatestInterviewScore(score);
          setInterviewPassed(Boolean(interviewData.passed) || score >= 70);

          // Capture the per-category breakdown so the preview can mirror the
          // "Verified Interview Performance" box employers see. /api/interviews/latest/
          // returns flat `*_score` fields, while the employer serializer uses an
          // `interview_breakdown` object with short names — support all shapes.
          const bd = interviewData.breakdown ?? interviewData.interview_breakdown ?? interviewData;
          const technical = bd.technical ?? bd.technical_score;
          const personality = bd.personality ?? bd.personality_score;
          const attentiveness = bd.attentiveness ?? bd.attentiveness_score;
          const eyeContact = bd.eye_contact ?? bd.eye_contact_score;
          if (technical != null || personality != null ||
            attentiveness != null || eyeContact != null) {
            setInterviewBreakdown({
              technical: Number(technical ?? 0),
              personality: Number(personality ?? 0),
              attentiveness: Number(attentiveness ?? 0),
              eye_contact: Number(eyeContact ?? 0),
            });
          }

          updateProfile({
            interview_score: score,
            interview_last_attempt: interviewData.submitted_at,
            interview_cooldown_until: interviewData.cooldown_until,
          });
        }
        const res = await authFetch(`${API_BASE_URL}/api/profiles/me/`);
        if (!res.ok) {
          if (res.status === 403) {
            toast.error('Only job seekers can access this page.');
            navigate('/dashboard');
            return;
          }
          throw new Error();
        }
        const data: RemoteProfile = sanitizeProfile(await res.json());
        setRemote(data);
        setForm(data);
        // If unpublished or empty, start in edit mode automatically
        setIsEditing(!data.published);
      } catch {
        toast.error('Failed to load profile.');
      } finally {
        setLoading(false);
      }
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Form handlers ──────────────────────────────────────────────────────────
  const handleField = (k: keyof RemoteProfile, v: any) => setForm(f => ({ ...f, [k]: v }));

  const addSkill = () => {
    const s = skillInput.trim();
    if (!s) return;
    if (form.skills.includes(s)) { setSkillInput(''); return; }
    if (form.skills.length >= 30) { toast.error('Maximum 30 skills.'); return; }
    setForm(f => ({ ...f, skills: [...f.skills, s] }));
    setSkillInput('');
  };

  const removeSkill = (s: string) =>
    setForm(f => ({ ...f, skills: f.skills.filter(x => x !== s) }));

  // ── API actions ────────────────────────────────────────────────────────────
  const saveDraft = async (): Promise<boolean> => {
    setSaving(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/profiles/me/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bio: form.bio,
          location: form.location,
          skills: form.skills,
          projects_summary: form.projects_summary,
          website: normalizeProfileUrl(form.website, 'website'),
          linkedin: normalizeProfileUrl(form.linkedin, 'linkedin'),
          github: normalizeProfileUrl(form.github, 'github'),
          // Contact details and full name are always revealed to an employer
          // once they purchase access — these are not user-gated.
          show_contact: true,
          show_full_name: true,
        }),
      });
      const rawData = await res.json();
      if (!res.ok) {
        toast.error(typeof rawData === 'object' ? Object.values(rawData).flat().join(' ') : 'Save failed.');
        return false;
      }
      const data = sanitizeProfile(rawData as RemoteProfile);
      setRemote(data);
      setForm(data);
      updateProfile({
        bio: data.bio,
        skills: data.skills,
        projects_summary: data.projects_summary,
        published: data.published,
      });
      toast.success('Profile saved.');
      if (data.published) setIsEditing(false);
      return true;
    } catch {
      toast.error('Network error.');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const publish = async () => {
    if (!interviewPassed) return;
    setPublishing(true);
    try {
      // Save form data first so backend has latest content for validation
      const saved = await saveDraft();
      if (!saved) return;

      const res = await authFetch(`${API_BASE_URL}/api/profiles/me/publish/`, { method: 'POST' });
      const rawData = await res.json();
      if (!res.ok) {
        toast.error((rawData as any).error || 'Publication failed.');
        return;
      }
      const data = sanitizeProfile(rawData as RemoteProfile);
      setRemote(data);
      setForm(data);
      updateProfile({ published: true });
      setIsEditing(false);
      toast.success('🎉 Profile published! Employers can now discover you.');
    } catch {
      toast.error('Network error.');
    } finally {
      setPublishing(false);
    }
  };

  const unpublish = async () => {
    setPublishing(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/profiles/me/unpublish/`, { method: 'POST' });
      const rawData = await res.json();
      if (!res.ok) { toast.error((rawData as any).error || 'Unpublish failed.'); return; }
      const data = sanitizeProfile(rawData as RemoteProfile);
      setRemote(data);
      setForm(data);
      updateProfile({ published: false });
      setIsEditing(true);
      toast.success('Profile hidden from employers.');
    } catch {
      toast.error('Network error.');
    } finally {
      setPublishing(false);
    }
  };

  // ── Score badge color (matches EmployerDashboard thresholds) ───────────────
  const scoreBadgeClass = (final: number) =>
    final >= 90 ? 'bg-green-100 text-green-700'
      : final >= 80 ? 'bg-yellow-100 text-yellow-700'
        : 'bg-gray-100 text-gray-700';

  // ── Profile preview (mirrors the EmployerDashboard candidate card) ─────────
  // `locked` = how employers see the profile BEFORE purchase: identity, contact,
  // bio, projects and links are hidden behind an anonymized handle. Unlocked =
  // the full post-purchase view.
  const ProfilePreview: React.FC<{ locked?: boolean }> = ({ locked = false }) => {
    const finalScore = authProfile?.final_score ?? 0;
    return (
      <div className="space-y-4">
        {/* Header row */}
        <div>
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            {locked ? (
              <Badge variant="outline" className="font-mono text-xs">
                Candidate #{user?.user_id ?? '————'}
              </Badge>
            ) : (
              <span className="text-lg font-bold text-gray-900">{user?.full_name || 'Your Name'}</span>
            )}
            {!!authProfile?.years_experience && (
              <Badge className="bg-blue-100 text-blue-700">
                {getExperienceDisplay(authProfile.years_experience, authProfile.experience_tier)}
              </Badge>
            )}
            <Badge className={scoreBadgeClass(finalScore)}>
              <Award className="w-3 h-3 mr-1" />Score: {finalScore}%
            </Badge>
          </div>
          {form.location && (
            <p className="text-sm text-gray-600 flex items-center gap-1">
              <MapPin className="w-3 h-3" />{form.location}
            </p>
          )}
        </div>

        {/* Contact — revealed only after purchase */}
        {!locked && (
          <div className="space-y-1 text-sm text-gray-600">
            <div className="flex items-center gap-2"><Mail className="w-4 h-4" /><span>{user?.email || '—'}</span></div>
            <div className="flex items-center gap-2"><Phone className="w-4 h-4" /><span>{user?.phone || '—'}</span></div>
          </div>
        )}

        {/* Bio — revealed only after purchase */}
        {!locked && (
          <div>
            <h4 className="font-semibold text-gray-900 mb-2 flex items-center gap-2"><User className="w-4 h-4" />About</h4>
            <p className="text-gray-700 text-sm">{form.bio || 'No bio added yet.'}</p>
          </div>
        )}

        {/* Skills */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Code className="w-4 h-4 text-gray-600" />
            <span className="text-sm font-medium text-gray-700">Technical Skills:</span>
          </div>
          {form.skills.length === 0 ? (
            <p className="text-sm text-gray-400 italic">No skills listed</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {form.skills.map(s => <Badge key={s} variant="outline" className="text-sm">{s}</Badge>)}
            </div>
          )}
        </div>

        {/* Score breakdown */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center p-3 bg-blue-50 rounded-lg">
            <div className="text-2xl font-bold text-blue-600">{authProfile?.resume_score ?? 0}%</div>
            <div className="text-xs text-gray-600">Resume</div>
          </div>
          <div className="text-center p-3 bg-purple-50 rounded-lg">
            <div className="text-2xl font-bold text-purple-600">{authProfile?.quiz_score ?? 0}%</div>
            <div className="text-xs text-gray-600">Quiz</div>
          </div>
          <div className="text-center p-3 bg-pink-50 rounded-lg">
            <div className="text-2xl font-bold text-pink-600">{latestInterviewScore}%</div>
            <div className="text-xs text-gray-600">Interview</div>
          </div>
        </div>

        {/* Verified interview performance */}
        {interviewBreakdown && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-3">
            <p className="text-sm font-medium text-green-900 mb-2 flex items-center gap-1">
              <Star className="w-3 h-3" />Verified Interview Performance
            </p>
            <div className="grid grid-cols-4 gap-2 text-xs">
              <div><span className="text-gray-600">Technical:</span> <strong className="text-green-800">{interviewBreakdown.technical}%</strong></div>
              <div><span className="text-gray-600">Behavioural:</span> <strong className="text-green-800">{interviewBreakdown.personality}%</strong></div>
              <div><span className="text-gray-600">Attentiveness:</span> <strong className="text-green-800">{interviewBreakdown.attentiveness}%</strong></div>
              <div><span className="text-gray-600">Eye Contact:</span> <strong className="text-green-800">{interviewBreakdown.eye_contact}%</strong></div>
            </div>
          </div>
        )}

        {/* Projects — revealed only after purchase */}
        {!locked && (
          <div>
            <h4 className="font-semibold text-gray-900 mb-2 flex items-center gap-2"><Briefcase className="w-4 h-4" />Projects & Experience</h4>
            <p className="text-gray-700 text-sm">{form.projects_summary || 'No projects added yet.'}</p>
          </div>
        )}

        {/* Social — revealed only after purchase */}
        {!locked && (form.website || form.linkedin || form.github) && (
          <div className="pt-4 border-t">
            <div className="flex gap-3 flex-wrap">
              {form.website && <Button asChild variant="outline" size="sm"><a href={form.website} target="_blank" rel="noopener noreferrer"><Globe className="w-4 h-4 mr-2" />Website</a></Button>}
              {form.linkedin && <Button asChild variant="outline" size="sm"><a href={form.linkedin} target="_blank" rel="noopener noreferrer"><Linkedin className="w-4 h-4 mr-2" />LinkedIn</a></Button>}
              {form.github && <Button asChild variant="outline" size="sm"><a href={form.github} target="_blank" rel="noopener noreferrer"><Github className="w-4 h-4 mr-2" />GitHub</a></Button>}
            </div>
          </div>
        )}

        {/* Lock note (pre-purchase) */}
        {locked && (
          <p className="text-xs text-gray-500 flex items-center gap-1">
            <Lock className="w-3 h-3" />Name, contact info, and bio unlock after purchase
          </p>
        )}
      </div>
    );
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="w-12 h-12 text-blue-600 animate-spin mx-auto" />
          <p className="text-gray-600 font-medium">Loading your profile…</p>
        </div>
      </div>
    );
  }

  // Locked: interview not passed yet
  if (!interviewPassed) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }} className="max-w-2xl w-full">
          <Card className="border-0 shadow-2xl">
            <CardHeader className="text-center pb-0">
              <div className="w-20 h-20 mx-auto mb-4 bg-gradient-to-br from-orange-600 to-red-600 rounded-full flex items-center justify-center">
                <Lock className="w-10 h-10 text-white" />
              </div>
              <CardTitle className="text-3xl mb-2">Profile Locked</CardTitle>
              <CardDescription>You must pass the interview before publishing your profile.</CardDescription>
            </CardHeader>
            <CardContent className="pt-6 space-y-4">
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-orange-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-orange-800">
                  <p className="font-semibold mb-1">Pipeline progress</p>
                  <ul className="space-y-1">
                    <li>Resume score: <strong>{authProfile?.resume_score ?? 0}%</strong> {(authProfile?.resume_score ?? 0) >= 70 ? '✓' : ''}</li>
                    <li>Quiz score: <strong>{authProfile?.quiz_score ?? 0}%</strong> {(authProfile?.quiz_score ?? 0) >= 70 ? '✓' : ''}</li>
                    <li>
                      Interview score: <strong>{latestInterviewScore}%</strong> {interviewPassed ? '✓' : ''}
                    </li>
                  </ul>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Button variant="outline" onClick={() => navigate('/dashboard')}>Back to Dashboard</Button>
                <Button onClick={() => navigate('/interview')}>Take Interview</Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
              <ArrowLeft className="w-4 h-4 mr-2" />Back to Dashboard
            </Button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <User className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">Profile Publication</h1>
                <p className="text-sm text-gray-600">
                  {remote.published ? 'Your profile is live to employers' : 'Create and publish your profile'}
                </p>
              </div>
            </div>
          </div>
          {remote.published && (
            <Badge className="bg-green-100 text-green-700 px-3 py-1">
              <span className="w-2 h-2 bg-green-600 rounded-full mr-2 inline-block animate-pulse" />
              Live
            </Badge>
          )}
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid lg:grid-cols-2 gap-8">
          {/* ── LEFT: Edit form ──────────────────────────────────────────── */}
          <div className="space-y-6">
            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}>
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Profile Information</CardTitle>
                      <CardDescription>{isEditing ? 'Review and edit your profile details' : 'Your published profile'}</CardDescription>
                    </div>
                    {remote.published && (
                      <Button variant="outline" size="sm" onClick={() => { setIsEditing(e => !e); if (isEditing) setForm(remote); }}>
                        {isEditing ? <><X className="w-4 h-4 mr-2" />Cancel</>
                          : <><Edit className="w-4 h-4 mr-2" />Edit</>}
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Bio */}
                  <div className="space-y-2">
                    <Label htmlFor="bio">Professional Bio *</Label>
                    <Textarea id="bio" rows={4} disabled={!isEditing}
                      placeholder="Write a brief description about yourself, your expertise, and career goals…"
                      value={form.bio} onChange={e => handleField('bio', e.target.value)} />
                  </div>

                  {/* Location */}
                  <div className="space-y-2">
                    <Label htmlFor="location">Location</Label>
                    <div className="relative">
                      <MapPin className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                      <Input id="location" placeholder="City, State/Country" className="pl-10"
                        disabled={!isEditing}
                        value={form.location} onChange={e => handleField('location', e.target.value)} />
                    </div>
                  </div>

                  {/* Skills */}
                  <div className="space-y-2">
                    <Label>Technical Skills *</Label>
                    <div className="flex flex-wrap gap-2 mb-2 min-h-[2rem]">
                      {form.skills.map(s => (
                        <Badge key={s} variant="secondary" className={isEditing ? 'cursor-pointer hover:bg-red-100' : ''}
                          onClick={() => isEditing && removeSkill(s)}>
                          {s}{isEditing && <span className="ml-1">×</span>}
                        </Badge>
                      ))}
                      {form.skills.length === 0 && <span className="text-sm text-gray-400 italic">Add at least one skill</span>}
                    </div>
                    {isEditing && (
                      <Input placeholder="Add a skill and press Enter" value={skillInput}
                        onChange={e => setSkillInput(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSkill(); } }} />
                    )}
                  </div>

                  {/* Projects */}
                  <div className="space-y-2">
                    <Label htmlFor="projects">Projects & Experience Summary</Label>
                    <Textarea id="projects" rows={4} disabled={!isEditing}
                      placeholder="Describe your key projects, achievements, and professional experience…"
                      value={form.projects_summary} onChange={e => handleField('projects_summary', e.target.value)} />
                  </div>

                  {/* Social */}
                  <div className="space-y-3 pt-4 border-t">
                    <Label>Social & Professional Links</Label>
                    {[
                      { key: 'website', icon: Globe, placeholder: 'Website URL' },
                      { key: 'linkedin', icon: Linkedin, placeholder: 'LinkedIn URL' },
                      { key: 'github', icon: Github, placeholder: 'GitHub URL' },
                    ].map(({ key, icon: Icon, placeholder }) => (
                      <div key={key} className="relative">
                        <Icon className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                        <Input className="pl-10" disabled={!isEditing} placeholder={placeholder}
                          value={(form as any)[key]} onChange={e => handleField(key as keyof RemoteProfile, e.target.value)} />
                      </div>
                    ))}
                  </div>

                  {isEditing && (
                    <Button className="w-full" onClick={saveDraft} disabled={saving}>
                      {saving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
                        : <><CheckCircle2 className="w-4 h-4 mr-2" />Save Changes</>}
                    </Button>
                  )}
                </CardContent>
              </Card>
            </motion.div>

            {/* Publish card */}
            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }}>
              <Card className="border-0 shadow-lg">
                <CardContent className="pt-6 space-y-3">
                  {remote.published ? (
                    <Button
                      className="w-full border-red-500 text-red-600 hover:bg-red-50 hover:text-red-700"
                      variant="outline" size="lg" onClick={unpublish} disabled={publishing}>
                      {publishing ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Working…</>
                        : <><EyeOff className="w-4 h-4 mr-2" />Unpublish Profile</>}
                    </Button>
                  ) : (
                    <Button
                      className="w-full bg-green-500 hover:bg-green-600 text-white"
                      size="lg" onClick={publish} disabled={publishing}>
                      {publishing ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Publishing…</>
                        : 'Publish Profile'}
                    </Button>
                  )}
                  {!remote.published && (!form.bio.trim() || form.skills.length === 0) && (
                    <p className="text-xs text-gray-500 text-center">
                      Add a bio and at least one skill to enable publication.
                    </p>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </div>

          {/* ── RIGHT: Preview ───────────────────────────────────────────── */}
          <div className="space-y-6">
            <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}>
              <Card className="border-0 shadow-lg sticky top-24">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Profile Preview</CardTitle>
                      <CardDescription>How employers will see your profile</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setShowPreview(p => !p)}>
                      {showPreview ? <><EyeOff className="w-4 h-4 mr-2" />Hide Details</>
                        : <><Eye className="w-4 h-4 mr-2" />Show Details</>}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-gray-500 mb-4">
                    {showPreview
                      ? 'Full view — what an employer sees after purchasing access to your profile.'
                      : 'Pre-purchase view — how employers see your profile before unlocking it.'}
                  </p>
                  <ProfilePreview locked={!showPreview} />
                </CardContent>
              </Card>
            </motion.div>

            <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }}>
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="text-lg">Profile Visibility</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                    <p className="text-gray-700"><strong>Visible to all:</strong> Skills, experience tier, and assessment scores</p>
                  </div>
                  <div className="flex items-start gap-3">
                    <EyeOff className="w-5 h-5 text-orange-600 flex-shrink-0 mt-0.5" />
                    <p className="text-gray-700"><strong>Hidden until purchase:</strong> Full name, contact details, bio, and project descriptions</p>
                  </div>
                  <div className="flex items-start gap-3">
                    <Award className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                    <p className="text-gray-700"><strong>Verification:</strong> All scores are AI-verified and cannot be edited</p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  );
}
