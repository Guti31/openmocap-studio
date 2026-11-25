import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Footprints,
  Play,
  RotateCcw,
  Timer,
  Users,
  UserCheck,
  Volume2,
  VolumeX,
  X,
  Zap,
} from 'lucide-react';
import { translations } from '../i18n';
import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';
import type { CalibrationMode, CalibrationState } from '../types/mocap';
import { calibrationAudio } from '../utils/calibrationAudio';

type FlowMode = 'assisted' | 'solo';

const PoseIllustration: React.FC<{ kind: 'tpose' | 'npose' | 'walk' | 'prep' }> = ({ kind }) => (
  <svg viewBox="0 0 140 160" className="w-28 h-32 mx-auto">
    <circle cx="70" cy="24" r="12" fill="none" stroke={kind === 'prep' ? '#f59e0b' : '#22d3ee'} strokeWidth="3.5" />
    <line
      x1="70"
      y1="36"
      x2="70"
      y2="90"
      stroke={kind === 'walk' ? '#10b981' : kind === 'prep' ? '#f59e0b' : '#22d3ee'}
      strokeWidth="4"
      strokeLinecap="round"
    />
    {kind === 'tpose' && (
      <>
        <line x1="20" y1="50" x2="120" y2="50" stroke="#38bdf8" strokeWidth="4" strokeLinecap="round" />
        <line x1="70" y1="90" x2="54" y2="146" stroke="#22d3ee" strokeWidth="4" strokeLinecap="round" />
        <line x1="70" y1="90" x2="86" y2="146" stroke="#22d3ee" strokeWidth="4" strokeLinecap="round" />
      </>
    )}
    {(kind === 'npose' || kind === 'prep') && (
      <>
        <line
          x1="50"
          y1="50"
          x2="90"
          y2="50"
          stroke={kind === 'prep' ? '#fbbf24' : '#38bdf8'}
          strokeWidth="4"
          strokeLinecap="round"
        />
        <line
          x1="50"
          y1="50"
          x2="47"
          y2="98"
          stroke={kind === 'prep' ? '#fbbf24' : '#38bdf8'}
          strokeWidth="4"
          strokeLinecap="round"
        />
        <line
          x1="90"
          y1="50"
          x2="93"
          y2="98"
          stroke={kind === 'prep' ? '#fbbf24' : '#38bdf8'}
          strokeWidth="4"
          strokeLinecap="round"
        />
        <line
          x1="70"
          y1="90"
          x2="58"
          y2="146"
          stroke={kind === 'prep' ? '#f59e0b' : '#22d3ee'}
          strokeWidth="4"
          strokeLinecap="round"
        />
        <line
          x1="70"
          y1="90"
          x2="82"
          y2="146"
          stroke={kind === 'prep' ? '#f59e0b' : '#22d3ee'}
          strokeWidth="4"
          strokeLinecap="round"
        />
      </>
    )}
    {kind === 'walk' && (
      <>
        <line x1="48" y1="50" x2="92" y2="50" stroke="#10b981" strokeWidth="4" strokeLinecap="round" />
        <line x1="48" y1="50" x2="36" y2="90" stroke="#34d399" strokeWidth="4" strokeLinecap="round" />
        <line x1="92" y1="50" x2="108" y2="85" stroke="#34d399" strokeWidth="4" strokeLinecap="round" />
        <line x1="70" y1="90" x2="48" y2="144" stroke="#10b981" strokeWidth="4" strokeLinecap="round" />
        <line x1="70" y1="90" x2="98" y2="140" stroke="#10b981" strokeWidth="4" strokeLinecap="round" />
      </>
    )}
  </svg>
);

const CountdownRing: React.FC<{ progress: number; secondsLeft: number; color: string }> = ({
  progress,
  secondsLeft,
  color,
}) => {
  const r = 46;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - Math.max(0, Math.min(1, progress)));
  const countNum = Math.max(1, Math.ceil(secondsLeft));

  return (
    <div className="relative w-32 h-32 mx-auto flex items-center justify-center">
      <svg className="w-32 h-32 -rotate-90" viewBox="0 0 112 112">
        <circle cx="56" cy="56" r={r} fill="none" stroke="#1e293b" strokeWidth="8" />
        <circle
          cx="56"
          cy="56"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          className="transition-all duration-100"
        />
      </svg>
      <span className="absolute text-4xl font-extrabold font-mono text-white tabular-nums">
        {countNum}
      </span>
    </div>
  );
};

export const CalibrationWizardModal: React.FC = () => {
  const open = useStudioStore((s) => s.calibrationModalOpen);
  const setOpen = useStudioStore((s) => s.setCalibrationModalOpen);
  const locale = useStudioStore((s) => s.locale);
  const advancedMode = useStudioStore((s) => s.advancedMode);
  const calibration = useStudioStore((s) => s.calibration);
  const setCalibration = useStudioStore((s) => s.setCalibration);
  const sensors = useStudioStore((s) => s.sensors);
  const setToast = useStudioStore((s) => s.setToast);

  const [flowMode, setFlowMode] = useState<FlowMode>('assisted');
  const [poseType, setPoseType] = useState<'tpose' | 'npose'>('tpose');
  const [calMode, setCalMode] = useState<CalibrationMode>('full');
  const [busy, setBusy] = useState<boolean>(false);
  const [showTechDetails, setShowTechDetails] = useState<boolean>(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // Audio UI state
  const [muted, setMuted] = useState<boolean>(calibrationAudio.isMuted());
  const [volume, setVolume] = useState<number>(calibrationAudio.getVolume());

  // Solo hands-free state
  const [soloPrepLeft, setSoloPrepLeft] = useState<number | null>(null);
  const [soloPrepTotal, setSoloPrepTotal] = useState<number>(6);
  const [soloWaitingLower, setSoloWaitingLower] = useState<boolean>(false);
  const [soloQuick, setSoloQuick] = useState<boolean>(false);

  const soloActiveRef = useRef<boolean>(false);
  const soloQuickRef = useRef<boolean>(false);
  const flowModeRef = useRef<FlowMode>(flowMode);
  const soloIntervalRef = useRef<number | null>(null);
  const soloTimeoutRef = useRef<number | null>(null);
  const lastBeepSecRef = useRef<number | null>(null);
  const prevStateRef = useRef<CalibrationState>('uncalibrated');

  useEffect(() => {
    flowModeRef.current = flowMode;
  }, [flowMode]);

  const stopSoloTimers = useCallback(() => {
    soloActiveRef.current = false;
    if (soloIntervalRef.current !== null) {
      window.clearInterval(soloIntervalRef.current);
      soloIntervalRef.current = null;
    }
    if (soloTimeoutRef.current !== null) {
      window.clearTimeout(soloTimeoutRef.current);
      soloTimeoutRef.current = null;
    }
    setSoloPrepLeft(null);
    setSoloWaitingLower(false);
  }, []);

  const state: CalibrationState = calibration?.state ?? 'uncalibrated';

  const startStaticCapture = useCallback(
    async (modeOverride: CalibrationMode = 'full', skipVoice = false) => {
      setCalMode(modeOverride);
      setLocalError(null);
      setBusy(true);
      try {
        calibrationAudio.ensureReady();
        if (!skipVoice) {
          calibrationAudio.speak(
            locale === 'es'
              ? poseType === 'tpose'
                ? 'Posición T, mantén los brazos abiertos sin moverte'
                : 'Postura inicial, quédate derecho sin moverte'
              : poseType === 'tpose'
              ? 'T-Pose, hold your arms out horizontally without moving'
              : 'Initial pose, stand still',
            { locale },
          );
        }
        const hw = await api.hardwareStatus();
        if (hw?.drivers?.simulator?.running) {
          await api.configSimulator({ preset: poseType });
          await new Promise((r) => setTimeout(r, 140));
        }
        const nextCal = await api.startStaticCalibration(poseType, 4.0, modeOverride);
        if (nextCal) {
          setCalibration(nextCal);
        }
      } catch (err) {
        const msg = (err as Error).message;
        stopSoloTimers();
        calibrationAudio.playErrorTone();
        setLocalError(msg);
        setToast(msg);
      } finally {
        setBusy(false);
      }
    },
    [locale, poseType, setCalibration, setToast, stopSoloTimers],
  );

  const startStraightCapture = useCallback(
    async (completeAfter = false, skipVoice = false) => {
      setLocalError(null);
      setBusy(true);
      try {
        calibrationAudio.ensureReady();
        if (!skipVoice) {
          calibrationAudio.speak(
            locale === 'es'
              ? 'Posición recta, quédate completamente derecho'
              : 'Straight pose, stand completely straight',
            { locale },
          );
        }
        const hw = await api.hardwareStatus();
        if (hw?.drivers?.simulator?.running) {
          await api.configSimulator({ preset: 'npose' });
          await new Promise((r) => setTimeout(r, 140));
        }
        const nextCal = await api.startStraightCalibration(3.0, completeAfter);
        if (nextCal) {
          setCalibration(nextCal);
        }
      } catch (err) {
        const msg = (err as Error).message;
        stopSoloTimers();
        calibrationAudio.playErrorTone();
        setLocalError(msg);
        setToast(msg);
      } finally {
        setBusy(false);
      }
    },
    [locale, setCalibration, setToast, stopSoloTimers],
  );

  const startWalkCapture = useCallback(
    async (skipVoice = false) => {
      setLocalError(null);
      setBusy(true);
      try {
        calibrationAudio.ensureReady();
        if (!skipVoice) {
          calibrationAudio.speak(
            locale === 'es'
              ? 'Camina en línea recta y regresa'
              : 'Walk in a straight line and return',
            { locale },
          );
        }
        const hw = await api.hardwareStatus();
        if (hw?.drivers?.simulator?.running) {
          await api.configSimulator({ preset: 'walk' });
          await new Promise((r) => setTimeout(r, 140));
        }
        const nextCal = await api.startWalkCalibration(6.0);
        if (nextCal) {
          setCalibration(nextCal);
        }
      } catch (err) {
        const msg = (err as Error).message;
        stopSoloTimers();
        calibrationAudio.playErrorTone();
        setLocalError(msg);
        setToast(msg);
      } finally {
        setBusy(false);
      }
    },
    [locale, setCalibration, setToast, stopSoloTimers],
  );

  // Sincronizar modo del backend
  useEffect(() => {
    if (calibration?.mode && state !== 'uncalibrated' && state !== 'error') {
      setCalMode(calibration.mode);
    }
  }, [calibration?.mode, state]);

  // Limpiar audio/temporizadores al cerrar o desmontar
  useEffect(() => {
    if (!open) {
      stopSoloTimers();
      calibrationAudio.stopAll();
    }
  }, [open, stopSoloTimers]);

  useEffect(() => {
    return () => {
      stopSoloTimers();
      calibrationAudio.stopAll();
    };
  }, [stopSoloTimers]);

  // Motor reactivo de voz/tonos para cuentas regresivas y transiciones de fase (Con Ayuda y Solo)
  useEffect(() => {
    if (!open) return;

    const prev = prevStateRef.current;
    if (prev !== state) {
      prevStateRef.current = state;
      lastBeepSecRef.current = null;

      if (prev === 'capturing_static' && state === 'static_done') {
        calibrationAudio.playPhaseConfirm();
        if (flowModeRef.current === 'solo' && soloActiveRef.current) {
          calibrationAudio.speak(
            locale === 'es'
              ? '¡Posición recta! Baja los brazos y quédate derecho'
              : 'Straight pose! Lower your arms and stand straight',
            { locale },
          );
          setSoloWaitingLower(true);
          soloTimeoutRef.current = window.setTimeout(() => {
            soloTimeoutRef.current = null;
            setSoloWaitingLower(false);
            if (soloActiveRef.current) {
              void startStraightCapture(soloQuickRef.current, true);
            }
          }, 1500);
        } else {
          calibrationAudio.speak(
            locale === 'es' ? 'Listo, baja los brazos' : 'Done, lower your arms',
            { locale },
          );
        }
      } else if (prev === 'capturing_straight' && state === 'straight_done') {
        calibrationAudio.playPhaseConfirm();
        if (flowModeRef.current === 'solo' && soloActiveRef.current) {
          calibrationAudio.speak(
            locale === 'es'
              ? '¡Camina! Camina hacia adelante y regresa'
              : 'Walk! Walk forward and return',
            { locale },
          );
          void startWalkCapture(true);
        } else {
          calibrationAudio.speak(locale === 'es' ? 'Listo' : 'Ready', { locale });
        }
      } else if (
        (prev === 'capturing_static' || prev === 'capturing_straight' || prev === 'capturing_walk') &&
        state === 'calibrated'
      ) {
        const wasSolo = soloActiveRef.current || flowModeRef.current === 'solo';
        stopSoloTimers();
        calibrationAudio.playCompleteChime();
        calibrationAudio.speak(
          locale === 'es'
            ? wasSolo
              ? '¡Alto! Calibración completada con éxito'
              : '¡Alto! Calibración completada'
            : 'Stop! Calibration completed',
          { locale },
        );
      } else if (state === 'error') {
        stopSoloTimers();
        calibrationAudio.playErrorTone();
      }
    }

    if (state === 'capturing_static' || state === 'capturing_straight' || state === 'capturing_walk') {
      const rem = calibration?.remaining_s ?? 0;
      const cap = state === 'capturing_static' ? 4 : state === 'capturing_straight' ? 3 : 6;
      const sec = Math.min(cap, Math.max(1, Math.ceil(rem)));
      if (rem > 0.05 && sec !== lastBeepSecRef.current) {
        lastBeepSecRef.current = sec;
        calibrationAudio.speakCountdown(sec, locale);
      }
    }
  }, [calibration?.remaining_s, locale, open, startStraightCapture, startWalkCapture, state, stopSoloTimers]);

  if (!open) return null;

  const t = translations[locale];
  const progress = calibration?.progress ?? 0;
  const remaining = calibration?.remaining_s ?? 0;
  const activeMode: CalibrationMode =
    state !== 'uncalibrated' && state !== 'error' && calibration?.mode ? calibration.mode : calMode;

  const activeAssignedSensors = sensors.filter(
    (s) => s.status !== 'lost' && s.segment && s.segment !== 'UNASSIGNED',
  );
  const activeSensorCount = activeAssignedSensors.length;
  const backendError =
    state === 'error' || calibration?.ok === false
      ? calibration?.error_es || calibration?.message_es || 'Error durante la calibración.'
      : null;
  const visibleError = localError || backendError;

  const handleToggleMute = () => {
    const nextMuted = !muted;
    calibrationAudio.ensureReady();
    calibrationAudio.setMuted(nextMuted);
    setMuted(nextMuted);
  };

  const handleVolumeChange = (val: number) => {
    calibrationAudio.ensureReady();
    calibrationAudio.setVolume(val);
    setVolume(val);
    if (val > 0 && muted) {
      calibrationAudio.setMuted(false);
      setMuted(false);
    }
  };

  const handleStartSoloSequence = async (quickOnly: boolean) => {
    stopSoloTimers();
    setLocalError(null);
    calibrationAudio.ensureReady();

    if (state !== 'uncalibrated') {
      try {
        const res = await api.resetCalibration();
        if (res) setCalibration(res);
      } catch {
        // continuar
      }
    }

    const prepSec = quickOnly ? 5 : 6;
    setFlowMode('solo');
    flowModeRef.current = 'solo';
    soloActiveRef.current = true;
    soloQuickRef.current = quickOnly;
    setSoloQuick(quickOnly);
    setCalMode(quickOnly ? 'quick' : 'full');
    setSoloPrepTotal(prepSec);
    setSoloPrepLeft(prepSec);

    calibrationAudio.speak(
      locale === 'es'
        ? 'Prepárate, aléjate de la computadora y ponte derecho'
        : 'Get ready, step back from the computer and stand straight',
      { locale },
    );

    const endTs = performance.now() + prepSec * 1000;
    let lastPrepBeep = prepSec + 1;

    soloIntervalRef.current = window.setInterval(() => {
      if (!soloActiveRef.current) return;
      const leftS = Math.max(0, (endTs - performance.now()) / 1000);
      setSoloPrepLeft(leftS);

      const ceilSec = Math.ceil(leftS);
      if (ceilSec >= 1 && ceilSec <= 5 && ceilSec < lastPrepBeep) {
        lastPrepBeep = ceilSec;
        calibrationAudio.speakCountdown(ceilSec, locale);
      }

      if (leftS <= 0.02) {
        if (soloIntervalRef.current !== null) {
          window.clearInterval(soloIntervalRef.current);
          soloIntervalRef.current = null;
        }
        setSoloPrepLeft(null);
        calibrationAudio.playPhaseConfirm();
        calibrationAudio.speak(
          locale === 'es' ? '¡Posición T! Mantén la Posición T' : 'T-Pose! Hold the T-Pose',
          { locale },
        );
        void startStaticCapture(quickOnly ? 'quick' : 'full', true);
      }
    }, 100);
  };

  const handleCompleteQuick = async () => {
    setLocalError(null);
    setBusy(true);
    try {
      calibrationAudio.ensureReady();
      const nextCal = await api.completeQuickCalibration();
      if (nextCal) {
        setCalibration(nextCal);
      }
      calibrationAudio.playCompleteChime();
      calibrationAudio.speak(
        locale === 'es' ? '¡Alto! Calibración completada' : 'Stop! Calibration completed',
        { locale },
      );
    } catch (err) {
      const msg = (err as Error).message;
      calibrationAudio.playErrorTone();
      setLocalError(msg);
      setToast(msg);
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async () => {
    stopSoloTimers();
    calibrationAudio.stopAll();
    setLocalError(null);
    setBusy(true);
    try {
      const nextCal = await api.resetCalibration();
      if (nextCal) {
        setCalibration(nextCal);
      }
    } catch (err) {
      const msg = (err as Error).message;
      setLocalError(msg);
      setToast(msg);
    } finally {
      setBusy(false);
    }
  };

  const handleClose = () => {
    stopSoloTimers();
    calibrationAudio.stopAll();
    setOpen(false);
  };

  const isSoloPrep = soloPrepLeft !== null;
  const showInitialSetup = !isSoloPrep && !soloWaitingLower && (state === 'uncalibrated' || state === 'error');
  const hideWalkStep = (flowMode === 'solo' && soloQuick) || (activeMode === 'quick' && state === 'calibrated' && !calibration?.reports?.PELVIS?.sample_count_walk);

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-[#111827] border border-slate-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Cabecera con control de audio/voz */}
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between gap-3 bg-slate-900/70">
          <h2 className="text-base font-bold text-slate-100">
            {activeMode === 'quick' && state === 'calibrated' ? t.wizardQuickTitle : t.wizardFullTitle}
          </h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleToggleMute}
              title={muted ? t.wizardUnmuteAudio : t.wizardMuteAudio}
              className={`p-1.5 rounded-lg border text-xs transition ${
                muted
                  ? 'bg-slate-800 border-slate-700 text-slate-400'
                  : 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
              }`}
            >
              {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={muted ? 0 : volume}
              onChange={(e) => handleVolumeChange(Number(e.target.value))}
              aria-label="Volumen"
              className="w-16 accent-cyan-400 cursor-pointer"
            />
            <button onClick={handleClose} className="ml-1 text-slate-400 hover:text-white">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Pestañas Modo A (Con Ayuda) vs Modo B (Solo Automática) */}
        <div className="px-5 pt-3 pb-2 bg-slate-950/50 border-b border-slate-800 grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={isSoloPrep || soloWaitingLower || state === 'capturing_static' || state === 'capturing_straight' || state === 'capturing_walk'}
            onClick={() => setFlowMode('assisted')}
            className={`px-3 py-2 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition ${
              flowMode === 'assisted'
                ? 'bg-cyan-500/20 border-cyan-400 text-cyan-200'
                : 'bg-slate-900/70 border-slate-800 text-slate-400 hover:border-slate-600'
            }`}
          >
            <Users className="w-4 h-4" />
            <span>{t.wizardModeAssistedTab}</span>
          </button>
          <button
            type="button"
            disabled={isSoloPrep || soloWaitingLower || state === 'capturing_static' || state === 'capturing_straight' || state === 'capturing_walk'}
            onClick={() => setFlowMode('solo')}
            className={`px-3 py-2 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition ${
              flowMode === 'solo'
                ? 'bg-amber-500/20 border-amber-400 text-amber-200'
                : 'bg-slate-900/70 border-slate-800 text-slate-400 hover:border-slate-600'
            }`}
          >
            <Timer className="w-4 h-4" />
            <span>{t.wizardModeSoloTab}</span>
          </button>
        </div>

        {/* Barra superior de etapas */}
        <div
          className={`px-5 py-2.5 bg-slate-950/70 border-b border-slate-800 grid ${
            hideWalkStep ? 'grid-cols-3' : 'grid-cols-4'
          } gap-2 text-center text-[11px] font-medium`}
        >
          <div
            className={
              isSoloPrep || showInitialSetup || state === 'capturing_static'
                ? 'text-cyan-300 font-bold'
                : 'text-emerald-400'
            }
          >
            1. Posición T (4 s)
          </div>
          <div
            className={
              soloWaitingLower || state === 'static_done' || state === 'capturing_straight'
                ? 'text-cyan-300 font-bold'
                : state === 'straight_done' || state === 'capturing_walk' || state === 'calibrated'
                ? 'text-emerald-400'
                : 'text-slate-500'
            }
          >
            {t.wizardStepStraight}
          </div>
          {!hideWalkStep && (
            <div
              className={
                state === 'straight_done' || state === 'capturing_walk'
                  ? 'text-cyan-300 font-bold'
                  : state === 'calibrated'
                  ? 'text-emerald-400'
                  : 'text-slate-500'
              }
            >
              {t.wizardStepWalk3}
            </div>
          )}
          <div className={state === 'calibrated' ? 'text-emerald-400 font-bold' : 'text-slate-500'}>
            {hideWalkStep ? `3. ${t.wizardStepReady}` : `4. ${t.wizardStepReady}`}
          </div>
        </div>

        <div className="p-6 overflow-y-auto space-y-4 text-center">
          {/* Banner de error explícito */}
          {visibleError && (
            <div className="p-3.5 rounded-xl bg-rose-950/80 border border-rose-500/70 text-left flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div className="flex-1 space-y-2">
                <p className="text-xs font-bold text-rose-200">{t.wizardErrorTitle}</p>
                <p className="text-xs text-rose-100 leading-relaxed">{visibleError}</p>
                <button
                  type="button"
                  disabled={busy}
                  onClick={handleReset}
                  className="px-3 py-1 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-semibold"
                >
                  {t.wizardRetryBtn}
                </button>
              </div>
            </div>
          )}

          {/* Preparación Solo (Modo B) */}
          {isSoloPrep && (
            <div className="py-4 space-y-4">
              <PoseIllustration kind="prep" />
              <CountdownRing
                progress={(soloPrepTotal - (soloPrepLeft ?? 0)) / Math.max(1, soloPrepTotal)}
                secondsLeft={soloPrepLeft ?? 0}
                color="#f59e0b"
              />
              <p className="text-base font-bold text-amber-300">
                Prepárate, aléjate de la computadora y ponte derecho...
              </p>
              <p className="text-xs text-slate-300">
                Al terminar la cuenta regresiva escucharás &ldquo;¡Posición T!&rdquo; y comenzará la captura automáticamente.
              </p>
              <button
                type="button"
                onClick={handleReset}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs text-slate-200"
              >
                {t.wizardCancelSeqBtn}
              </button>
            </div>
          )}

          {/* Transición automática de bajar brazos entre T-Pose y Recta (Modo B Solo) */}
          {soloWaitingLower && (
            <div className="py-5 space-y-4">
              <PoseIllustration kind="npose" />
              <p className="text-lg font-bold text-cyan-300">
                ¡Posición recta! Baja los brazos y quédate derecho...
              </p>
              <p className="text-xs text-slate-400">
                Iniciando captura de postura recta en 1.5 segundos...
              </p>
              <button
                type="button"
                onClick={handleReset}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs text-slate-200"
              >
                {t.wizardCancelSeqBtn}
              </button>
            </div>
          )}

          {/* Pantalla inicial según pestaña elegida */}
          {showInitialSetup && (
            <div className="space-y-4">
              <PoseIllustration kind={poseType} />
              <p className="text-sm font-semibold text-slate-100 leading-snug max-w-lg mx-auto">
                {flowMode === 'assisted'
                  ? locale === 'es'
                    ? 'Un asistente controla cada fase paso a paso con voz y tonos: 1) Posición T (4 s), 2) Posición Recta (3 s) y 3) Caminata (6 s).'
                    : 'An assistant triggers each phase step-by-step with voice guidance: 1) T-Pose (4 s), 2) Straight Pose (3 s), 3) Walk (6 s).'
                  : locale === 'es'
                  ? 'Modo manos libres para calibrar solo: incluye temporizador de preparación, voz en español y bips en cada segundo.'
                  : 'Hands-free solo mode with preparation countdown, voice prompts, and audible second beeps.'}
              </p>

              {/* Indicador de sensores activos */}
              <div
                className={`text-xs px-3 py-1.5 rounded-lg border inline-flex items-center gap-2 ${
                  activeSensorCount > 0
                    ? 'bg-emerald-950/40 border-emerald-700/60 text-emerald-300'
                    : 'bg-amber-950/40 border-amber-700/60 text-amber-300'
                }`}
              >
                <span>
                  {activeSensorCount > 0
                    ? `${activeSensorCount} ${locale === 'es' ? 'sensor(es) activos listos (traje parcial o completo 1–17+)' : 'active sensor(s) ready (partial or full suit 1–17+)'}`
                    : locale === 'es'
                    ? 'Sin sensores transmitiendo aún: conecta la antena o activa el simulador'
                    : 'No sensors streaming yet: connect antenna or start virtual demo'}
                </span>
              </div>

              {flowMode === 'assisted' ? (
                <div className="space-y-3">
                  <div className="flex justify-center gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => setPoseType('tpose')}
                      className={`px-3 py-1 rounded-full border ${
                        poseType === 'tpose'
                          ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300 font-semibold'
                          : 'bg-slate-900 border-slate-700 text-slate-400'
                      }`}
                    >
                      {t.wizardTposeOpt}
                    </button>
                    <button
                      type="button"
                      onClick={() => setPoseType('npose')}
                      className={`px-3 py-1 rounded-full border ${
                        poseType === 'npose'
                          ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300 font-semibold'
                          : 'bg-slate-900 border-slate-700 text-slate-400'
                      }`}
                    >
                      {t.wizardNposeOpt}
                    </button>
                  </div>

                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void startStaticCapture('full')}
                    className="w-full py-3.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-cyan-600/25"
                  >
                    <Play className="w-4 h-4 fill-current" />
                    <span>{t.wizardAssistedPhase1Btn}</span>
                  </button>
                </div>
              ) : (
                <div className="space-y-2.5">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleStartSoloSequence(false)}
                    className="w-full py-3.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-amber-600/25"
                  >
                    <Timer className="w-4 h-4" />
                    <span>{t.wizardSoloStartBtn}</span>
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleStartSoloSequence(true)}
                    className="w-full py-2.5 rounded-xl bg-emerald-600/90 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center justify-center gap-2"
                  >
                    <Zap className="w-4 h-4" />
                    <span>{t.wizardSoloQuickBtn}</span>
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Captura Estática Fase 1 (Posición T 4 s) */}
          {!isSoloPrep && !soloWaitingLower && state === 'capturing_static' && (
            <div className="py-4 space-y-4">
              <PoseIllustration kind={poseType} />
              <CountdownRing progress={progress} secondsLeft={remaining} color="#06b6d4" />
              <p className="text-base font-semibold text-cyan-300">
                {poseType === 'tpose'
                  ? 'Mantén la Posición T (brazos horizontales sin moverte)...'
                  : 'Mantente quieto en postura N...'}
              </p>
              <p className="text-xs text-slate-400">
                Capturando muestras reales de {calibration?.active_sensors_captured ?? activeSensorCount} sensor(es)...
              </p>
              {flowMode === 'solo' && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs text-slate-200"
                >
                  {t.wizardCancelSeqBtn}
                </button>
              )}
            </div>
          )}

          {/* Paso intermedio Con Ayuda tras Fase 1: lanzar Fase 2 Posición Recta (3 s) */}
          {!isSoloPrep && !soloWaitingLower && state === 'static_done' && (
            <div className="space-y-4">
              <PoseIllustration kind="npose" />
              <div className="text-xs px-3 py-1.5 rounded-lg bg-emerald-950/50 border border-emerald-700/60 text-emerald-300 inline-block">
                Fase 1 (Posición T) guardada ({calibration?.calibrated_segments ?? 0} sensor(es) · calidad{' '}
                {calibration?.overall_quality_pct ?? 100}% · balanceo ±{calibration?.max_static_std_deg ?? 0}°)
              </div>
              <p className="text-base font-semibold text-slate-100 leading-snug max-w-md mx-auto">
                Baja los brazos a los costados, ponte completamente derecho mirando al frente e inicia la Fase 2.
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={() => void startStraightCapture(false)}
                className="w-full py-3.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-cyan-600/25"
              >
                <UserCheck className="w-4 h-4" />
                <span>{t.wizardAssistedPhase2Btn}</span>
              </button>
            </div>
          )}

          {/* Captura Fase 2: Posición Recta (3 s) */}
          {!isSoloPrep && !soloWaitingLower && state === 'capturing_straight' && (
            <div className="py-4 space-y-4">
              <PoseIllustration kind="npose" />
              <CountdownRing progress={progress} secondsLeft={remaining} color="#38bdf8" />
              <p className="text-base font-semibold text-sky-300">
                Posición recta: quédate completamente derecho con los brazos abajo...
              </p>
              <p className="text-xs text-slate-400">
                Alineando cero vertical de columna, escápulas y brazos ({calibration?.active_sensors_captured ?? activeSensorCount} sensor(es))...
              </p>
              {flowMode === 'solo' && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs text-slate-200"
                >
                  {t.wizardCancelSeqBtn}
                </button>
              )}
            </div>
          )}

          {/* Paso intermedio Con Ayuda tras Fase 2: lanzar Fase 3 Caminata (6 s) */}
          {!isSoloPrep && !soloWaitingLower && state === 'straight_done' && (
            <div className="space-y-4">
              <PoseIllustration kind="walk" />
              <div className="text-xs px-3 py-1.5 rounded-lg bg-emerald-950/50 border border-emerald-700/60 text-emerald-300 inline-block">
                Posición Recta anclada ({calibration?.calibrated_segments ?? 0} sensor(es) · calidad{' '}
                {calibration?.overall_quality_pct ?? 100}%)
              </div>
              <p className="text-base font-semibold text-slate-100 leading-snug max-w-md mx-auto">
                {t.walkDesc}
              </p>
              <div className="space-y-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void startWalkCapture(false)}
                  className="w-full py-3.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/25"
                >
                  <Footprints className="w-4 h-4" />
                  <span>{t.wizardAssistedPhase3Btn}</span>
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={handleCompleteQuick}
                  className="w-full py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-200 font-semibold text-xs flex items-center justify-center gap-1.5"
                >
                  <Zap className="w-3.5 h-3.5 text-emerald-400" />
                  <span>{t.wizardSkipWalkBtn}</span>
                </button>
              </div>
            </div>
          )}

          {/* Captura Fase 3: Caminata (6 s) */}
          {!isSoloPrep && !soloWaitingLower && state === 'capturing_walk' && (
            <div className="py-4 space-y-4">
              <PoseIllustration kind="walk" />
              <CountdownRing progress={progress} secondsLeft={remaining} color="#10b981" />
              <p className="text-base font-semibold text-emerald-300">
                Camina naturalmente en línea recta y regresa...
              </p>
              {flowMode === 'solo' && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs text-slate-200"
                >
                  {t.wizardCancelSeqBtn}
                </button>
              )}
            </div>
          )}

          {/* Paso Final: Confirmación visual */}
          {!isSoloPrep && !soloWaitingLower && state === 'calibrated' && (
            <div className="space-y-4 py-2">
              <div className="w-16 h-16 rounded-full bg-emerald-500/20 border-2 border-emerald-400 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-10 h-10 text-emerald-400" />
              </div>
              <h3 className="text-xl font-extrabold text-emerald-300">
                {t.wizardDoneTitle}
              </h3>
              <p className="text-xs text-slate-300">
                {calibration?.mode === 'quick'
                  ? calibration?.straight_anchored
                    ? 'Calibración rápida (T-Pose + Posición Recta)'
                    : 'Calibración rápida (Solo T-Pose)'
                  : 'Calibración completa (T-Pose + Posición Recta + Caminata 360°)'}{' '}
                aplicada a {calibration?.calibrated_segments ?? 0} sensor(es) (precisión:{' '}
                {calibration?.overall_quality_pct ?? 100}%).
              </p>

              {(advancedMode || showTechDetails) && (
                <div className="max-h-48 overflow-y-auto border border-slate-800 rounded-lg text-left">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-900 text-slate-400 sticky top-0">
                      <tr>
                        <th className="px-3 py-1.5">Segmento</th>
                        <th className="px-3 py-1.5">Calidad</th>
                        <th className="px-3 py-1.5">Recto</th>
                        <th className="px-3 py-1.5">Rumbo</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80 font-mono">
                      {Object.values(calibration?.reports ?? {}).map((rep) => (
                        <tr key={rep.segment}>
                          <td className="px-3 py-1 text-slate-200">{rep.segment}</td>
                          <td className="px-3 py-1 text-emerald-400">{rep.quality_pct.toFixed(1)}%</td>
                          <td className="px-3 py-1 text-slate-300">
                            {(rep.straight_residual_deg ?? rep.static_std_deg).toFixed(2)}°
                          </td>
                          <td className="px-3 py-1 text-cyan-300">{rep.yaw_correction_deg.toFixed(2)}°</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {!advancedMode && (
                <button
                  type="button"
                  onClick={() => setShowTechDetails(!showTechDetails)}
                  className="text-[11px] text-slate-400 hover:text-slate-200 inline-flex items-center gap-1"
                >
                  <ChevronDown className="w-3 h-3" />
                  <span>{showTechDetails ? 'Ocultar detalle por sensor' : 'Ver detalle por sensor'}</span>
                </button>
              )}
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/60 flex items-center justify-between">
          <button
            type="button"
            disabled={busy}
            onClick={handleReset}
            className="px-3 py-1.5 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{t.recalibrate}</span>
          </button>
          <button
            type="button"
            onClick={handleClose}
            className="px-5 py-2 rounded-lg text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-white"
          >
            {state === 'calibrated' ? t.wizardReadyToRecordBtn : t.close}
          </button>
        </div>
      </div>
    </div>
  );
};
