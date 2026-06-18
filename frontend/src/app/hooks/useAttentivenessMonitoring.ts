import { RefObject, useEffect, useRef, useState } from 'react';
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision';
import { toast } from 'sonner';

export type MonitoringStatus =
  | 'idle'
  | 'loading'
  | 'calibrating'
  | 'active'
  | 'unavailable';

// ── Asset sources: LOCAL first, CDN fallback (versions pinned!) ───────────────
const WASM_SOURCES = [
  '/models/wasm',
  'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/wasm',
];
const MODEL_SOURCES = [
  '/models/face_landmarker.task',
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
];
const DELEGATES: Array<'GPU' | 'CPU'> = ['GPU', 'CPU'];

// ── Timing ────────────────────────────────────────────────────────────────────
const SAMPLE_INTERVAL_MS = 800;

// ── Calibration ───────────────────────────────────────────────────────────────
const CALIBRATION_REQUIRED_SAMPLES = 4;
const CALIBRATION_TIMEOUT_MS = 12000; // never hang in 'calibrating'
const CALIBRATION_MAX_HEAD_OFFSET = 0.45;
const CALIBRATION_MAX_EYE_LOOK_AWAY = 0.45;

// ── Active-phase tolerances (deviation from baseline) ─────────────────────────
const FACE_CENTER_TOLERANCE_X = 0.22;
const FACE_CENTER_TOLERANCE_Y = 0.25;
const HEAD_TURN_TOLERANCE = 0.35;
const EYE_LOOK_AWAY_DELTA = 0.30; // gaze deviation above resting baseline

// ── Live meter smoothing (EMA of pass/fail per frame) ─────────────────────────
const LIVE_ALPHA = 0.3;

// ── Warning streaks (in samples; at 800 ms → ×0.8 s) ──────────────────────────
const NO_FACE_WARN_STREAK = 6;       // ~4.8 s
const MULTI_FACE_WARN_STREAK = 3;    // ~2.4 s
const LOW_EYE_CONTACT_WARN_STREAK = 6;

// ── Types ─────────────────────────────────────────────────────────────────────
export type MonitoringPhase = 'idle' | 'preflight' | 'scoring';

interface UseAttentivenessMonitoringArgs {
  /**
   * 'idle'      → monitoring off; the model is not loaded.
   * 'preflight' → load the model and run detection so the UI can confirm the
   *               camera pipeline works BEFORE the interview is allowed to
   *               start. Frames do NOT count toward the session grade and
   *               proctoring warnings are suppressed.
   * 'scoring'   → full monitoring: the session grade accumulates and warnings
   *               fire. Switching preflight → scoring resets the grade and
   *               re-runs calibration for the real attempt.
   */
  phase: MonitoringPhase;
  videoRef: RefObject<HTMLVideoElement | null>;
}

export interface AttentivenessMonitoringResult {
  /** Live, recency-weighted meter for the UI bars (0–100). */
  attentivenessScore: number;
  eyeContactScore: number;
  /** Cumulative session grade for submission (0–100). */
  sessionAttentiveness: number;
  sessionEyeContact: number;
  faceDetected: boolean;
  multipleFaces: boolean;
  monitoringStatus: MonitoringStatus;
  calibrationProgress: number;
  warning: string | null;
}

type FrameReason = 'ok' | 'no_face' | 'multiple_faces' | 'low_eye_contact';

interface RawFrame {
  reason: 'ok' | 'no_face' | 'multiple_faces';
  faceCenterX?: number;
  faceCenterY?: number;
  signedHeadOffset?: number;
  eyeLookAwayScore?: number;
}

interface Baseline {
  faceCenterX: number;
  faceCenterY: number;
  signedHeadOffset: number;
  eyeLookAway: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function clampScore(score: number) {
  return Math.max(0, Math.min(100, Math.round(score)));
}

function getMaxEyeLookAwayScore(categories: any[]): number {
  return categories.reduce((max, item) => {
    const name: string = item.categoryName || item.displayName || '';
    const isEyeLook = name.startsWith('eyeLook') && !name.toLowerCase().includes('blink');
    return isEyeLook ? Math.max(max, item.score || 0) : max;
  }, 0);
}

function analyseRawFrame(result: any): RawFrame {
  const faces = result.faceLandmarks || [];
  if (faces.length === 0) return { reason: 'no_face' };
  if (faces.length > 1) return { reason: 'multiple_faces' };

  const landmarks = faces[0];
  let minX = 1, maxX = 0, minY = 1, maxY = 0;
  for (const p of landmarks) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const faceCenterX = (minX + maxX) / 2;
  const faceCenterY = (minY + maxY) / 2;

  const nose = landmarks[1];
  const leftEye = landmarks[33];
  const rightEye = landmarks[263];
  let signedHeadOffset = 0;
  if (nose && leftEye && rightEye) {
    const eyeMidX = (leftEye.x + rightEye.x) / 2;
    const eyeDistance = Math.abs(rightEye.x - leftEye.x) || 0.01;
    signedHeadOffset = (nose.x - eyeMidX) / eyeDistance;
  }

  const blend = result.faceBlendshapes?.[0]?.categories || [];
  const eyeLookAwayScore = getMaxEyeLookAwayScore(blend);

  return { reason: 'ok', faceCenterX, faceCenterY, signedHeadOffset, eyeLookAwayScore };
}

function isGoodCalibrationFrame(f: RawFrame): boolean {
  if (f.reason !== 'ok') return false;
  const cx = f.faceCenterX ?? 0.5;
  const cy = f.faceCenterY ?? 0.5;
  const head = f.signedHeadOffset ?? 1;
  const gaze = f.eyeLookAwayScore ?? 1;
  const centered = cx > 0.2 && cx < 0.8 && cy > 0.15 && cy < 0.85;
  const straight = Math.abs(head) < CALIBRATION_MAX_HEAD_OFFSET;
  const forward = gaze < CALIBRATION_MAX_EYE_LOOK_AWAY;
  return centered && straight && forward;
}

function classifyFrame(
  f: RawFrame,
  b: Baseline,
): { attentive: boolean; eyeContact: boolean; reason: FrameReason } {
  if (f.reason === 'no_face') return { attentive: false, eyeContact: false, reason: 'no_face' };
  if (f.reason === 'multiple_faces') return { attentive: false, eyeContact: false, reason: 'multiple_faces' };

  const cx = f.faceCenterX ?? b.faceCenterX;
  const cy = f.faceCenterY ?? b.faceCenterY;
  const head = f.signedHeadOffset ?? b.signedHeadOffset;
  const gaze = f.eyeLookAwayScore ?? 1;

  const faceCentered =
    Math.abs(cx - b.faceCenterX) < FACE_CENTER_TOLERANCE_X &&
    Math.abs(cy - b.faceCenterY) < FACE_CENTER_TOLERANCE_Y;
  const headStraight = Math.abs(head - b.signedHeadOffset) < HEAD_TURN_TOLERANCE;
  const eyesForward =
    gaze < 0.55 &&
    gaze - b.eyeLookAway < EYE_LOOK_AWAY_DELTA;

  const attentive = faceCentered && headStraight;     // presence + head
  const eyeContact = attentive && eyesForward;         // + eyes on camera

  return { attentive, eyeContact, reason: eyeContact ? 'ok' : 'low_eye_contact' };
}

// ── Model loading (bundled runtime; local-first assets; GPU→CPU) ──────────────
async function createFaceLandmarker(): Promise<FaceLandmarker> {
  const common = {
    runningMode: 'VIDEO' as const,
    numFaces: 2,
    outputFaceBlendshapes: true,
    minFaceDetectionConfidence: 0.5,
    minFacePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  };

  let lastErr: unknown = null;
  for (const wasm of WASM_SOURCES) {
    let vision: any;
    try {
      vision = await FilesetResolver.forVisionTasks(wasm);
    } catch (e) {
      lastErr = e;
      continue;
    }
    for (const model of MODEL_SOURCES) {
      for (const delegate of DELEGATES) {
        try {
          const lm = await FaceLandmarker.createFromOptions(vision, {
            ...common,
            baseOptions: { modelAssetPath: model, delegate },
          });
          console.info(`[Attentiveness] model loaded (wasm=${wasm.startsWith('/') ? 'local' : 'cdn'}, delegate=${delegate})`);
          return lm;
        } catch (e) {
          lastErr = e;
        }
      }
    }
  }
  throw lastErr ?? new Error('Could not initialise FaceLandmarker');
}

// ── Hook ──────────────────────────────────────────────────────────────────────
export function useAttentivenessMonitoring({
  phase,
  videoRef,
}: UseAttentivenessMonitoringArgs): AttentivenessMonitoringResult {
  const [attentivenessScore, setAttentivenessScore] = useState(100);
  const [eyeContactScore, setEyeContactScore] = useState(100);
  const [sessionAttentiveness, setSessionAttentiveness] = useState(100);
  const [sessionEyeContact, setSessionEyeContact] = useState(100);
  const [faceDetected, setFaceDetected] = useState(true);
  const [multipleFaces, setMultipleFaces] = useState(false);
  const [monitoringStatus, setMonitoringStatus] = useState<MonitoringStatus>('idle');
  const [calibrationProgress, setCalibrationProgress] = useState(0);
  const [warning, setWarning] = useState<string | null>(null);

  const landmarkerRef = useRef<FaceLandmarker | null>(null);

  const calSamplesRef = useRef<Baseline[]>([]);
  const calStartRef = useRef(0);
  const baselineRef = useRef<Baseline | null>(null);

  const liveAttRef = useRef(100);
  const liveEcRef = useRef(100);

  const statsRef = useRef({
    total: 0,
    attentive: 0,
    eyeContact: 0,
    noFaceStreak: 0,
    multiFaceStreak: 0,
    lowEcStreak: 0,
    warnedNoFace: false,
    warnedMulti: false,
    warnedEc: false,
  });

  // Close the model only on unmount.
  useEffect(() => {
    return () => {
      landmarkerRef.current?.close();
      landmarkerRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (phase === 'idle') {
      setMonitoringStatus('idle');
      return;
    }

    // Only the real interview ('scoring') counts toward the session grade and
    // surfaces proctoring warnings. 'preflight' merely proves the pipeline can
    // load so the setup screen can unblock the Start button.
    const isScoring = phase === 'scoring';

    let cancelled = false;
    let intervalId: number | undefined;

    const reset = () => {
      calSamplesRef.current = [];
      baselineRef.current = null;
      calStartRef.current = performance.now();
      liveAttRef.current = 100;
      liveEcRef.current = 100;
      statsRef.current = {
        total: 0, attentive: 0, eyeContact: 0,
        noFaceStreak: 0, multiFaceStreak: 0, lowEcStreak: 0,
        warnedNoFace: false, warnedMulti: false, warnedEc: false,
      };
      setAttentivenessScore(100);
      setEyeContactScore(100);
      setSessionAttentiveness(100);
      setSessionEyeContact(100);
      setFaceDetected(true);
      setMultipleFaces(false);
      setCalibrationProgress(0);
      setWarning(null);
    };

    const finalizeCalibration = () => {
      const s = calSamplesRef.current;
      baselineRef.current = s.length
        ? {
          faceCenterX: s.reduce((a, b) => a + b.faceCenterX, 0) / s.length,
          faceCenterY: s.reduce((a, b) => a + b.faceCenterY, 0) / s.length,
          signedHeadOffset: s.reduce((a, b) => a + b.signedHeadOffset, 0) / s.length,
          eyeLookAway: s.reduce((a, b) => a + b.eyeLookAway, 0) / s.length,
        }
        : // No good frames captured before timeout → neutral default so we never hang.
        { faceCenterX: 0.5, faceCenterY: 0.5, signedHeadOffset: 0, eyeLookAway: 0.1 };

      statsRef.current.total = 0;
      statsRef.current.attentive = 0;
      statsRef.current.eyeContact = 0;
      setAttentivenessScore(100);
      setEyeContactScore(100);
      setSessionAttentiveness(100);
      setSessionEyeContact(100);
      setCalibrationProgress(100);
      setMonitoringStatus('active');
    };

    const sample = () => {
      if (cancelled) return;
      const video = videoRef.current;
      const lm = landmarkerRef.current;
      if (!video || !lm || video.readyState < 2) return;

      const result = lm.detectForVideo(video, performance.now());
      const raw = analyseRawFrame(result);

      setFaceDetected(raw.reason !== 'no_face');
      setMultipleFaces(raw.reason === 'multiple_faces');

      // ── Calibration phase ──
      if (!baselineRef.current) {
        if (isGoodCalibrationFrame(raw)) {
          calSamplesRef.current.push({
            faceCenterX: raw.faceCenterX ?? 0.5,
            faceCenterY: raw.faceCenterY ?? 0.5,
            signedHeadOffset: raw.signedHeadOffset ?? 0,
            eyeLookAway: raw.eyeLookAwayScore ?? 0.1,
          });
          setCalibrationProgress(
            clampScore((calSamplesRef.current.length / CALIBRATION_REQUIRED_SAMPLES) * 100),
          );
        }

        const timedOut = performance.now() - calStartRef.current > CALIBRATION_TIMEOUT_MS;
        if (calSamplesRef.current.length >= CALIBRATION_REQUIRED_SAMPLES || timedOut) {
          finalizeCalibration();
        }
        return;
      }

      // ── Active phase ──
      const frame = classifyFrame(raw, baselineRef.current);
      const st = statsRef.current;
      st.total += 1;
      if (frame.attentive) st.attentive += 1;
      if (frame.eyeContact) st.eyeContact += 1;

      // streak bookkeeping
      if (frame.reason === 'no_face') st.noFaceStreak += 1;
      else { st.noFaceStreak = 0; st.warnedNoFace = false; }

      if (frame.reason === 'multiple_faces') st.multiFaceStreak += 1;
      else { st.multiFaceStreak = 0; st.warnedMulti = false; }

      if (raw.reason === 'ok' && !frame.eyeContact) st.lowEcStreak += 1;
      else if (frame.eyeContact) { st.lowEcStreak = 0; st.warnedEc = false; }

      // live meters (responsive EMA of pass/fail)
      liveAttRef.current = liveAttRef.current * (1 - LIVE_ALPHA) + (frame.attentive ? 100 : 0) * LIVE_ALPHA;
      liveEcRef.current = liveEcRef.current * (1 - LIVE_ALPHA) + (frame.eyeContact ? 100 : 0) * LIVE_ALPHA;
      setAttentivenessScore(clampScore(liveAttRef.current));
      setEyeContactScore(clampScore(liveEcRef.current));

      // cumulative session grades (submit these)
      setSessionAttentiveness(clampScore((st.attentive / st.total) * 100));
      setSessionEyeContact(clampScore((st.eyeContact / st.total) * 100));

      // live warning string for the overlay + debounced toasts
      let w: string | null = null;
      if (frame.reason === 'no_face') {
        w = 'No face detected — please look at the screen';
        if (st.noFaceStreak >= NO_FACE_WARN_STREAK && !st.warnedNoFace) {
          st.warnedNoFace = true;
          if (isScoring) toast.warning('Please stay clearly visible on camera.');
        }
      } else if (frame.reason === 'multiple_faces') {
        w = 'Multiple faces detected — please stay alone during the interview';
        if (st.multiFaceStreak >= MULTI_FACE_WARN_STREAK && !st.warnedMulti) {
          st.warnedMulti = true;
          if (isScoring) toast.warning('Multiple faces detected. Please stay alone during the interview.');
        }
      } else if (!frame.eyeContact) {
        w = 'Try to keep your eyes on the camera';
        if (st.lowEcStreak >= LOW_EYE_CONTACT_WARN_STREAK && !st.warnedEc) {
          st.warnedEc = true;
          if (isScoring) toast.warning('Please maintain attention toward the interview screen.');
        }
      }
      setWarning(w);
    };

    const start = async () => {
      try {
        reset();
        setMonitoringStatus('loading');
        if (!landmarkerRef.current) {
          landmarkerRef.current = await createFaceLandmarker();
        }
        if (cancelled) return;
        calStartRef.current = performance.now();
        setMonitoringStatus('calibrating');
        sample();
        intervalId = window.setInterval(sample, SAMPLE_INTERVAL_MS);
      } catch (err) {
        console.error('[Attentiveness] monitoring failed:', err);
        setMonitoringStatus('unavailable');
        toast.error('Attentiveness monitoring could not start.');
      }
    };

    start();

    return () => {
      cancelled = true;
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [phase, videoRef]);

  return {
    attentivenessScore,
    eyeContactScore,
    sessionAttentiveness,
    sessionEyeContact,
    faceDetected,
    multipleFaces,
    monitoringStatus,
    calibrationProgress,
    warning,
  };
}