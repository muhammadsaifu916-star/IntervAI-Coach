import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { motion } from 'motion/react';
import {
  Search, Filter, Award, Code, Briefcase, LogOut, Eye, Star,
  TrendingUp, Users, ShoppingCart, Loader2, MapPin, Lock, Unlock,
  ChevronDown, ChevronRight, ArrowUpDown, Mail, Phone, CheckCircle2,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '../components/ui/table';
import { Switch } from '../components/ui/switch';
import { Label } from '../components/ui/label';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { API_BASE_URL } from '../config';
import { getExperienceDisplay, EXPERIENCE_TIER_DISPLAY } from '../utils/experienceDisplay';

// ── Types matching backend PublicProfileSerializer ────────────────────────────
interface PublicCandidate {
  id: number;
  display_name: string;
  experience_tier: string | null;
  years_experience: number | null;
  location: string;
  skills: string[];
  scores: {
    resume: number;
    quiz: number;
    interview: number;
    final: number;
  };
  interview_breakdown: {
    technical: number;
    personality: number;
    attentiveness: number;
    eye_contact: number;
  } | null;
  published_at: string;
  unlocked: boolean;

  // Present only when unlocked (injected server-side):
  full_name?: string;
  email?: string;
  phone?: string;
  bio?: string;
  projects_summary?: string;
  website?: string;
  linkedin?: string;
  github?: string;
}

interface DashboardStats {
  total: number;
  avg_score: number;
  top_rated: number;
}

type SortKey = 'score_desc' | 'score_asc' | 'recent' | 'experience';

const EXPERIENCE_TIERS = [
  'Entry Level',
  'Mid Level',
  'Senior Level',
];

const PAGE_SIZE = 8;

// ── Cart persistence (per-employer) ───────────────────────────────────────────
const cartKey = (employerId: number | undefined) => `intervai:employer-cart:${employerId ?? 'anon'}`;

function loadCart(employerId: number | undefined): number[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(cartKey(employerId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(n => typeof n === 'number') : [];
  } catch {
    return [];
  }
}

function saveCart(employerId: number | undefined, ids: number[]) {
  if (typeof window === 'undefined') return;
  try { localStorage.setItem(cartKey(employerId), JSON.stringify(ids)); } catch { /* quota etc */ }
}

// Debounce helper
function useDebounced<T>(value: T, delay = 400): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

function scoreBadgeClass(score: number): string {
  if (score >= 90) return 'bg-green-100 text-green-700';
  if (score >= 80) return 'bg-yellow-100 text-yellow-700';
  return 'bg-gray-100 text-gray-700';
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function EmployerDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout, authFetch } = useAuth();

  // Active tab — driven by URL hash when present
  const [activeTab, setActiveTab] = useState(() =>
    location.hash === '#purchased-profiles' ? 'purchased' : 'browse'
  );

  useEffect(() => {
    if (location.hash === '#purchased-profiles') {
      setActiveTab('purchased');
      // Clean up the hash so a later manual tab switch isn't overridden
      window.history.replaceState(null, '', location.pathname + location.search);
    }
  }, [location.hash, location.pathname, location.search]);

  const [candidates, setCandidates] = useState<PublicCandidate[]>([]);
  const [stats, setStats] = useState<DashboardStats>({ total: 0, avg_score: 0, top_rated: 0 });
  const [loading, setLoading] = useState(true);

  // Purchased / unlocked profiles (fetched unfiltered so filters never hide them)
  const [purchased, setPurchased] = useState<PublicCandidate[]>([]);
  const [purchasedLoading, setPurchasedLoading] = useState(true);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [experienceFilter, setExperienceFilter] = useState('all');
  const [minScore, setMinScore] = useState('0');
  const [sortKey, setSortKey] = useState<SortKey>('score_desc');
  const [hidePurchased, setHidePurchased] = useState(true);

  // Table paging + row expansion
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  // Cart (selected for purchase) — persisted in localStorage per employer
  const [selectedCandidates, setSelectedCandidates] = useState<number[]>([]);

  const employerId = user?.user_id;

  useEffect(() => {
    if (employerId) setSelectedCandidates(loadCart(Number(employerId)));
  }, [employerId]);

  useEffect(() => {
    if (employerId) saveCart(Number(employerId), selectedCandidates);
  }, [employerId, selectedCandidates]);

  const debouncedSearch = useDebounced(searchQuery);

  // ── Fetch candidates whenever filters change ─────────────────────────────
  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (debouncedSearch.trim()) params.set('search', debouncedSearch.trim());
      if (experienceFilter !== 'all') params.set('experience_tier', experienceFilter);
      if (minScore !== '0') params.set('min_score', minScore);

      const res = await authFetch(`${API_BASE_URL}/api/profiles/public/?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to load candidates.');
      const data = await res.json();
      setCandidates(data.results ?? []);
      setStats(data.stats ?? { total: 0, avg_score: 0, top_rated: 0 });
    } catch {
      toast.error('Could not load candidates.');
    } finally {
      setLoading(false);
    }
  }, [authFetch, debouncedSearch, experienceFilter, minScore]);

  useEffect(() => { fetchCandidates(); }, [fetchCandidates]);

  // Reset paging whenever the filtered/sorted result set changes
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [debouncedSearch, experienceFilter, minScore, sortKey, hidePurchased]);

  // ── Fetch purchased (unlocked) profiles — unfiltered ─────────────────────
  const fetchPurchased = useCallback(async () => {
    setPurchasedLoading(true);
    try {
      const res = await authFetch(`${API_BASE_URL}/api/profiles/public/`);
      if (!res.ok) throw new Error('Failed to load purchased profiles.');
      const data = await res.json();
      const all: PublicCandidate[] = data.results ?? [];
      setPurchased(all.filter(c => c.unlocked));
    } catch {
      // Non-fatal — the browse tab still works
    } finally {
      setPurchasedLoading(false);
    }
  }, [authFetch]);

  useEffect(() => { fetchPurchased(); }, [fetchPurchased]);

  // A cart only holds things you intend to buy — drop any candidate you already own.
  useEffect(() => {
    if (purchased.length === 0) return;
    const ownedIds = new Set(purchased.map(p => p.id));
    setSelectedCandidates(prev => {
      const next = prev.filter(id => !ownedIds.has(id));
      return next.length === prev.length ? prev : next;
    });
  }, [purchased]);

  const handleLogout = () => { logout(); navigate('/'); };

  const toggleSelection = (id: number) => {
    // Guard: owned candidates can never enter the cart.
    if (purchased.some(p => p.id === id)) return;
    setSelectedCandidates(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);
  };

  const toggleExpand = (id: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleViewProfile = (candidateId: number) =>
    navigate(`/profile-access?candidate=${candidateId}`);

  const handleViewCart = () => {
    if (selectedCandidates.length === 0) {
      navigate('/profile-access');
      return;
    }
    navigate(`/profile-access?candidates=${selectedCandidates.join(',')}`);
  };

  const clearCart = () => setSelectedCandidates([]);

  // ── Sorting (client-side, on top of the server's filtered list) ───────────
  const sortedCandidates = useMemo(() => {
    // Browse is a discovery surface. By default we hide already-purchased
    // candidates (they live in the Purchased tab); the toggle can show them.
    const arr = hidePurchased ? candidates.filter(c => !c.unlocked) : [...candidates];
    switch (sortKey) {
      case 'score_asc':
        arr.sort((a, b) => a.scores.final - b.scores.final);
        break;
      case 'recent':
        arr.sort((a, b) => +new Date(b.published_at) - +new Date(a.published_at));
        break;
      case 'experience':
        arr.sort((a, b) => (b.years_experience ?? -1) - (a.years_experience ?? -1));
        break;
      case 'score_desc':
      default:
        arr.sort((a, b) => b.scores.final - a.scores.final);
        break;
    }
    return arr;
  }, [candidates, sortKey, hidePurchased]);

  const visibleCandidates = sortedCandidates.slice(0, visibleCount);
  const hasMore = visibleCount < sortedCandidates.length;

  const statColorClasses: Record<string, { bg: string; text: string }> = {
    blue: { bg: 'bg-blue-100', text: 'text-blue-600' },
    purple: { bg: 'bg-purple-100', text: 'text-purple-600' },
    green: { bg: 'bg-green-100', text: 'text-green-600' },
    orange: { bg: 'bg-orange-100', text: 'text-orange-600' },
  };

  const purchasedCount = purchased.length;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <Briefcase className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">Employer Dashboard</h1>
                <p className="text-sm text-gray-600">Find verified talent</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right hidden sm:block">
                <p className="text-sm font-medium text-gray-900">{user?.full_name}</p>
                <p className="text-xs text-gray-600">{user?.email}</p>
              </div>
              <Button variant="outline" size="sm" onClick={handleViewCart}>
                <ShoppingCart className="w-4 h-4 mr-2" />
                Cart ({selectedCandidates.length})
              </Button>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                <LogOut className="w-4 h-4 mr-2" />Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Stats Overview */}
        <div className="grid md:grid-cols-4 gap-6 mb-8">
          {[
            { label: 'Candidates', value: stats.total, icon: Users, color: 'blue' },
            { label: 'Avg Score', value: `${stats.avg_score}%`, icon: TrendingUp, color: 'purple' },
            { label: 'Purchased', value: purchasedCount, icon: Unlock, color: 'green' },
            { label: 'In Cart', value: selectedCandidates.length, icon: ShoppingCart, color: 'orange' },
          ].map(({ label, value, icon: Icon, color }, i) => {
            const colorClass = statColorClasses[color];

            return (
              <motion.div
                key={label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 * (i + 1) }}
              >
                <Card className="border-0 shadow-lg">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-600">{label}</p>
                        <p className="text-3xl font-bold text-gray-900">{value}</p>
                      </div>

                      <div className={`w-12 h-12 ${colorClass.bg} rounded-lg flex items-center justify-center`}>
                        <Icon className={`w-6 h-6 ${colorClass.text}`} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>

        {/* Tabs: Browse vs Purchased */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}>
          <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
            <TabsList>
              <TabsTrigger value="browse">
                <Users className="w-4 h-4 mr-2" />Browse Candidates
              </TabsTrigger>
              <TabsTrigger value="purchased">
                <Unlock className="w-4 h-4 mr-2" />
                Purchased{purchasedCount > 0 ? ` (${purchasedCount})` : ''}
              </TabsTrigger>
            </TabsList>

            {/* ── Browse tab ──────────────────────────────────────────────── */}
            <TabsContent value="browse" className="space-y-6">
              {/* Search and Filters */}
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Filter className="w-5 h-5" />Search &amp; Filter Candidates
                  </CardTitle>
                  <CardDescription>Find the perfect match for your requirements</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid md:grid-cols-4 gap-4">
                    <div className="relative md:col-span-2">
                      <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                      <Input
                        placeholder="Search by skills (e.g. react, python)…"
                        className="pl-10"
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                      />
                    </div>
                    <Select value={experienceFilter} onValueChange={setExperienceFilter}>
                      <SelectTrigger><SelectValue placeholder="Experience Level" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All Experience Levels</SelectItem>
                        {EXPERIENCE_TIERS.map(t => (
                          <SelectItem key={t} value={t}>
                            {EXPERIENCE_TIER_DISPLAY[t] || t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={minScore} onValueChange={setMinScore}>
                      <SelectTrigger><SelectValue placeholder="Minimum Score" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="0">All Scores</SelectItem>
                        <SelectItem value="70">70% and above</SelectItem>
                        <SelectItem value="80">80% and above</SelectItem>
                        <SelectItem value="90">90% and above</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>

              {/* Candidate table */}
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Users className="w-5 h-5" />Available Candidates
                      </CardTitle>
                      <CardDescription>
                        {loading
                          ? 'Loading…'
                          : `Showing ${Math.min(visibleCount, sortedCandidates.length)} of ${sortedCandidates.length}`}
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                      <div className="flex items-center gap-2 pr-1">
                        <Switch
                          id="hide-purchased"
                          checked={hidePurchased}
                          onCheckedChange={setHidePurchased}
                        />
                        <Label htmlFor="hide-purchased" className="text-sm text-gray-600 cursor-pointer">
                          Hide purchased
                        </Label>
                      </div>
                      <Select value={sortKey} onValueChange={v => setSortKey(v as SortKey)}>
                        <SelectTrigger className="w-[190px]">
                          <ArrowUpDown className="w-4 h-4 mr-2" />
                          <SelectValue placeholder="Sort" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="score_desc">Score: High to Low</SelectItem>
                          <SelectItem value="score_asc">Score: Low to High</SelectItem>
                          <SelectItem value="recent">Most Recent</SelectItem>
                          <SelectItem value="experience">Most Experience</SelectItem>
                        </SelectContent>
                      </Select>
                      {selectedCandidates.length > 0 && (
                        <>
                          <Button variant="outline" size="sm" onClick={clearCart}>Clear</Button>
                          <Button size="sm" onClick={handleViewCart}>
                            <ShoppingCart className="w-4 h-4 mr-2" />
                            Unlock ({selectedCandidates.length})
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {loading ? (
                    <div className="py-16 text-center space-y-3">
                      <Loader2 className="w-10 h-10 text-blue-600 animate-spin mx-auto" />
                      <p className="text-gray-600">Loading candidates…</p>
                    </div>
                  ) : sortedCandidates.length === 0 ? (
                    <div className="py-12 text-center">
                      <Search className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                      <h3 className="text-lg font-semibold text-gray-900 mb-2">No candidates found</h3>
                      <p className="text-gray-600">
                        {stats.total === 0
                          ? 'No candidates have published their profile yet.'
                          : 'Try adjusting your search filters.'}
                      </p>
                    </div>
                  ) : (
                    <>
                      {/* Scrollable table region */}
                      <div className="rounded-lg border border-gray-200 overflow-hidden">
                        <div className="max-h-[34rem] overflow-y-auto">
                          <Table>
                            <TableHeader className="sticky top-0 z-10 bg-gray-50">
                              <TableRow className="bg-gray-50 hover:bg-gray-50">
                                <TableHead className="w-8"></TableHead>
                                <TableHead>Candidate</TableHead>
                                <TableHead className="hidden lg:table-cell">Skills</TableHead>
                                <TableHead className="text-center hidden sm:table-cell">Resume</TableHead>
                                <TableHead className="text-center hidden sm:table-cell">Quiz</TableHead>
                                <TableHead className="text-center hidden sm:table-cell">Interview</TableHead>
                                <TableHead className="text-center">Final</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {visibleCandidates.map(c => {
                                const isSelected = selectedCandidates.includes(c.id);
                                const isExpanded = expandedRows.has(c.id);
                                return (
                                  <React.Fragment key={c.id}>
                                    <TableRow
                                      className={isSelected ? 'bg-blue-50/60 hover:bg-blue-50' : undefined}
                                    >
                                      {/* Expander */}
                                      <TableCell className="align-top">
                                        {c.interview_breakdown ? (
                                          <button
                                            type="button"
                                            onClick={() => toggleExpand(c.id)}
                                            aria-label={isExpanded ? 'Collapse' : 'Expand'}
                                            className="text-gray-400 hover:text-gray-700 transition-colors mt-1"
                                          >
                                            {isExpanded
                                              ? <ChevronDown className="w-4 h-4" />
                                              : <ChevronRight className="w-4 h-4" />}
                                          </button>
                                        ) : null}
                                      </TableCell>

                                      {/* Candidate identity */}
                                      <TableCell className="align-top">
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <span className="font-medium text-gray-900">
                                            {c.unlocked ? (c.full_name || c.display_name) : c.display_name}
                                          </span>
                                          {c.unlocked && (
                                            <Badge className="bg-green-100 text-green-700 gap-1">
                                              <CheckCircle2 className="w-3 h-3" />Purchased
                                            </Badge>
                                          )}
                                        </div>
                                        <div className="flex items-center gap-2 flex-wrap mt-1">
                                          {c.years_experience != null && (
                                            <Badge className="bg-blue-100 text-blue-700">
                                              {getExperienceDisplay(c.years_experience, c.experience_tier)}
                                            </Badge>
                                          )}
                                        </div>
                                        {c.location && (
                                          <p className="text-xs text-gray-500 flex items-center gap-1 mt-1">
                                            <MapPin className="w-3 h-3" />{c.location}
                                          </p>
                                        )}
                                      </TableCell>

                                      {/* Skills */}
                                      <TableCell className="align-top hidden lg:table-cell">
                                        {c.skills.length === 0 ? (
                                          <span className="text-sm text-gray-400 italic">None listed</span>
                                        ) : (
                                          <div className="flex flex-wrap gap-1 max-w-xs">
                                            {c.skills.slice(0, 4).map(s => (
                                              <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                                            ))}
                                            {c.skills.length > 4 && (
                                              <Badge variant="outline" className="text-xs text-gray-500">
                                                +{c.skills.length - 4}
                                              </Badge>
                                            )}
                                          </div>
                                        )}
                                      </TableCell>

                                      {/* Score columns */}
                                      <TableCell className="text-center align-top hidden sm:table-cell">
                                        <span className="font-semibold text-blue-600">{c.scores.resume}%</span>
                                      </TableCell>
                                      <TableCell className="text-center align-top hidden sm:table-cell">
                                        <span className="font-semibold text-purple-600">{c.scores.quiz}%</span>
                                      </TableCell>
                                      <TableCell className="text-center align-top hidden sm:table-cell">
                                        <span className="font-semibold text-pink-600">{c.scores.interview}%</span>
                                      </TableCell>
                                      <TableCell className="text-center align-top">
                                        <Badge className={scoreBadgeClass(c.scores.final)}>
                                          <Award className="w-3 h-3 mr-1" />{c.scores.final}%
                                        </Badge>
                                      </TableCell>

                                      {/* Actions */}
                                      <TableCell className="text-right align-top">
                                        <div className="flex justify-end gap-2">
                                          {!c.unlocked && (
                                            <Button
                                              variant={isSelected ? 'default' : 'outline'}
                                              size="sm"
                                              onClick={() => toggleSelection(c.id)}
                                            >
                                              {isSelected ? 'Selected' : 'Select'}
                                            </Button>
                                          )}
                                          <Button variant="outline" size="sm" onClick={() => handleViewProfile(c.id)}>
                                            <Eye className="w-4 h-4 sm:mr-2" />
                                            <span className="hidden sm:inline">{c.unlocked ? 'View' : 'Preview'}</span>
                                          </Button>
                                        </div>
                                      </TableCell>
                                    </TableRow>

                                    {/* Expanded interview breakdown */}
                                    {isExpanded && c.interview_breakdown && (
                                      <TableRow className="bg-green-50/50 hover:bg-green-50/50">
                                        <TableCell></TableCell>
                                        <TableCell colSpan={7}>
                                          <p className="text-sm font-medium text-green-900 mb-2 flex items-center gap-1">
                                            <Star className="w-3 h-3" />Verified Interview Performance
                                          </p>
                                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs max-w-2xl">
                                            <div><span className="text-gray-600">Technical:</span> <strong className="text-green-800">{c.interview_breakdown.technical}%</strong></div>
                                            <div><span className="text-gray-600">Behavioural:</span> <strong className="text-green-800">{c.interview_breakdown.personality}%</strong></div>
                                            <div><span className="text-gray-600">Attentiveness:</span> <strong className="text-green-800">{c.interview_breakdown.attentiveness}%</strong></div>
                                            <div><span className="text-gray-600">Eye Contact:</span> <strong className="text-green-800">{c.interview_breakdown.eye_contact}%</strong></div>
                                          </div>
                                          {!c.unlocked && (
                                            <p className="text-xs text-gray-500 mt-3 flex items-center gap-1">
                                              <Lock className="w-3 h-3" />Name, contact info, and bio unlock after purchase
                                            </p>
                                          )}
                                        </TableCell>
                                      </TableRow>
                                    )}
                                  </React.Fragment>
                                );
                              })}
                            </TableBody>
                          </Table>
                        </div>
                      </div>

                      {/* Show more */}
                      {hasMore && (
                        <div className="flex justify-center mt-6">
                          <Button
                            variant="outline"
                            onClick={() => setVisibleCount(v => v + PAGE_SIZE)}
                          >
                            Show more
                            <span className="ml-2 text-gray-500">
                              ({sortedCandidates.length - visibleCount} left)
                            </span>
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* ── Purchased tab ───────────────────────────────────────────── */}
            <TabsContent value="purchased" className="space-y-6">
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Unlock className="w-5 h-5" />Purchased Profiles
                  </CardTitle>
                  <CardDescription>
                    Candidates you've unlocked. Contact details are revealed here.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {purchasedLoading ? (
                    <div className="py-16 text-center space-y-3">
                      <Loader2 className="w-10 h-10 text-green-600 animate-spin mx-auto" />
                      <p className="text-gray-600">Loading purchased profiles…</p>
                    </div>
                  ) : purchased.length === 0 ? (
                    <div className="py-12 text-center">
                      <ShoppingCart className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                      <h3 className="text-lg font-semibold text-gray-900 mb-2">No purchases yet</h3>
                      <p className="text-gray-600 mb-4">
                        Unlock a candidate from the Browse tab to see their full profile and contact info here.
                      </p>
                    </div>
                  ) : (
                    <div className="grid md:grid-cols-2 gap-4">
                      {purchased.map(c => (
                        <div
                          key={c.id}
                          className="border border-green-200 bg-green-50/40 rounded-lg p-4 flex flex-col gap-3"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-gray-900">
                                  {c.full_name || c.display_name}
                                </span>
                                <Badge className="bg-green-100 text-green-700 gap-1">
                                  <CheckCircle2 className="w-3 h-3" />Unlocked
                                </Badge>
                              </div>
                              <div className="flex items-center gap-2 flex-wrap mt-1">
                                {c.years_experience != null && (
                                  <Badge className="bg-blue-100 text-blue-700">
                                    {getExperienceDisplay(c.years_experience, c.experience_tier)}
                                  </Badge>
                                )}
                              </div>
                            </div>
                            <Badge className={scoreBadgeClass(c.scores.final)}>
                              <Award className="w-3 h-3 mr-1" />{c.scores.final}%
                            </Badge>
                          </div>

                          {c.location && (
                            <p className="text-sm text-gray-600 flex items-center gap-1">
                              <MapPin className="w-3 h-3" />{c.location}
                            </p>
                          )}

                          {/* Revealed contact */}
                          <div className="space-y-1 text-sm">
                            {c.email && (
                              <p className="flex items-center gap-2 text-gray-700">
                                <Mail className="w-3 h-3 text-gray-500" />{c.email}
                              </p>
                            )}
                            {c.phone && (
                              <p className="flex items-center gap-2 text-gray-700">
                                <Phone className="w-3 h-3 text-gray-500" />{c.phone}
                              </p>
                            )}
                          </div>

                          {c.skills.length > 0 && (
                            <div className="flex flex-wrap gap-1">
                              {c.skills.slice(0, 6).map(s => (
                                <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                              ))}
                              {c.skills.length > 6 && (
                                <Badge variant="outline" className="text-xs text-gray-500">
                                  +{c.skills.length - 6}
                                </Badge>
                              )}
                            </div>
                          )}

                          <Button
                            variant="outline"
                            size="sm"
                            className="self-start mt-1"
                            onClick={() => handleViewProfile(c.id)}
                          >
                            <Eye className="w-4 h-4 mr-2" />View full profile
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </motion.div>
      </div>
    </div>
  );
}
