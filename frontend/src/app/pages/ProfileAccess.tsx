import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { motion } from 'motion/react';
import {
  Check, ArrowLeft, Lock, Shield, Download, Mail, Phone,
  MapPin, Award, Code, Briefcase, User, CheckCircle2, Loader2,
  ShoppingBag, Star, Calendar, Hash, AlertCircle, ExternalLink, Globe,
  Linkedin, Github, Eye,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { API_BASE_URL } from '../config';
import jsPDF from 'jspdf';
import { getExperienceDisplay } from '../utils/experienceDisplay';

// ── Types ─────────────────────────────────────────────────────────────────────
interface Package {
  id: number;
  slug: string;
  name: string;
  price: string;        // DecimalField → string
  profile_limit: number;        // 0 = unlimited
  validity_days: number;
  features: string[];
  recommended: boolean;
  is_unlimited: boolean;
}

interface Purchase {
  id: number;
  package_name: string;
  price_paid: string;
  profile_limit: number;
  validity_days: number;
  purchased_at: string;
  expires_at: string;
  payment_method: string;
  transaction_id: string;
  status_label: 'active' | 'expired' | 'exhausted';
  is_active: boolean;
  unlocks_used: number;
  unlocks_remaining: number | null;
  has_capacity: boolean;
}

interface PublicCandidate {
  id: number;
  display_name: string;
  experience_tier: string | null;
  years_experience: number | null;
  location: string;
  skills: string[];
  scores: { resume: number; quiz: number; interview: number; final: number };
  interview_breakdown: { technical: number; personality: number; attentiveness: number; eye_contact: number } | null;
  published_at: string;
  unlocked: boolean;

  // Present only when unlocked:
  full_name?: string;
  email?: string;
  phone?: string;
  bio?: string;
  projects_summary?: string;
  website?: string;
  linkedin?: string;
  github?: string;
}

type Mode = 'loading' | 'library' | 'preview' | 'checkout' | 'unlocked' | 'batch' | 'batch-done';

interface BatchItem {
  candidate: PublicCandidate;
  alreadyUnlocked: boolean;
  result?: 'unlocked' | 'failed' | 'skipped';
}

// Format a price (string/number from the API) as Pakistani Rupees, e.g. "Rs 3,000".
function formatPKR(value: string | number): string {
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (!isFinite(n)) return 'Rs 0';
  return `Rs ${Math.round(n).toLocaleString('en-PK')}`;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function ProfileAccess() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { authFetch } = useAuth();

  const candidateId = searchParams.get('candidate');

  // Comma-separated list of candidate IDs for batch mode (?candidates=1,3,7)
  const candidatesParam = searchParams.get('candidates');
  const batchCandidateIds: number[] = React.useMemo(() => {
    if (!candidatesParam) return [];
    return Array.from(new Set(
      candidatesParam.split(',')
        .map(s => parseInt(s.trim(), 10))
        .filter(n => Number.isFinite(n) && n > 0)
    ));
  }, [candidatesParam]);

  const [mode, setMode] = useState<Mode>('loading');
  const [packages, setPackages] = useState<Package[]>([]);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [candidate, setCandidate] = useState<PublicCandidate | null>(null);
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null);
  const [selectedPackage, setSelectedPackage] = useState<string>('professional');
  const [submitting, setSubmitting] = useState(false);

  const selectedPkg = packages.find(p => p.slug === selectedPackage);

  const BANK_DETAILS = {
    accountTitle: 'WAYAL YASIN',
    bankName: 'Meezan Bank',
    accountNumber: '11590109438978',
    iban: 'PK75MEZN0011590109438978',
  };

  const WHATSAPP_NUMBER = '923164720474';

  const whatsappMessage = selectedPkg
    ? `Hello, I want to buy the ${selectedPkg.name} package on IntervAI Coach.
Package: ${selectedPkg.name}
Price: ${formatPKR(selectedPkg.price)}
I have transferred the payment. Please verify my screenshot and activate my package.`
    : 'Hello, I want to buy a package on IntervAI Coach.';

  const whatsappUrl = `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(whatsappMessage)}`;

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    async function init() {
      try {
        const [pkgRes, purchRes] = await Promise.all([
          authFetch(`${API_BASE_URL}/api/payments/packages/`),
          authFetch(`${API_BASE_URL}/api/payments/purchases/`),
        ]);

        if (pkgRes.ok) setPackages(await pkgRes.json());
        if (purchRes.ok) setPurchases(await purchRes.json());

        if (candidateId) {
          // Single-candidate flow
          const candRes = await authFetch(`${API_BASE_URL}/api/profiles/public/${candidateId}/`);
          if (!candRes.ok) {
            toast.error('Candidate profile not found.');
            navigate('/employer-dashboard');
            return;
          }
          const data: PublicCandidate = await candRes.json();
          setCandidate(data);
          setMode(data.unlocked ? 'unlocked' : 'preview');
        } else if (batchCandidateIds.length > 0) {
          // Batch flow — fetch each profile in parallel
          const results = await Promise.allSettled(
            batchCandidateIds.map(id =>
              authFetch(`${API_BASE_URL}/api/profiles/public/${id}/`)
                .then(r => r.ok ? r.json() : Promise.reject())
            )
          );

          const items: BatchItem[] = results
            .filter((r): r is PromiseFulfilledResult<PublicCandidate> => r.status === 'fulfilled')
            .map(r => ({
              candidate: r.value,
              alreadyUnlocked: !!r.value.unlocked,
            }));

          if (items.length === 0) {
            toast.error('None of the selected candidates could be loaded.');
            navigate('/employer-dashboard');
            return;
          }
          if (items.length < batchCandidateIds.length) {
            toast.warning(`${batchCandidateIds.length - items.length} candidate(s) could not be loaded.`);
          }
          setBatchItems(items);
          setMode('batch');
        } else {
          // Library/management view
          setMode('library');
        }
      } catch {
        toast.error('Failed to load. Please try again.');
        navigate('/employer-dashboard');
      }
    }
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId, candidatesParam]);

  // ── Active purchase helper ─────────────────────────────────────────────────
  const activePurchase = purchases.find(p => p.is_active && p.has_capacity);

  // ── Actions ────────────────────────────────────────────────────────────────
  const handleUnlock = async (cid: number) => {
    setSubmitting(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/payments/unlock/${cid}/`, { method: 'POST' });
      const data = await res.json();

      if (res.status === 402 || data.purchase_required) {
        toast.error('No active package — please purchase one first.');
        setMode('checkout');
        return;
      }
      if (!res.ok) { toast.error(data.error || 'Unlock failed.'); return; }

      toast.success(data.already_unlocked ? 'Already unlocked.' : 'Profile unlocked!');

      // Refresh candidate to get the unlocked fields
      const candRes = await authFetch(`${API_BASE_URL}/api/profiles/public/${cid}/`);
      if (candRes.ok) {
        setCandidate(await candRes.json());
        setMode('unlocked');
      }

      // Refresh purchases to reflect consumed slot
      const purchRes = await authFetch(`${API_BASE_URL}/api/payments/purchases/`);
      if (purchRes.ok) setPurchases(await purchRes.json());
    } catch {
      toast.error('Network error.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleBatchUnlock = async () => {
    // Filter out already-unlocked items
    const toUnlock = batchItems.filter(b => !b.alreadyUnlocked);
    if (toUnlock.length === 0) {
      toast.info('All selected candidates are already unlocked.');
      return;
    }

    // Check capacity before starting
    if (!activePurchase) {
      toast.error('No active package — purchase one first.');
      setMode('checkout');
      return;
    }
    const remaining = activePurchase.unlocks_remaining;
    if (remaining !== null && remaining < toUnlock.length) {
      toast.error(
        `Active package has ${remaining} unlock${remaining === 1 ? '' : 's'} left, ` +
        `but ${toUnlock.length} are needed. Buy a larger package or remove some candidates.`
      );
      return;
    }

    setSubmitting(true);
    setBatchProgress({ done: 0, total: toUnlock.length });

    // Unlock sequentially to keep slot accounting honest and toasts readable
    const updated = [...batchItems];
    let unlockedCount = 0;
    let failedCount = 0;

    for (let i = 0; i < toUnlock.length; i++) {
      const item = toUnlock[i];
      const idx = updated.findIndex(b => b.candidate.id === item.candidate.id);
      try {
        const res = await authFetch(
          `${API_BASE_URL}/api/payments/unlock/${item.candidate.id}/`,
          { method: 'POST' }
        );
        const data = await res.json();

        if (res.status === 402 || data.purchase_required) {
          // Mark this + remaining as skipped, break out
          updated[idx] = { ...updated[idx], result: 'skipped' };
          for (let j = i + 1; j < toUnlock.length; j++) {
            const k = updated.findIndex(b => b.candidate.id === toUnlock[j].candidate.id);
            if (k !== -1) updated[k] = { ...updated[k], result: 'skipped' };
          }
          toast.error('Ran out of unlock capacity.');
          break;
        }

        if (res.ok) {
          updated[idx] = { ...updated[idx], result: 'unlocked' };
          unlockedCount++;
        } else {
          updated[idx] = { ...updated[idx], result: 'failed' };
          failedCount++;
        }
      } catch {
        updated[idx] = { ...updated[idx], result: 'failed' };
        failedCount++;
      }
      setBatchProgress({ done: i + 1, total: toUnlock.length });
    }

    setBatchItems(updated);

    // Refresh purchases to reflect consumed slots
    try {
      const purchRes = await authFetch(`${API_BASE_URL}/api/payments/purchases/`);
      if (purchRes.ok) setPurchases(await purchRes.json());
    } catch { /* non-fatal */ }

    if (unlockedCount > 0) toast.success(`Unlocked ${unlockedCount} profile${unlockedCount === 1 ? '' : 's'}.`);
    if (failedCount > 0) toast.error(`${failedCount} unlock${failedCount === 1 ? '' : 's'} failed.`);

    setSubmitting(false);
    setMode('batch-done');
  };

  const handleDownloadReport = () => {
    if (!candidate || !candidate.unlocked) {
      toast.error('Please unlock this profile first.');
      return;
    }

    const value = (v: string | number | null | undefined) =>
      v === null || v === undefined || v === '' ? 'N/A' : String(v);

    const doc = new jsPDF();

    let y = 15;

    const addTitle = (text: string) => {
      doc.setFontSize(18);
      doc.setFont('helvetica', 'bold');
      doc.text(text, 14, y);
      y += 12;
    };

    const addSection = (title: string) => {
      y += 5;
      doc.setFontSize(13);
      doc.setFont('helvetica', 'bold');
      doc.text(title, 14, y);
      y += 7;
    };

    const addLine = (label: string, text: string | number | null | undefined) => {
      doc.setFontSize(10);
      doc.setFont('helvetica', 'normal');

      const line = `${label}: ${value(text)}`;
      const wrapped = doc.splitTextToSize(line, 180);

      if (y + wrapped.length * 6 > 280) {
        doc.addPage();
        y = 15;
      }

      doc.text(wrapped, 14, y);
      y += wrapped.length * 6;
    };

    const addParagraph = (text: string | null | undefined) => {
      doc.setFontSize(10);
      doc.setFont('helvetica', 'normal');

      const wrapped = doc.splitTextToSize(value(text), 180);

      wrapped.forEach((line: string) => {
        if (y > 280) {
          doc.addPage();
          y = 15;
        }
        doc.text(line, 14, y);
        y += 6;
      });
    };

    addTitle('IntervAI Coach - Candidate Profile');

    addSection('Basic Information');
    addLine('Name', candidate.full_name ?? candidate.display_name);
    addLine('Email', candidate.email);
    addLine('Phone', candidate.phone);
    addLine('Location', candidate.location);

    addSection('Experience');
    addLine('Experience', getExperienceDisplay(candidate.years_experience, candidate.experience_tier));

    addSection('Skills');
    addParagraph(candidate.skills.length > 0 ? candidate.skills.join(', ') : 'N/A');

    addSection('Assessment Scores');
    addLine('Resume Score', `${value(candidate.scores.resume)}%`);
    addLine('Quiz Score', `${value(candidate.scores.quiz)}%`);
    addLine('Interview Score', `${value(candidate.scores.interview)}%`);
    addLine('Final Score', `${value(candidate.scores.final)}%`);

    addSection('Interview Breakdown');
    addLine('Technical', `${value(candidate.interview_breakdown?.technical)}%`);
    addLine('Behavioural', `${value(candidate.interview_breakdown?.personality)}%`);
    addLine('Attentiveness', `${value(candidate.interview_breakdown?.attentiveness)}%`);
    addLine('Eye Contact', `${value(candidate.interview_breakdown?.eye_contact)}%`);

    addSection('About');
    addParagraph(candidate.bio);

    addSection('Projects & Experience');
    addParagraph(candidate.projects_summary);

    addSection('Links');
    addLine('Website', candidate.website);
    addLine('LinkedIn', candidate.linkedin);
    addLine('GitHub', candidate.github);

    doc.save(`candidate-profile-${candidate.id}.pdf`);

    toast.success('Candidate profile downloaded as PDF.');
  };

  // ── Loading ────────────────────────────────────────────────────────────────
  if (mode === 'loading') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="w-12 h-12 text-blue-600 animate-spin mx-auto" />
          <p className="text-gray-600 font-medium">Loading…</p>
        </div>
      </div>
    );
  }

  // ── Header (shared) ────────────────────────────────────────────────────────
  const Header: React.FC<{ title: string; subtitle: string; success?: boolean }> = ({ title, subtitle, success }) => (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/employer-dashboard')}>
          <ArrowLeft className="w-4 h-4 mr-2" />Back to Dashboard
        </Button>
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${success
            ? 'bg-gradient-to-br from-green-600 to-emerald-600'
            : 'bg-gradient-to-br from-blue-600 to-purple-600'}`}>
            {success ? <CheckCircle2 className="w-6 h-6 text-white" /> : <Briefcase className="w-6 h-6 text-white" />}
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{title}</h1>
            <p className="text-sm text-gray-600">{subtitle}</p>
          </div>
        </div>
      </div>
    </header>
  );

  // ── Unlocked candidate view ────────────────────────────────────────────────
  if (mode === 'unlocked' && candidate) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
        <Header title="Profile Unlocked" subtitle="Full access granted" success />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
          <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
            <Card className="border-0 shadow-2xl overflow-hidden">
              <div className="bg-gradient-to-r from-green-600 to-emerald-600 text-white p-6 text-center">
                <CheckCircle2 className="w-16 h-16 mx-auto mb-3" />
                <h2 className="text-3xl font-bold mb-1">Profile Unlocked</h2>
                <p className="text-green-100">You have full access to this candidate's information</p>
              </div>
            </Card>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <Card className="border-0 shadow-2xl">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Candidate Profile</CardTitle>
                  <Button variant="outline" onClick={handleDownloadReport}>
                    <Download className="w-4 h-4 mr-2" />Download Report
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Identity */}
                <div className="flex items-start gap-6 pb-6 border-b">
                  <div className="w-24 h-24 bg-gradient-to-br from-blue-600 to-purple-600 rounded-full flex items-center justify-center text-white text-3xl font-bold flex-shrink-0">
                    {(candidate.full_name ?? candidate.display_name).charAt(0)}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-2xl font-bold text-gray-900 mb-2">
                      {candidate.full_name ?? candidate.display_name}
                    </h3>
                    <div className="flex flex-wrap gap-2 mb-4">
                      {candidate.years_experience != null && (
                        <Badge className="bg-blue-100 text-blue-700">
                          {getExperienceDisplay(candidate.years_experience, candidate.experience_tier)}
                        </Badge>
                      )}
                      <Badge className="bg-green-100 text-green-700">Final Score: {candidate.scores.final}%</Badge>
                    </div>
                    <div className="grid md:grid-cols-2 gap-3 text-sm text-gray-700">
                      {candidate.email && <div className="flex items-center gap-2"><Mail className="w-4 h-4 text-gray-400" />{candidate.email}</div>}
                      {candidate.phone && <div className="flex items-center gap-2"><Phone className="w-4 h-4 text-gray-400" />{candidate.phone}</div>}
                      {candidate.location && <div className="flex items-center gap-2"><MapPin className="w-4 h-4 text-gray-400" />{candidate.location}</div>}
                    </div>
                  </div>
                </div>

                {/* Bio */}
                {candidate.bio && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-2 flex items-center gap-2"><User className="w-4 h-4" />About</h4>
                    <p className="text-gray-700 text-sm whitespace-pre-line">{candidate.bio}</p>
                  </div>
                )}

                {/* Skills */}
                <div>
                  <h4 className="font-semibold text-gray-900 mb-2 flex items-center gap-2"><Code className="w-4 h-4" />Technical Skills</h4>
                  <div className="flex flex-wrap gap-2">
                    {candidate.skills.map(s => <Badge key={s} variant="outline">{s}</Badge>)}
                  </div>
                </div>

                {/* Scores */}
                <div>
                  <h4 className="font-semibold text-gray-900 mb-3 flex items-center gap-2"><Award className="w-4 h-4" />AI Assessment Scores</h4>
                  <div className="grid grid-cols-3 gap-4">
                    {[
                      { label: 'Resume', value: candidate.scores.resume, bg: 'bg-blue-50', text: 'text-blue-600' },
                      { label: 'Quiz', value: candidate.scores.quiz, bg: 'bg-purple-50', text: 'text-purple-600' },
                      { label: 'Interview', value: candidate.scores.interview, bg: 'bg-pink-50', text: 'text-pink-600' },
                    ].map(({ label, value, bg, text }) => (
                      <div key={label} className={`text-center p-3 ${bg} rounded-lg`}>
                        <div className={`text-2xl font-bold ${text}`}>{value}%</div>
                        <div className="text-xs text-gray-600">{label}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Interview breakdown */}
                {candidate.interview_breakdown && (
                  <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                    <h5 className="font-semibold text-green-900 mb-3 flex items-center gap-2">
                      <Star className="w-4 h-4" />Verified Interview Performance
                    </h5>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {[
                        ['Technical', candidate.interview_breakdown.technical],
                        ['Behavioural', candidate.interview_breakdown.personality],
                        ['Attentiveness', candidate.interview_breakdown.attentiveness],
                        ['Eye Contact', candidate.interview_breakdown.eye_contact],
                      ].map(([label, val]) => (
                        <div key={label as string} className="text-center bg-white rounded p-2">
                          <div className="text-lg font-bold text-green-700">{val}%</div>
                          <div className="text-xs text-gray-600">{label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Projects */}
                {candidate.projects_summary && (
                  <div>
                    <h4 className="font-semibold text-gray-900 mb-2 flex items-center gap-2"><Briefcase className="w-4 h-4" />Projects & Experience</h4>
                    <p className="text-gray-700 text-sm whitespace-pre-line">{candidate.projects_summary}</p>
                  </div>
                )}

                {/* Social */}
                {(candidate.website || candidate.linkedin || candidate.github) && (
                  <div className="pt-4 border-t flex flex-wrap gap-3">
                    {candidate.website && <Button asChild variant="outline" size="sm"><a href={candidate.website} target="_blank" rel="noopener noreferrer"><Globe className="w-4 h-4 mr-2" />Website</a></Button>}
                    {candidate.linkedin && <Button asChild variant="outline" size="sm"><a href={candidate.linkedin} target="_blank" rel="noopener noreferrer"><Linkedin className="w-4 h-4 mr-2" />LinkedIn</a></Button>}
                    {candidate.github && <Button asChild variant="outline" size="sm"><a href={candidate.github} target="_blank" rel="noopener noreferrer"><Github className="w-4 h-4 mr-2" />GitHub</a></Button>}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </div>
    );
  }

  // ── Preview mode (candidate locked, decide whether to unlock or checkout) ──
  if (mode === 'preview' && candidate) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
        <Header title="Unlock Candidate" subtitle={candidate.display_name} />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 grid lg:grid-cols-3 gap-6">
          {/* Locked preview */}
          <div className="lg:col-span-2">
            <Card className="border-0 shadow-2xl">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Lock className="w-5 h-5 text-orange-600" />
                  <CardTitle>Profile Preview (Locked)</CardTitle>
                </div>
                <CardDescription>Public info shown. Name, contact, bio and projects unlock after purchase.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-start gap-4">
                  <div className="w-20 h-20 bg-gray-200 rounded-full flex items-center justify-center">
                    <User className="w-10 h-10 text-gray-400" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-bold text-gray-900 mb-2">{candidate.display_name}</h3>
                    <div className="flex flex-wrap gap-2">
                      {candidate.years_experience != null && (
                        <Badge className="bg-blue-100 text-blue-700">
                          {getExperienceDisplay(candidate.years_experience, candidate.experience_tier)}
                        </Badge>
                      )}
                      <Badge className="bg-green-100 text-green-700">Score: {candidate.scores.final}%</Badge>
                    </div>
                  </div>
                </div>

                <div>
                  <Label className="text-xs uppercase tracking-wide text-gray-500">Skills</Label>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {candidate.skills.map(s => <Badge key={s} variant="outline">{s}</Badge>)}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center p-3 bg-blue-50 rounded-lg">
                    <div className="text-2xl font-bold text-blue-600">{candidate.scores.resume}%</div>
                    <div className="text-xs text-gray-600">Resume</div>
                  </div>
                  <div className="text-center p-3 bg-purple-50 rounded-lg">
                    <div className="text-2xl font-bold text-purple-600">{candidate.scores.quiz}%</div>
                    <div className="text-xs text-gray-600">Quiz</div>
                  </div>
                  <div className="text-center p-3 bg-pink-50 rounded-lg">
                    <div className="text-2xl font-bold text-pink-600">{candidate.scores.interview}%</div>
                    <div className="text-xs text-gray-600">Interview</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Unlock panel */}
          <div className="lg:col-span-1 space-y-4">
            {activePurchase ? (
              <Card className="border-0 shadow-2xl">
                <CardHeader>
                  <CardTitle className="text-lg">Use Active Package</CardTitle>
                  <CardDescription>{activePurchase.package_name}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="text-sm space-y-1">
                    <p>Unlocks remaining: <strong>
                      {activePurchase.unlocks_remaining === null ? 'Unlimited' : activePurchase.unlocks_remaining}
                    </strong></p>
                    <p>Expires: <strong>{new Date(activePurchase.expires_at).toLocaleDateString()}</strong></p>
                  </div>
                  <Button className="w-full" onClick={() => handleUnlock(candidate.id)} disabled={submitting}>
                    {submitting ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Unlocking…</>
                      : <>Unlock This Profile</>}
                  </Button>
                  <Button variant="outline" className="w-full" size="sm" onClick={() => setMode('checkout')}>
                    Buy Additional Package
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <Card className="border-0 shadow-2xl">
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-5 h-5 text-orange-600" />
                    <CardTitle className="text-lg">No Active Package</CardTitle>
                  </div>
                  <CardDescription>Purchase a package to unlock this profile</CardDescription>
                </CardHeader>
                <CardContent>
                  <Button className="w-full" onClick={() => setMode('checkout')}>
                    Choose a Package
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Library mode (no candidate in URL) ─────────────────────────────────────
  if (mode === 'library') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
        <Header title="Your Packages" subtitle="Manage purchases and browse candidates" />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
          {/* Package activation confirmation */}
          {activePurchase && (
            <Card className="mb-6 border-emerald-200 bg-emerald-50">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5" />
                  <div>
                    <h3 className="font-semibold text-emerald-800">
                      Package Activated
                    </h3>
                    <p className="text-sm text-emerald-700">
                      Your {activePurchase.package_name} package has been verified and activated successfully.
                      You can now unlock candidate profiles.
                    </p>

                    <div className="mt-3 text-sm text-emerald-700">
                      <p>
                        Unlocks remaining:{' '}
                        <strong>
                          {activePurchase.unlocks_remaining === null
                            ? 'Unlimited'
                            : activePurchase.unlocks_remaining}
                        </strong>
                      </p>
                      <p>
                        Expires:{' '}
                        <strong>{new Date(activePurchase.expires_at).toLocaleDateString()}</strong>
                      </p>
                    </div>

                    <Button
                      className="mt-4"
                      size="sm"
                      onClick={() => navigate('/employer-dashboard')}
                    >
                      Browse Candidates
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Purchase history */}
          <Card className="border-0 shadow-lg">
            <CardHeader>
              <CardTitle>Purchase History</CardTitle>
              <CardDescription>All your packages, active and past</CardDescription>
            </CardHeader>
            <CardContent>
              {purchases.length === 0 ? (
                <div className="text-center py-12 space-y-3">
                  <ShoppingBag className="w-12 h-12 text-gray-300 mx-auto" />
                  <p className="text-gray-500">You haven't purchased any packages yet.</p>
                  <Button onClick={() => setMode('checkout')}>Buy Your First Package</Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {purchases.map(p => (
                    <div key={p.id} className="border rounded-lg p-4 flex items-center justify-between gap-4 flex-wrap">
                      <div className="flex-1 min-w-[200px]">
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="font-semibold">{p.package_name}</h4>
                          <Badge className={
                            p.status_label === 'active' ? 'bg-green-100 text-green-700' :
                              p.status_label === 'expired' ? 'bg-gray-100 text-gray-600' :
                                'bg-orange-100 text-orange-700'
                          }>
                            {p.status_label}
                          </Badge>
                        </div>
                        <div className="text-xs text-gray-600 space-y-0.5">
                          <p className="flex items-center gap-1"><Hash className="w-3 h-3" />{p.transaction_id}</p>
                          <p className="flex items-center gap-1"><Calendar className="w-3 h-3" />Purchased {new Date(p.purchased_at).toLocaleDateString()} · Expires {new Date(p.expires_at).toLocaleDateString()}</p>
                          <p>Unlocks: {p.unlocks_used} / {p.profile_limit === 0 ? '∞' : p.profile_limit}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-2xl font-bold text-gray-900">{formatPKR(p.price_paid)}</p>
                        <p className="text-xs text-gray-500">{p.payment_method}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex justify-center">
            <Button size="lg" onClick={() => setMode('checkout')}>
              Buy {purchases.length > 0 ? 'Another' : 'a'} Package
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ── Batch unlock mode ──────────────────────────────────────────────────────
  if (mode === 'batch' || mode === 'batch-done') {
    const lockedItems = batchItems.filter(b => !b.alreadyUnlocked);
    const unlockedItems = batchItems.filter(b => b.alreadyUnlocked);
    const needed = lockedItems.length;
    const remaining = activePurchase?.unlocks_remaining; // null = unlimited
    const hasCapacity = !activePurchase
      ? false
      : activePurchase.unlocks_remaining === null || activePurchase.unlocks_remaining >= needed;

    const successCount = batchItems.filter(b => b.result === 'unlocked').length;
    const failedCount = batchItems.filter(b => b.result === 'failed').length;
    const skippedCount = batchItems.filter(b => b.result === 'skipped').length;

    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
        <Header
          title={mode === 'batch-done' ? 'Unlock Complete' : 'Unlock Selected Candidates'}
          subtitle={mode === 'batch-done'
            ? `${successCount} unlocked${failedCount ? `, ${failedCount} failed` : ''}${skippedCount ? `, ${skippedCount} skipped` : ''}`
            : `${batchItems.length} candidate${batchItems.length === 1 ? '' : 's'} selected`}
          success={mode === 'batch-done' && successCount > 0}
        />

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
          {/* Capacity summary */}
          <Card className="border-0 shadow-lg">
            <CardContent className="pt-6">
              <div className="grid sm:grid-cols-4 gap-4 text-center">
                <div className="p-3 bg-blue-50 rounded-lg">
                  <div className="text-2xl font-bold text-blue-600">{batchItems.length}</div>
                  <div className="text-xs text-gray-600">Selected</div>
                </div>
                <div className="p-3 bg-green-50 rounded-lg">
                  <div className="text-2xl font-bold text-green-600">{unlockedItems.length}</div>
                  <div className="text-xs text-gray-600">Already Unlocked</div>
                </div>
                <div className="p-3 bg-orange-50 rounded-lg">
                  <div className="text-2xl font-bold text-orange-600">{needed}</div>
                  <div className="text-xs text-gray-600">To Unlock</div>
                </div>
                <div className={`p-3 rounded-lg ${hasCapacity ? 'bg-purple-50' : 'bg-red-50'}`}>
                  <div className={`text-2xl font-bold ${hasCapacity ? 'text-purple-600' : 'text-red-600'}`}>
                    {remaining === null ? '∞' : (remaining ?? 0)}
                  </div>
                  <div className="text-xs text-gray-600">Slots Available</div>
                </div>
              </div>

              {mode === 'batch' && needed > 0 && (
                <div className={`mt-4 p-3 rounded-lg border flex items-start gap-3 text-sm ${hasCapacity ? 'bg-green-50 border-green-200 text-green-800'
                  : 'bg-red-50 border-red-200 text-red-800'
                  }`}>
                  {hasCapacity ? <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    : <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />}
                  <div>
                    {hasCapacity ? (
                      <>You have enough unlock capacity. Click <strong>Unlock All</strong> to proceed.</>
                    ) : !activePurchase ? (
                      <>No active package. Purchase one to unlock these candidates.</>
                    ) : (
                      <>Active package has only {remaining} slot{remaining === 1 ? '' : 's'} but {needed} are needed. Buy an additional package or remove candidates.</>
                    )}
                  </div>
                </div>
              )}

              {mode === 'batch' && (
                <div className="mt-4 flex flex-wrap gap-3 justify-end">
                  <Button variant="outline" onClick={() => navigate('/employer-dashboard')}>
                    Back to Dashboard
                  </Button>
                  {!activePurchase || !hasCapacity ? (
                    <Button onClick={() => setMode('checkout')}>Buy a Package</Button>
                  ) : (
                    <Button onClick={handleBatchUnlock} disabled={submitting || needed === 0}>
                      {submitting && batchProgress
                        ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Unlocking {batchProgress.done}/{batchProgress.total}…</>
                        : needed === 0
                          ? 'Nothing to Unlock'
                          : `Unlock All (${needed})`}
                    </Button>
                  )}
                </div>
              )}

              {mode === 'batch-done' && (
                <div className="mt-4 flex flex-wrap gap-3 justify-end">
                  <Button variant="outline" onClick={() => navigate('/employer-dashboard')}>
                    Back to Dashboard
                  </Button>
                  {/* <Button onClick={() => setMode('library')}>View Library</Button> */}
                  <Button onClick={() => navigate('/employer-dashboard#purchased-profiles')}>
                    View Purchased Profiles
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Candidate cards */}
          <div className="space-y-3">
            {batchItems.map(item => {
              const c = item.candidate;
              const statusBadge = () => {
                if (item.result === 'unlocked') return <Badge className="bg-green-100 text-green-700">Unlocked just now</Badge>;
                if (item.result === 'failed') return <Badge className="bg-red-100 text-red-700">Failed</Badge>;
                if (item.result === 'skipped') return <Badge className="bg-gray-100 text-gray-600">Skipped</Badge>;
                if (item.alreadyUnlocked) return <Badge className="bg-green-100 text-green-700">Already unlocked</Badge>;
                return <Badge className="bg-orange-100 text-orange-700"><Lock className="w-3 h-3 mr-1" />Will use 1 slot</Badge>;
              };

              return (
                <Card key={c.id} className="border-0 shadow">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-center justify-between gap-4 flex-wrap">
                      <div className="flex-1 min-w-[200px]">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <h4 className="font-semibold text-gray-900">
                            {c.full_name ?? c.display_name}
                          </h4>
                          {statusBadge()}
                        </div>
                        <div className="flex flex-wrap gap-1 items-center text-xs text-gray-600">
                          {c.years_experience != null && (
                            <span>{getExperienceDisplay(c.years_experience, c.experience_tier)}</span>
                          )}
                          {c.years_experience != null && c.location && <span>·</span>}
                          {c.location && <span>{c.location}</span>}
                          <span>·</span>
                          <span>Final score: <strong className="text-gray-900">{c.scores.final}%</strong></span>
                        </div>
                        {c.skills.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {c.skills.slice(0, 5).map(s => (
                              <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                            ))}
                            {c.skills.length > 5 && (
                              <Badge variant="outline" className="text-xs">+{c.skills.length - 5}</Badge>
                            )}
                          </div>
                        )}
                      </div>

                      {(item.alreadyUnlocked || item.result === 'unlocked') && (
                        <Button variant="outline" size="sm" onClick={() => navigate(`/profile-access?candidate=${c.id}`)}>
                          <Eye className="w-4 h-4 mr-2" />View
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ── Checkout mode ──────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <Header title="Buy a Package" subtitle="Bank transfer payment" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activePurchase && (
          <Card className="mb-6 border-emerald-200 bg-emerald-50">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-emerald-800">
                    Package Activated
                  </h3>
                  <p className="text-sm text-emerald-700">
                    Your {activePurchase.package_name} package has been verified and activated successfully.
                    You can now unlock candidate profiles.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Packages */}
          <div className="lg:col-span-2 space-y-4">
            <h2 className="text-lg font-bold text-gray-900">Choose a Package</h2>
            <div className="grid sm:grid-cols-1 gap-4">
              {packages.map(pkg => (
                <motion.div key={pkg.id} whileHover={{ scale: 1.01 }}>
                  <Card
                    className={`border-0 shadow-lg cursor-pointer transition-all ${selectedPackage === pkg.slug ? 'ring-2 ring-blue-500' : ''
                      }`}
                    onClick={() => setSelectedPackage(pkg.slug)}
                  >
                    <CardContent className="pt-6">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <h3 className="text-lg font-bold">{pkg.name}</h3>
                            {pkg.recommended && <Badge className="bg-blue-100 text-blue-700">Recommended</Badge>}
                          </div>
                          <ul className="space-y-1 text-sm text-gray-600">
                            {pkg.features.map(f => (
                              <li key={f} className="flex items-start gap-2">
                                <Check className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" />
                                <span>{f}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="text-right">
                          <p className="text-3xl font-bold text-gray-900">{formatPKR(pkg.price)}</p>
                          <p className="text-xs text-gray-500">{pkg.validity_days} days</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Bank transfer instructions */}
          <div className="lg:col-span-1">
            <Card className="border-0 shadow-2xl sticky top-24">
              <CardHeader>
                <CardTitle>Payment Instructions</CardTitle>
                <CardDescription>
                  Transfer payment to given bank account, then send your payment screenshot on WhatsApp for verification.
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4">
                {selectedPkg && (
                  <div className="space-y-2 text-sm bg-blue-50 border border-blue-100 rounded-lg p-4">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Selected Package:</span>
                      <span className="font-medium">{selectedPkg.name}</span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-gray-600">Validity:</span>
                      <span className="font-medium">{selectedPkg.validity_days} days</span>
                    </div>

                    <div className="flex justify-between text-lg pt-2 border-t border-blue-100">
                      <span className="font-bold">Amount:</span>
                      <span className="font-bold">{formatPKR(selectedPkg.price)}</span>
                    </div>
                  </div>
                )}

                <div className="space-y-3 text-sm border rounded-lg p-4">
                  <h4 className="font-semibold text-gray-900">Bank Account Details</h4>

                  <div>
                    <p className="text-gray-500">Account Title</p>
                    <p className="font-medium">{BANK_DETAILS.accountTitle}</p>
                  </div>

                  <div>
                    <p className="text-gray-500">Bank Name</p>
                    <p className="font-medium">{BANK_DETAILS.bankName}</p>
                  </div>

                  <div>
                    <p className="text-gray-500">Account Number</p>
                    <p className="font-medium">{BANK_DETAILS.accountNumber}</p>
                  </div>

                  <div>
                    <p className="text-gray-500">IBAN</p>
                    <p className="font-medium break-all">{BANK_DETAILS.iban}</p>
                  </div>
                </div>

                <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 text-sm text-orange-800">
                  <p className="font-semibold mb-1">Important</p>
                  <p>
                    After sending the payment screenshot, our team will verify and activate your package within a few hours.
                  </p>
                </div>

                <Button asChild className="w-full" size="lg" disabled={!selectedPkg}>
                  <a href={whatsappUrl} target="_blank" rel="noopener noreferrer">
                    Send Screenshot on WhatsApp
                  </a>
                </Button>

                {candidateId && (
                  <p className="text-xs text-center text-gray-500">
                    After your package is activated, return here to unlock Candidate #{candidateId}.
                  </p>
                )}

                {batchCandidateIds.length > 0 && !candidateId && (
                  <p className="text-xs text-center text-gray-500">
                    After your package is activated, return here to unlock your selected candidates.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
