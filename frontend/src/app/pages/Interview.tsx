import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { motion, AnimatePresence } from 'motion/react';
import {
  Video, ArrowLeft, AlertTriangle,
  CheckCircle2, Clock, Brain, Loader2, FileText, Trash2,
  Mic, MicOff, XCircle, Eye, EyeOff, ScanFace,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { useAuth } from '../context/AuthContext';
import { toast } from 'sonner';
import { API_BASE_URL } from '../config';
import { useAttentivenessMonitoring } from '../hooks/useAttentivenessMonitoring';
import { getExperienceDisplay } from '../utils/experienceDisplay';

// ── Types ─────────────────────────────────────────────────────────────────────
interface InterviewQuestion {
  id: number;
  question_text: string;
  question_type: 'technical' | 'personality';
  category: string;
  order: number;
}

type PageState = 'loading' | 'locked' | 'setup' | 'active' | 'submitting';

// ── Constants ──────────────────────────────────────────────────────────────────
const INTERVIEW_TIME_LIMIT = 1500;
const FOCUS_VIOLATION_LIMIT = 1;
const NON_ENGLISH_PATTERN = /[^\x00-\x7F]/;

function looksNonEnglish(text: string): boolean {
  return NON_ENGLISH_PATTERN.test(text);
}

// Human-friendly "time remaining" until a cooldown ends (e.g. "2 days 5 hours",
// "3 hours 12 minutes"). Used instead of a calendar date so short cooldowns read
// correctly rather than collapsing to "today".
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

// ── Component ─────────────────────────────────────────────────────────────────
export default function Interview() {
  const navigate = useNavigate();
  const { authFetch, refreshUser, canTakeInterview } = useAuth();

  // Page state machine
  const [pageState, setPageState] = useState<PageState>('loading');
  const [lockReason, setLockReason] = useState('');
  const [cooldownEnd, setCooldownEnd] = useState<Date | null>(null);
  const [previousScore, setPreviousScore] = useState<number | null>(null);

  // Session
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [jobRole, setJobRole] = useState('');
  const [yearsExperience, setYearsExperience] = useState<number>(0);
  const [experienceBand, setExperienceBand] = useState('');
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [timeLeft, setTimeLeft] = useState(INTERVIEW_TIME_LIMIT);
  const [resumed, setResumed] = useState(false);

  // Interview progress
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [transcripts, setTranscripts] = useState<Record<number, string>>({});   // questionId → transcript
  const [interimText, setInterimText] = useState('');

  // A/V
  const [mediaError, setMediaError] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [streamReady, setStreamReady] = useState(false);

  // Mic test (setup screen only — kept separate from real interview transcripts)
  const [micTestActive, setMicTestActive] = useState(false);
  const [micTestText, setMicTestText] = useState('');
  const [micTestInterim, setMicTestInterim] = useState('');
  const [micLevel, setMicLevel] = useState(0); // 0–100 live input level

  // End-interview confirmation modal
  const [showEndConfirm, setShowEndConfirm] = useState(false);

  // Refs (declared before hooks that consume them)
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const isRecognitionActiveRef = useRef(false);
  const currentQuestionIdRef = useRef<number | null>(null);
  const mediaViolationRef = useRef(false);
  const enteredFullscreenRef = useRef(false);
  const monitoringRef = useRef({
    tab_switches: 0,
    window_blur_events: 0,
    screenshot_attempted: 0,
    device_detected: 0,
    gaze_off_over_20s: 0,
    camera_available: 1,
    mic_available: 1,
    english_only_violation: 0,
    terminated_by_violation: false,
  });

  // Mic test refs
  const micTestRecognitionRef = useRef<SpeechRecognition | null>(null);
  const isMicTestActiveRef = useRef(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micRafRef = useRef<number | null>(null);
  const audioBlobsRef = useRef<Record<number, Blob>>({});
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recorderChunksRef = useRef<Blob[]>([]);
  const answerTimingsRef = useRef<Record<number, number>>({});
  const questionStartedAtRef = useRef<number | null>(null);
  const pendingMonitoringSamplesRef = useRef<{ attentive: boolean; eye_contact: boolean }[]>([]);
  const monitoringSyncTimerRef = useRef<number | null>(null);

  const handleMonitoringSample = useCallback((sample: { attentive: boolean; eye_contact: boolean }) => {
    pendingMonitoringSamplesRef.current.push(sample);
  }, []);

  const handleSustainedGazeOff = useCallback(() => {
    monitoringRef.current.gaze_off_over_20s += 1;
    toast.warning('Sustained gaze away detected — this affects your attentiveness score.');
  }, []);

  const flushMonitoringToBackend = useCallback(async (includeEvents = false) => {
    if (!sessionId || pendingMonitoringSamplesRef.current.length === 0) return;
    const samples = pendingMonitoringSamplesRef.current.splice(0);
    const monitoring = monitoringRef.current;
    try {
      await authFetch(`${API_BASE_URL}/api/interviews/monitoring/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          samples,
          ...(includeEvents
            ? {
              events: {
                tab_switches: monitoring.tab_switches,
                window_blur_events: monitoring.window_blur_events,
                screenshot_attempted: monitoring.screenshot_attempted,
                device_detected: monitoring.device_detected,
                gaze_off_over_20s: monitoring.gaze_off_over_20s,
                english_only_violation: monitoring.english_only_violation,
              },
              flags: {
                camera_available: monitoring.camera_available,
                mic_available: monitoring.mic_available,
                terminated_by_violation: monitoring.terminated_by_violation,
              },
            }
            : {}),
        }),
      });
    } catch {
      pendingMonitoringSamplesRef.current.unshift(...samples);
    }
  }, [authFetch, sessionId]);

  const stopQuestionRecording = useCallback(async (): Promise<void> => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;

    await new Promise<void>((resolve) => {
      recorder.onstop = () => {
        const qId = currentQuestionIdRef.current;
        if (qId && recorderChunksRef.current.length > 0) {
          audioBlobsRef.current[qId] = new Blob(recorderChunksRef.current, {
            type: recorder.mimeType || 'audio/webm',
          });
        }
        recorderChunksRef.current = [];
        resolve();
      };
      recorder.stop();
    });
    mediaRecorderRef.current = null;
  }, []);

  const startQuestionRecording = useCallback(() => {
    const stream = streamRef.current;
    const audioTrack = stream?.getAudioTracks()[0];
    if (!audioTrack) return;

    recorderChunksRef.current = [];
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm';
    const recorder = new MediaRecorder(new MediaStream([audioTrack]), { mimeType });
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) recorderChunksRef.current.push(event.data);
    };
    recorder.start(1000);
    mediaRecorderRef.current = recorder;
    questionStartedAtRef.current = Date.now();
  }, []);

  // Monitoring — real MediaPipe-based attentiveness analysis
  // (preflights on the setup screen; scores during the live interview)
  const {
    attentivenessScore,        // live meter (for the bars)
    eyeContactScore,           // live meter (for the bars)
    sessionAttentiveness,      // cumulative grade (submit this)
    sessionEyeContact,         // cumulative grade (submit this)
    faceDetected,
    multipleFaces,
    monitoringStatus,
    calibrationProgress,
    warning: attentivenessWarning,
  } = useAttentivenessMonitoring({
    phase: pageState === 'active' ? 'scoring' : pageState === 'setup' ? 'preflight' : 'idle',
    videoRef,
    onSample: pageState === 'active' ? handleMonitoringSample : undefined,
    onSustainedGazeOff: pageState === 'active' ? handleSustainedGazeOff : undefined,
  });

  const isMonitorLoading = monitoringStatus === 'loading';
  const isMonitorReady = monitoringStatus === 'active' || monitoringStatus === 'calibrating';
  const isMonitorUnavailable = monitoringStatus === 'unavailable';

  // Keep currentQuestionIdRef in sync
  useEffect(() => {
    if (questions.length > 0) {
      currentQuestionIdRef.current = questions[currentQuestion]?.id ?? null;
    }
  }, [currentQuestion, questions]);

  // Gate interview page on quiz pass / cooldown / already passed.
  // Do not override active/submitting flows — refreshUser() after submit sets
  // cooldown on the profile and would otherwise flash the locked screen briefly.
  useEffect(() => {
    setPageState((current) => {
      if (current === 'active' || current === 'submitting') {
        return current;
      }
      if (current === 'loading' && sessionId != null) {
        return current;
      }

      const gate = canTakeInterview();
      if (!gate.allowed) {
        return 'locked';
      }
      return current === 'locked' ? 'setup' : 'setup';
    });
  }, [canTakeInterview, sessionId]);

  useEffect(() => {
    if (pageState !== 'locked') return;
    const gate = canTakeInterview();
    if (!gate.allowed) {
      setLockReason(gate.reason || 'Interview is currently unavailable.');
      if (gate.cooldownEnd) setCooldownEnd(gate.cooldownEnd);
    }
  }, [pageState, canTakeInterview]);

  // Sync monitoring samples to backend during active interview.
  useEffect(() => {
    if (pageState !== 'active' || !sessionId) return;
    monitoringSyncTimerRef.current = window.setInterval(() => {
      void flushMonitoringToBackend(false);
    }, 5000);
    return () => {
      if (monitoringSyncTimerRef.current) {
        window.clearInterval(monitoringSyncTimerRef.current);
        monitoringSyncTimerRef.current = null;
      }
    };
  }, [pageState, sessionId, flushMonitoringToBackend]);

  // Start audio recording when interview becomes active or question changes.
  useEffect(() => {
    if (pageState !== 'active' || questions.length === 0) return;
    startQuestionRecording();
    return () => {
      void stopQuestionRecording();
    };
  }, [pageState, currentQuestion, questions.length, startQuestionRecording, stopQuestionRecording]);

  // Camera + microphone: required throughout interview
  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: true })
      .then(stream => {
        stream.getAudioTracks().forEach(track => {
          track.enabled = true;
        });

        stream.getVideoTracks().forEach(track => {
          track.enabled = true;
        });

        const hasMic = stream.getAudioTracks().length > 0;
        const hasCamera = stream.getVideoTracks().length > 0;

        if (!hasMic || !hasCamera) {
          setMediaError('Camera and microphone are required to start the interview.');
          return;
        }

        streamRef.current = stream;
        setMediaError(null);
        setStreamReady(true);

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      })
      .catch(() => {
        setStreamReady(false);
        setMediaError('Camera and microphone access is required to start the interview.');
        toast.error('Camera / Microphone access denied');
      });

    return () => {
      streamRef.current?.getTracks().forEach(track => track.stop());
      streamRef.current = null;
      setStreamReady(false);
    };
  }, []);

  useEffect(() => {
    if (videoRef.current && streamRef.current) videoRef.current.srcObject = streamRef.current;
  }, [pageState]);

  const checkMediaStatus = useCallback(() => {
    const stream = streamRef.current;

    if (!stream) {
      setMediaError('Camera and microphone are required during the interview.');
      return false;
    }

    const hasActiveMic = stream
      .getAudioTracks()
      .some(track => track.readyState === 'live' && track.enabled);

    const hasActiveCamera = stream
      .getVideoTracks()
      .some(track => track.readyState === 'live' && track.enabled);

    if (!hasActiveMic || !hasActiveCamera) {
      setMediaError('Camera and microphone must remain enabled throughout the interview.');
      return false;
    }

    setMediaError(null);
    return true;
  }, []);

  // Speech recognition
  useEffect(() => {
    if (pageState !== 'active') {
      isRecognitionActiveRef.current = false;
      return;
    }

    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SR) { toast.error('Speech Recognition not supported in this browser.'); return; }

    isRecognitionActiveRef.current = true;

    const startRecognition = () => {
      const recognition = new SR();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let finalText = '';
        let interimText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) finalText += event.results[i][0].transcript + ' ';
          else interimText += event.results[i][0].transcript;
        }
        if (finalText && currentQuestionIdRef.current !== null) {
          const qId = currentQuestionIdRef.current;
          if (looksNonEnglish(finalText)) {
            monitoringRef.current.english_only_violation += 1;
            toast.error('Please answer in English only.');
          }
          setTranscripts(prev => ({ ...prev, [qId]: (prev[qId] || '') + finalText }));
        }
        setInterimText(interimText);
      };

      recognition.onerror = (e: any) => { if (e.error !== 'no-speech') console.error('SR error:', e.error); };
      recognition.onend = () => {
        setInterimText('');
        if (isRecognitionActiveRef.current) {
          try { recognition.start(); } catch { /* already running */ }
        }
      };

      recognition.start();
      recognitionRef.current = recognition;
    };

    startRecognition();
    return () => {
      isRecognitionActiveRef.current = false;
      recognitionRef.current?.stop();
    };
  }, [pageState]);

  // ── Mic test: speech-to-text (setup screen only) ──────────────────────────────
  useEffect(() => {
    if (pageState !== 'setup' || !micTestActive) {
      isMicTestActiveRef.current = false;
      micTestRecognitionRef.current?.stop();
      setMicTestInterim('');
      return;
    }

    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SR) {
      toast.error('Speech Recognition not supported in this browser.');
      setMicTestActive(false);
      return;
    }

    isMicTestActiveRef.current = true;

    const startRecognition = () => {
      const recognition = new SR();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event: SpeechRecognitionEvent) => {
        let finalText = '';
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) finalText += event.results[i][0].transcript + ' ';
          else interim += event.results[i][0].transcript;
        }
        if (finalText) setMicTestText(prev => prev + finalText);
        setMicTestInterim(interim);
      };

      recognition.onerror = (e: any) => { if (e.error !== 'no-speech') console.error('Mic test SR error:', e.error); };
      recognition.onend = () => {
        setMicTestInterim('');
        if (isMicTestActiveRef.current) {
          try { recognition.start(); } catch { /* already running */ }
        }
      };

      recognition.start();
      micTestRecognitionRef.current = recognition;
    };

    startRecognition();
    return () => {
      isMicTestActiveRef.current = false;
      micTestRecognitionRef.current?.stop();
    };
  }, [pageState, micTestActive]);

  // ── Mic test: live input-level meter (setup screen only) ──────────────────────
  useEffect(() => {
    if (pageState !== 'setup' || !micTestActive || !streamReady || !streamRef.current) {
      setMicLevel(0);
      return;
    }

    const AudioCtx = (window as any).AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) return;

    let cancelled = false;
    const ctx: AudioContext = new AudioCtx();
    audioCtxRef.current = ctx;

    const source = ctx.createMediaStreamSource(streamRef.current);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);

    const data = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      if (cancelled) return;
      analyser.getByteTimeDomainData(data);

      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }

      const rms = Math.sqrt(sum / data.length);
      const level = Math.min(100, Math.round(rms * 250));
      setMicLevel(level);
      micRafRef.current = requestAnimationFrame(tick);
    };

    tick();

    return () => {
      cancelled = true;
      if (micRafRef.current) cancelAnimationFrame(micRafRef.current);
      micRafRef.current = null;
      source.disconnect();
      ctx.close().catch(() => { });
      audioCtxRef.current = null;
      setMicLevel(0);
    };
  }, [pageState, micTestActive, streamReady]);

  // Timer
  useEffect(() => {
    if (pageState !== 'active') return;
    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) { clearInterval(timer); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [pageState]);

  useEffect(() => {
    if (timeLeft === 0 && pageState === 'active') handleFinishInterview();
  }, [timeLeft, pageState]);

  // ── AI monitoring – warnings are now surfaced by the monitoring hook itself
  // (debounced with a streak + already-warned latch), so no toast effect here.

  // ── Handlers ─────────────────────────────────────────────────────────────────
  const handleStartInterview = async () => {
    if (!checkMediaStatus()) {
      toast.error('Camera and microphone must be enabled before starting the interview.');
      return;
    }

    // Proctoring is mandatory: never create a backend session for an interview
    // whose attentiveness/eye-contact can't be measured. The model is loaded in
    // the background while the candidate is on this setup screen ('preflight').
    if (isMonitorUnavailable) {
      toast.error('Attentiveness monitoring failed to start. Camera-based proctoring is required — use Chrome or Edge, allow camera access, and reload.');
      return;
    }
    if (!isMonitorReady) {
      toast.info('Attentiveness monitoring is still initializing. Please wait a moment and try again.');
      return;
    }

    mediaViolationRef.current = false;
    enteredFullscreenRef.current = false;
    setMicTestActive(false);

    document.documentElement.requestFullscreen?.()
      .then(() => {
        enteredFullscreenRef.current = true;
      })
      .catch(() => {
        enteredFullscreenRef.current = false;
      });

    setPageState('loading');

    try {
      const res = await authFetch(`${API_BASE_URL}/api/interviews/start/`, {
        method: 'POST',
      });

      const data = await res.json();

      if (!res.ok) {
        // If user already has an interview result, send them to the report page
        // instead of showing the temporary locked/interview result screen.
        if (data.already_passed || data.cooldown_until) {
          toast.info(
            data.already_passed
              ? 'You have already passed the interview.'
              : 'Interview is on cooldown. View your report for details.'
          );

          navigate('/interview-report', { replace: true });
          return;
        }

        // Keep real locked cases on the locked screen
        if (data.quiz_required) {
          setLockReason('You must pass the quiz before taking the interview.');
        } else {
          setLockReason(data.error || 'Interview is currently unavailable.');
        }

        setPageState('locked');
        return;
      }

      setSessionId(data.session_id);
      setJobRole(data.job_role || '');
      setYearsExperience(Number(data.years_experience || 0));
      setExperienceBand(data.experience_band || '');
      setQuestions(data.questions);
      setTimeLeft(data.time_limit_seconds ?? INTERVIEW_TIME_LIMIT);
      setResumed(data.resumed ?? false);

      const initial: Record<number, string> = {};
      data.questions.forEach((q: InterviewQuestion) => {
        initial[q.id] = '';
      });
      setTranscripts(initial);

      setPageState('active');
      setIsRecording(true);

      if (data.resumed) toast.info('Interview resumed. Keep going!');
      else toast.success('Interview started. Good luck!');
    } catch {
      toast.error('Could not connect to the interview server. Please try again.');
      navigate('/dashboard');
    }
  };

  const handleNextQuestion = async () => {
    setInterimText('');
    const qId = questions[currentQuestion]?.id;
    if (qId && questionStartedAtRef.current) {
      answerTimingsRef.current[qId] = (Date.now() - questionStartedAtRef.current) / 1000;
    }
    await stopQuestionRecording();

    if (currentQuestion < questions.length - 1) {
      setCurrentQuestion(q => q + 1);
      toast.info('Next question loaded');
    } else {
      handleFinishInterview();
    }
  };

  const handleClearTranscript = () => {
    const qId = questions[currentQuestion]?.id;
    if (qId) setTranscripts(prev => ({ ...prev, [qId]: '' }));
    toast.success('Transcript cleared');
  };

  const handleToggleMicTest = () => {
    if (mediaError) {
      toast.error('Microphone is not available. Please allow access first.');
      return;
    }
    setMicTestActive(prev => !prev);
  };

  const handleClearMicTest = () => {
    setMicTestText('');
    setMicTestInterim('');
  };

  const handleFinishInterview = useCallback(async (terminatedByViolation: boolean = false) => {
    if (pageState === 'submitting') return;

    isRecognitionActiveRef.current = false;
    recognitionRef.current?.stop();

    const qId = questions[currentQuestion]?.id;
    if (qId && questionStartedAtRef.current) {
      answerTimingsRef.current[qId] = (Date.now() - questionStartedAtRef.current) / 1000;
    }
    await stopQuestionRecording();

    const stream = streamRef.current;
    const hasCamera = Boolean(stream?.getVideoTracks().some(t => t.readyState === 'live' && t.enabled));
    const hasMic = Boolean(stream?.getAudioTracks().some(t => t.readyState === 'live' && t.enabled));

    monitoringRef.current.camera_available = hasCamera ? 1 : 0;
    monitoringRef.current.mic_available = hasMic ? 1 : 0;
    if (terminatedByViolation) {
      monitoringRef.current.terminated_by_violation = true;
    }

    await flushMonitoringToBackend(true);

    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;

    setIsRecording(false);
    setPageState('submitting');

    if (!sessionId) { navigate('/dashboard'); return; }

    const answersPayload: Record<string, string> = {};
    questions.forEach(q => { answersPayload[String(q.id)] = transcripts[q.id] || ''; });

    const monitoring = monitoringRef.current;
    // Drain any samples captured since the last periodic flush so the backend
    // has the complete set when it computes the final attentiveness grade.
    const remainingSamples = pendingMonitoringSamplesRef.current.splice(0);
    const formData = new FormData();
    formData.append('session_id', String(sessionId));
    formData.append('answers', JSON.stringify(answersPayload));
    formData.append('answer_timings', JSON.stringify(answerTimingsRef.current));
    formData.append('monitoring', JSON.stringify({
      samples: remainingSamples,
      events: {
        tab_switches: monitoring.tab_switches,
        window_blur_events: monitoring.window_blur_events,
        screenshot_attempted: monitoring.screenshot_attempted,
        device_detected: monitoring.device_detected,
        gaze_off_over_20s: monitoring.gaze_off_over_20s,
        english_only_violation: monitoring.english_only_violation,
      },
      flags: {
        camera_available: monitoring.camera_available,
        mic_available: monitoring.mic_available,
        terminated_by_violation: monitoring.terminated_by_violation,
      },
    }));

    questions.forEach(q => {
      const blob = audioBlobsRef.current[q.id];
      if (blob) {
        formData.append(`audio_${q.id}`, blob, `answer_${q.id}.webm`);
      }
    });

    try {
      const res = await authFetch(`${API_BASE_URL}/api/interviews/submit/`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();

      if (res.ok) {
        await refreshUser();

        if (data.passed) {
          toast.success('Congratulations! You passed the interview!');
        } else {
          toast.error('Interview not passed. View your report for feedback and cooldown details.');
        }

        navigate('/interview-report', { replace: true });
        return;
      } else {
        toast.error(data.error || 'Submission failed.');
        setPageState('setup');
      }
    } catch {
      toast.error('Network error during submission.');
      setPageState('setup');
    }
  }, [pageState, sessionId, questions, transcripts, authFetch, navigate, refreshUser, stopQuestionRecording, flushMonitoringToBackend, currentQuestion]);

  // Opens the in-app confirmation modal.
  // NOTE: we intentionally avoid window.confirm() here — a native dialog forces
  // the browser to leave fullscreen / blur the window, which trips the violation
  // detector and auto-submits the interview even when the user clicks "Cancel".
  const handleEndInterview = () => {
    setShowEndConfirm(true);
  };

  const confirmEndInterview = () => {
    setShowEndConfirm(false);
    handleFinishInterview();
  };

  const cancelEndInterview = () => {
    setShowEndConfirm(false);
  };

  // Tab / focus / fullscreen violation detection
  useEffect(() => {
    if (pageState !== 'active') return;

    let blurTimer: number | undefined;

    const clearBlurTimer = () => {
      if (blurTimer) {
        window.clearTimeout(blurTimer);
        blurTimer = undefined;
      }
    };

    const submitViolation = (reason: 'tab' | 'blur' | 'fullscreen' = 'tab') => {
      if (pageState !== 'active') return;

      if (reason === 'tab') {
        monitoringRef.current.tab_switches += 1;
      } else {
        // window blur and fullscreen-exit both count as focus-loss events
        monitoringRef.current.window_blur_events += 1;
      }

      const focusEvents =
        monitoringRef.current.tab_switches +
        monitoringRef.current.window_blur_events +
        monitoringRef.current.gaze_off_over_20s;

      // Tiered enforcement: warn for the first (LIMIT - 1) events, only auto-submit
      // once the candidate reaches the limit. This avoids ending an interview over a
      // single OS notification, permission prompt, or accidental Escape key.
      if (focusEvents >= FOCUS_VIOLATION_LIMIT) {
        toast.error('Final focus violation — submitting your interview now.');
        handleFinishInterview(true);
      } else {
        const remaining = FOCUS_VIOLATION_LIMIT - focusEvents;
        toast.warning(
          `Please stay on the interview screen. ${remaining} warning${remaining === 1 ? '' : 's'} left before your interview is auto-submitted.`
        );
      }
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        submitViolation('tab');
      }
    };

    const onBlur = () => {
      clearBlurTimer();
      blurTimer = window.setTimeout(() => submitViolation('blur'), 150);
    };

    const onFocus = () => {
      clearBlurTimer();
    };

    const onFullscreenChange = () => {
      if (enteredFullscreenRef.current && !document.fullscreenElement) {
        submitViolation('fullscreen');
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    document.addEventListener('fullscreenchange', onFullscreenChange);

    return () => {
      clearBlurTimer();
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('fullscreenchange', onFullscreenChange);
    };
  }, [pageState, handleFinishInterview]);

  useEffect(() => {
    if (pageState !== 'active') return;

    const interval = setInterval(() => {
      const mediaIsValid = checkMediaStatus();

      if (!mediaIsValid && !mediaViolationRef.current) {
        mediaViolationRef.current = true;
        monitoringRef.current.camera_available = 0;
        monitoringRef.current.mic_available = 0;
        toast.error('Camera or microphone stopped. Submitting your interview now.');
        handleFinishInterview(true);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [pageState, checkMediaStatus, handleFinishInterview]);

  // Screenshot / copy attempt detection
  useEffect(() => {
    if (pageState !== 'active') return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'PrintScreen' || (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 's')) {
        monitoringRef.current.screenshot_attempted += 1;
        toast.error('Screenshot attempts are not allowed during the interview.');
      }
    };

    const onCopy = () => {
      monitoringRef.current.screenshot_attempted += 1;
      toast.error('Copying content during the interview is not allowed.');
    };

    window.addEventListener('keydown', onKeyDown);
    document.addEventListener('copy', onCopy);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('copy', onCopy);
    };
  }, [pageState]);

  // External device heuristic — extra video inputs beyond the active camera.
  useEffect(() => {
    if (pageState !== 'active') return;

    const checkDevices = async () => {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoInputs = devices.filter(d => d.kind === 'videoinput');
        if (videoInputs.length > 2) {
          monitoringRef.current.device_detected += 1;
          toast.warning('Multiple camera devices detected.');
        }
      } catch {
        // ignore
      }
    };

    navigator.mediaDevices?.addEventListener('devicechange', checkDevices);
    void checkDevices();
    return () => navigator.mediaDevices?.removeEventListener('devicechange', checkDevices);
  }, [pageState]);

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  // ── Render helpers ────────────────────────────────────────────────────────────

  if (pageState === 'loading') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 className="w-12 h-12 text-blue-600 animate-spin mx-auto" />
          <p className="text-gray-600 font-medium">Setting up your interview…</p>
        </div>
      </div>
    );
  }

  if (pageState === 'locked') {
    const daysLeft = cooldownEnd
      ? Math.ceil((cooldownEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
      : 0;

    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }} className="max-w-2xl w-full">
          <Card className="border-0 shadow-2xl">
            <CardHeader className="text-center pb-0">
              <div className="w-20 h-20 mx-auto mb-4 bg-gradient-to-br from-orange-600 to-red-600 rounded-full flex items-center justify-center">
                <Clock className="w-10 h-10 text-white" />
              </div>
              <CardTitle className="text-3xl mb-2">Interview Locked</CardTitle>
              <CardDescription>{lockReason}</CardDescription>
            </CardHeader>
            <CardContent className="pt-6">
              {cooldownEnd && (
                <div className="bg-orange-50 border border-orange-200 rounded-lg p-6 mb-6 text-center">
                  <p className="text-lg font-semibold text-orange-900 mb-2">Cooldown Period Active</p>
                  <div className="text-4xl font-bold text-orange-600 mb-2">{daysLeft} {daysLeft === 1 ? 'Day' : 'Days'}</div>
                  <p className="text-sm text-orange-700">Available on: {cooldownEnd.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}</p>
                </div>
              )}

              {previousScore !== null && (
                <div className="bg-gray-50 rounded-lg p-4 mb-6">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm font-medium text-gray-600">Previous Score</span>
                    <span className="font-bold text-gray-900">{previousScore}%</span>
                  </div>
                  <Progress value={previousScore} className="h-2" />
                </div>
              )}

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-blue-700">Use this time to review resources and sharpen your skills before your next attempt.</p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {previousScore !== null && (
                  <Button onClick={() => navigate('/interview-report')}>
                    View Report
                  </Button>
                )}
                <Button variant="outline" onClick={() => navigate('/progress-report')}>View Resources</Button>
                <Button onClick={() => navigate('/dashboard')} className={previousScore !== null ? '' : 'sm:col-span-2'}>
                  Back to Dashboard
                </Button>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    );
  }

  if (pageState === 'submitting') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
        <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }} className="max-w-2xl w-full">
          <Card className="border-0 shadow-2xl">
            <CardHeader className="text-center pb-0">
              <div className="w-20 h-20 mx-auto mb-4 bg-gradient-to-br from-blue-600 to-purple-600 rounded-full flex items-center justify-center">
                <FileText className="w-10 h-10 text-white animate-pulse" />
              </div>
              <CardTitle className="text-3xl mb-2">Generating Your Report</CardTitle>
              <CardDescription>Analysing your interview performance…</CardDescription>
            </CardHeader>
            <CardContent className="pt-6 space-y-6">
              <div className="flex items-center justify-center">
                <Loader2 className="w-12 h-12 text-blue-600 animate-spin" />
              </div>
              <div className="space-y-3">
                {[
                  {
                    label: 'Analysing technical responses…',
                    box: 'bg-blue-50 border-blue-200',
                    icon: 'text-blue-600',
                    text: 'text-blue-800',
                  },
                  {
                    label: 'Evaluating behavioural answers…',
                    box: 'bg-purple-50 border-purple-200',
                    icon: 'text-purple-600',
                    text: 'text-purple-800',
                  },
                  {
                    label: 'Processing attentiveness metrics…',
                    box: 'bg-green-50 border-green-200',
                    icon: 'text-green-600',
                    text: 'text-green-800',
                  },
                ].map(({ label, box, icon, text }) => (
                  <div
                    key={label}
                    className={`${box} border rounded-lg p-4 flex items-center gap-3`}
                  >
                    <CheckCircle2 className={`w-5 h-5 ${icon}`} />
                    <span className={`text-sm ${text}`}>{label}</span>
                  </div>
                ))}
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <Progress value={66} className="h-2" />
                <p className="text-xs text-gray-600 mt-2 text-center">Generating comprehensive report…</p>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    );
  }

  // ── Setup screen ─────────────────────────────────────────────────────────────
  if (pageState === 'setup') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
        <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
                <ArrowLeft className="w-4 h-4 mr-2" />Back to Dashboard
              </Button>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                  <Video className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-gray-900">AI Interview</h1>
                  <p className="text-sm text-gray-600">{resumed ? 'Resume your session' : 'Setup & Instructions'}</p>
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {resumed && (
            <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
                <p className="text-sm text-amber-800"><strong>Resuming previous session.</strong> Your timer continues from where it left off.</p>
              </div>
            </motion.div>
          )}

          <div className="grid lg:grid-cols-2 gap-8">
            {/* Camera + Mic Preview */}
            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }} className="space-y-6">
              <Card className="border-0 shadow-2xl">
                <CardHeader>
                  <CardTitle>Camera Preview</CardTitle>
                  <CardDescription>Make sure you are clearly visible</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="relative aspect-video bg-gray-900 rounded-lg overflow-hidden">
                    <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover transform scale-x-[-1]" />
                  </div>
                  {mediaError && (
                    <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-3">
                      <p className="text-sm text-red-700">{mediaError}</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Microphone Test */}
              <Card className="border-0 shadow-2xl">
                <CardHeader>
                  <CardTitle>Microphone Test</CardTitle>
                  <CardDescription>Speak to test your mic before the Interview</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">

                  {/* Live input level */}
                  <div>
                    <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
                      <span>Input level</span>
                      <span>{micTestActive ? `${micLevel}%` : 'Off'}</span>
                    </div>
                    <div className="h-2 w-full bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-green-400 via-green-500 to-emerald-600 transition-[width] duration-75"
                        style={{ width: `${micTestActive ? micLevel : 0}%` }}
                      />
                    </div>
                  </div>

                  {/* Transcript box */}
                  <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-4 min-h-[110px]">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {micTestActive ? (
                          <>
                            <div className="w-2.5 h-2.5 bg-red-600 rounded-full animate-pulse" />
                            <span className="text-sm font-medium text-gray-700">Listening…</span>
                          </>
                        ) : (
                          <span className="text-sm font-medium text-gray-500">Mic test idle</span>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleClearMicTest}
                        disabled={!micTestText && !micTestInterim}
                        className="h-8"
                      >
                        <Trash2 className="w-4 h-4 mr-1" />Clear
                      </Button>
                    </div>
                    <p className="text-gray-600 italic text-sm">
                      {micTestText || micTestInterim
                        ? <>{micTestText}<span className="text-gray-400">{micTestInterim}</span></>
                        : 'Press “Test Microphone” and start speaking. Your speech will be transcribed here in real-time.'}
                    </p>
                  </div>

                  <Button
                    className="w-full"
                    variant={micTestActive ? 'destructive' : 'outline'}
                    onClick={handleToggleMicTest}
                    disabled={!!mediaError}
                  >
                    {micTestActive
                      ? <><MicOff className="w-4 h-4 mr-2" />Stop Test</>
                      : <><Mic className="w-4 h-4 mr-2" />Test Microphone</>}
                  </Button>

                  <p className="text-xs text-gray-500">
                    This is only a test — nothing here is saved or submitted. Your interview answers are recorded separately once you start.
                  </p>
                </CardContent>
              </Card>
            </motion.div>

            {/* Instructions */}
            <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}>
              <Card className="border-0 shadow-2xl">
                <CardHeader>
                  <CardTitle>Interview Instructions</CardTitle>
                  <CardDescription>Please read carefully before starting</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {(jobRole || yearsExperience > 0) && (
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                      <p className="text-sm text-blue-900">
                        <strong>Target role:</strong> {jobRole || 'Software Engineer'}
                        {' · '}
                        <strong>Experience:</strong> {getExperienceDisplay(yearsExperience, experienceBand)}
                      </p>
                    </div>
                  )}
                  <div className="space-y-3">
                    {[
                      'Ensure you are in a quiet, well-lit environment',
                      'Maintain eye contact with the camera',
                      'Speak clearly in English (mandatory)',
                      'Your spoken answers are recorded and transcribed on the server for scoring',
                      'Answer both technical and personality questions',
                    ].map(tip => (
                      <div key={tip} className="flex items-start gap-3">
                        <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                        <p className="text-sm text-gray-700">{tip}</p>
                      </div>
                    ))}
                  </div>

                  <div className="bg-red-50 border border-red-200 rounded-lg p-4 space-y-2">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle className="w-5 h-5 text-red-600" />
                      <p className="font-semibold text-red-900">Strict Rules</p>
                    </div>
                    <ul className="space-y-2 text-sm text-red-800">
                      {[
                        'Camera and microphone must remain on throughout the interview',
                        'Do not use any external devices or notes',
                        'Stay in fullscreen and focused on the interview screen',
                        'Switching tabs or leaving fullscreen gives a warning; repeated focus loss auto-submits your interview',
                        'AI monitors your face in real-time — looking away or turning your head will lower your score',
                      ].map(rule => (
                        <li key={rule} className="flex items-start gap-2">
                          <span className="text-red-600">&#8226;</span>
                          <span>{rule}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <ScanFace className="w-5 h-5 text-purple-600" />
                      <p className="font-semibold text-purple-900 text-sm">AI Face Monitoring</p>
                    </div>
                    <p className="text-sm text-purple-800">
                      The system uses AI-powered face detection to track your attentiveness and eye contact throughout the interview.
                      These scores contribute to your overall result, so stay focused on the camera.
                    </p>
                  </div>

                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <p className="text-sm text-blue-800">
                      <strong>Total Questions:</strong> 6 (Technical + Personality)<br />
                      <strong>Time Limit:</strong> {Math.round(timeLeft / 60)} minutes<br />
                      <strong>Passing Score:</strong> 70%
                    </p>
                  </div>

                  <Button
                    className="w-full"
                    size="lg"
                    onClick={handleStartInterview}
                    disabled={!!mediaError || !streamReady || !isMonitorReady}
                  >
                    {isMonitorUnavailable
                      ? 'Proctoring unavailable'
                      : !isMonitorReady
                        ? 'Initializing proctoring…'
                        : resumed ? 'Resume Interview' : 'Start Interview'}
                    <Video className="w-5 h-5 ml-2" />
                  </Button>
                  {isMonitorUnavailable && (
                    <p className="text-xs text-red-600 mt-2 text-center">
                      Face monitoring could not start. The interview requires working proctoring — use Chrome or Edge, allow camera access, and reload.
                    </p>
                  )}
                  {!isMonitorReady && !isMonitorUnavailable && !mediaError && streamReady && (
                    <p className="text-xs text-gray-500 mt-2 text-center">
                      Setting up face monitoring… this takes a few seconds.
                    </p>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </div>
      </div>
    );
  }

  // ── Active interview ──────────────────────────────────────────────────────────
  const currentQ = questions[currentQuestion];
  const currentTranscript = currentQ ? (transcripts[currentQ.id] || '') : '';

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* ── End Interview confirmation modal (in-app, so it never leaves fullscreen) ── */}
      <AnimatePresence>
        {showEndConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
            onClick={cancelEndInterview}
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
                  <h3 className="text-lg font-bold text-gray-900 mb-1">End interview?</h3>
                  <p className="text-sm text-gray-600">
                    Your recorded answers so far will be submitted and this attempt
                    will count. This cannot be undone.
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-6">
                <Button variant="outline" onClick={cancelEndInterview}>
                  Cancel
                </Button>
                <Button
                  onClick={confirmEndInterview}
                  className="bg-red-600 hover:bg-red-700 text-white"
                >
                  End Interview
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <Brain className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900">AI Interview in Progress</h1>
                <p className="text-xs text-gray-600">Question {currentQuestion + 1} of {questions.length}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="bg-orange-50 border border-orange-200 rounded-lg px-3 py-1 flex items-center gap-2">
                <Clock className="w-4 h-4 text-orange-600" />
                <span className="font-mono font-bold text-orange-900 text-sm">{formatTime(timeLeft)}</span>
              </div>
              {isRecording && (
                <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-1">
                  <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse" />
                  <span className="text-sm font-medium text-red-900">Recording</span>
                </div>
              )}
              {/* ── End Interview Button: confirms, then submits the current session ── */}
              <button
                onClick={handleEndInterview}
                className="group bg-red-600 hover:bg-red-700 active:bg-red-800 text-white font-semibold px-4 py-2 rounded-lg flex items-center gap-2 shadow-md hover:shadow-lg hover:shadow-red-200 transition-all duration-200 hover:scale-105 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-2"
                aria-label="End interview early"
              >
                <XCircle className="w-5 h-5 transition-transform duration-200 group-hover:rotate-90" />
                <span className="hidden sm:inline">End Interview</span>
              </button>
            </div>
          </div>
          <div className="mt-2">
            <Progress value={((currentQuestion + 1) / questions.length) * 100} className="h-1.5" />
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {mediaError && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-700">{mediaError}</p>
          </div>
        )}

        <div className="grid lg:grid-cols-3 gap-6">
          {/* Video panel */}
          <div className="lg:col-span-1">
            <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>
              <Card className="border-0 shadow-xl sticky top-24">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <ScanFace className="w-5 h-5 text-blue-600" />
                    Your Video
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {monitoringStatus === 'loading'
                      ? 'Loading AI monitor…'
                      : monitoringStatus === 'calibrating'
                        ? `Calibrating… (${calibrationProgress}%)`
                        : monitoringStatus === 'active'
                          ? 'AI is actively monitoring your behaviour'
                          : monitoringStatus === 'unavailable'
                            ? 'AI monitor unavailable — interview continues'
                            : 'Preparing AI monitor…'}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="relative aspect-video bg-gray-900 rounded-lg overflow-hidden mb-4">
                    <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover transform scale-x-[-1]" />

                    {/* Live / Face detection badge */}
                    <div className="absolute top-2 right-2 flex items-center gap-1.5">
                      {isMonitorReady && (
                        <Badge className={faceDetected ? 'bg-green-500 text-white' : 'bg-red-500 text-white'}>
                          {faceDetected ? <><Eye className="w-3 h-3 mr-1" />Face OK</> : <><EyeOff className="w-3 h-3 mr-1" />No Face</>}
                        </Badge>
                      )}
                      {isMonitorReady && multipleFaces && (
                        <Badge className="bg-red-500 text-white">
                          <AlertTriangle className="w-3 h-3 mr-1" />Multiple
                        </Badge>
                      )}
                      <Badge className="bg-green-500 text-white">Live</Badge>
                    </div>

                    {/* Model loading overlay */}
                    {isMonitorLoading && (
                      <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                        <div className="bg-white/90 backdrop-blur rounded-lg px-4 py-2 flex items-center gap-2">
                          <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                          <span className="text-xs font-medium text-gray-700">Loading face detection model…</span>
                        </div>
                      </div>
                    )}

                    {/* Calibration overlay */}
                    {monitoringStatus === 'calibrating' && (
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-blue-600/80 to-transparent pt-8 pb-2 px-3">
                        <p className="text-white text-xs font-medium text-center">
                          Calibrating ({calibrationProgress}%) — please look straight at the camera
                        </p>
                      </div>
                    )}

                    {/* Warning overlay when scores are critically low */}
                    {monitoringStatus === 'active' && !faceDetected && (
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-red-600/80 to-transparent pt-8 pb-2 px-3">
                        <p className="text-white text-xs font-medium text-center">
                          ⚠ Face not detected — please look at the screen
                        </p>
                      </div>
                    )}

                    {monitoringStatus === 'active' && faceDetected && attentivenessWarning && (
                      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-orange-500/70 to-transparent pt-8 pb-2 px-3">
                        <p className="text-white text-xs font-medium text-center">
                          ⚠ {attentivenessWarning}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Score bars */}
                  <div className="space-y-3">
                    {[
                      { label: 'Attentiveness', value: attentivenessScore, icon: Brain },
                      { label: 'Eye Contact', value: eyeContactScore, icon: Eye },
                    ].map(({ label, value, icon: Icon }) => {
                      const color =
                        value >= 70 ? 'text-green-600' : value >= 40 ? 'text-orange-600' : 'text-red-600';
                      const barColor =
                        value >= 70
                          ? '[&>div]:bg-green-500'
                          : value >= 40
                            ? '[&>div]:bg-orange-500'
                            : '[&>div]:bg-red-500';

                      return (
                        <div key={label}>
                          <div className="flex items-center justify-between text-sm mb-1">
                            <span className="flex items-center gap-1.5 text-gray-600">
                              <Icon className="w-3.5 h-3.5" />{label}
                            </span>
                            <span className={`font-semibold ${color}`}>{value}%</span>
                          </div>
                          <Progress value={value} className={`h-2 ${barColor}`} />
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <p className="text-xs text-blue-800">
                      Camera and microphone are required and must remain enabled during the interview.
                      AI monitors your face position and head direction in real-time.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </div>

          {/* Question + transcript */}
          <div className="lg:col-span-2">
            <motion.div key={currentQuestion} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              <Card className="border-0 shadow-xl mb-6">
                <CardHeader>
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <Badge className={currentQ?.question_type === 'technical' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'}>
                        {currentQ?.category}
                      </Badge>
                      <CardTitle className="text-2xl mt-3">{currentQ?.question_text}</CardTitle>
                    </div>
                  </div>
                  <CardDescription>Take your time and answer clearly in English</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg p-6 min-h-[200px]">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-red-600 rounded-full animate-pulse" />
                        <span className="text-sm font-medium text-gray-700">AI is listening…</span>
                      </div>
                      <Button variant="ghost" size="sm" onClick={handleClearTranscript} disabled={!currentTranscript} className="h-8">
                        <Trash2 className="w-4 h-4 mr-1" />Clear
                      </Button>
                    </div>
                    <p className="text-gray-600 italic">
                      {currentTranscript || interimText
                        ? <>{currentTranscript}<span className="text-gray-400">{interimText}</span></>
                        : 'Start speaking your answer. Your speech will be converted to text in real-time.'}
                    </p>
                  </div>

                  <div className="flex items-center justify-between mt-6">
                    <Button variant="outline" onClick={() => { setInterimText(''); setCurrentQuestion(q => Math.max(0, q - 1)); }} disabled={currentQuestion === 0}>
                      <ArrowLeft className="w-4 h-4 mr-2" />Previous
                    </Button>

                    {currentQuestion === questions.length - 1 ? (
                      <Button onClick={() => handleFinishInterview(false)} size="lg">
                        Finish Interview<CheckCircle2 className="w-5 h-5 ml-2" />
                      </Button>
                    ) : (
                      <Button onClick={handleNextQuestion} size="lg">
                        Next Question<ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Tips */}
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="text-lg">Tips for this Question</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-sm text-gray-700">
                    {currentQ?.question_type === 'technical' ? (
                      <>
                        <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" /><span>Provide specific examples and technical details</span></li>
                        <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" /><span>Explain your reasoning and thought process</span></li>
                        <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" /><span>Mention trade-offs and design considerations</span></li>
                      </>
                    ) : (
                      <>
                        <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-purple-600 flex-shrink-0 mt-0.5" /><span>Use the STAR method (Situation, Task, Action, Result)</span></li>
                        <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-purple-600 flex-shrink-0 mt-0.5" /><span>Be honest and show self-awareness</span></li>
                        <li className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 text-purple-600 flex-shrink-0 mt-0.5" /><span>Highlight what you learned from the experience</span></li>
                      </>
                    )}
                  </ul>
                </CardContent>
              </Card>
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  );
}