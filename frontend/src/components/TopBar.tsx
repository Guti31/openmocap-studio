import React, { useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  Circle,
  Download,
  Globe,
  PanelLeft,
  PanelRight,
  Radio,
  RefreshCw,
  Sliders,
  SlidersHorizontal,
  Square,
  UserCheck,
  Video,
  VideoOff,
} from 'lucide-react';
import { translations } from '../i18n';
import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';
import { cancelGuidedTakeSequence, toggleGuidedTakeRecording } from '../utils/studioRecorder';

interface TopBarProps {
  onToggleVideoRecord: () => void;
}

function formatChrono(secondsFloat: number): string {
  const total = Math.max(0, Math.floor(secondsFloat));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export const TopBar: React.FC<TopBarProps> = ({ onToggleVideoRecord }) => {
  const locale = useStudioStore((s) => s.locale);
  const setLocale = useStudioStore((s) => s.setLocale);
  const advancedMode = useStudioStore((s) => s.advancedMode);
  const setAdvancedMode = useStudioStore((s) => s.setAdvancedMode);
  const connected = useStudioStore((s) => s.connected);
  const streamHz = useStudioStore((s) => s.streamHz);
  const profiles = useStudioStore((s) => s.profiles);
  const activeProfile = useStudioStore((s) => s.activeProfile);
  const setProfiles = useStudioStore((s) => s.setProfiles);
  const sensors = useStudioStore((s) => s.sensors);
  const calibration = useStudioStore((s) => s.calibration);
  const recording = useStudioStore((s) => s.recording);
  const awinda = useStudioStore((s) => s.awinda);
  const simulatorActive = useStudioStore((s) => s.simulatorActive);
  const leftPanelOpen = useStudioStore((s) => s.leftPanelOpen);
  const rightPanelOpen = useStudioStore((s) => s.rightPanelOpen);
  const toggleLeftPanel = useStudioStore((s) => s.toggleLeftPanel);
  const toggleRightPanel = useStudioStore((s) => s.toggleRightPanel);
  const isVideoRecording = useStudioStore((s) => s.isVideoRecording);
  const overlayHudInVideo = useStudioStore((s) => s.overlayHudInVideo);
  const setOverlayHudInVideo = useStudioStore((s) => s.setOverlayHudInVideo);
  const studioTposeRecording = useStudioStore((s) => s.studioTposeRecording);
  const setStudioTposeRecording = useStudioStore((s) => s.setStudioTposeRecording);
  const recordingTposePhase = useStudioStore((s) => s.recordingTposePhase);
  const setCalibrationModalOpen = useStudioStore((s) => s.setCalibrationModalOpen);
  const setProfileModalOpen = useStudioStore((s) => s.setProfileModalOpen);
  const setExportModalOpen = useStudioStore((s) => s.setExportModalOpen);
  const setToast = useStudioStore((s) => s.setToast);

  const [recElapsedS, setRecElapsedS] = useState<number>(0);
  const [checkingUpdate, setCheckingUpdate] = useState<boolean>(false);

  const t = translations[locale];
  const isCalibrated = calibration?.state === 'calibrated';
  const isTakeRecording = Boolean(recording?.is_recording);

  useEffect(() => {
    return () => cancelGuidedTakeSequence();
  }, []);

  useEffect(() => {
    if (!isTakeRecording) {
      setRecElapsedS(0);
      return;
    }
    const startMs = Date.now();
    const timer = window.setInterval(() => {
      setRecElapsedS((Date.now() - startMs) / 1000);
    }, 250);
    return () => window.clearInterval(timer);
  }, [isTakeRecording]);

  const onlineSensors = sensors.filter((s) => s.status === 'online' || s.status === 'interpolating').length;
  const radioLinked = awinda?.connected_sensor_count ?? 0;

  let step1BadgeClass = 'bg-slate-800 border-slate-700 text-slate-300';
  let step1DotClass = 'bg-slate-500';
  let step1Text = t.connectUsbAntenna;

  if (!connected) {
    step1BadgeClass = 'bg-rose-500/15 border-rose-500/40 text-rose-300';
    step1DotClass = 'bg-rose-500';
    step1Text = t.startingEngine;
  } else if (awinda?.driver_missing) {
    step1BadgeClass = 'bg-rose-500/15 border-rose-500/40 text-rose-300';
    step1DotClass = 'bg-rose-500';
    step1Text = t.xsensDriverMissing;
  } else if (awinda?.antenna_state === 'error') {
    step1BadgeClass = 'bg-rose-500/15 border-rose-500/40 text-rose-300';
    step1DotClass = 'bg-rose-500';
    step1Text = `${t.antennaError} · ${radioLinked}/17`;
  } else if (awinda?.antenna_state === 'no_response') {
    step1BadgeClass = 'bg-amber-500/15 border-amber-500/40 text-amber-300';
    step1DotClass = 'bg-amber-500';
    step1Text = `${t.antennaNoResponse} (${awinda.port || 'USB'})`;
  } else if (awinda?.running && (awinda.antenna_state === 'radio_on' || awinda.antenna_state === 'streaming')) {
    const isStreamingData = onlineSensors > 0;
    step1BadgeClass = isStreamingData
      ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
      : 'bg-amber-500/15 border-amber-500/40 text-amber-300';
    step1DotClass = isStreamingData ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400 animate-pulse';
    step1Text = `Radio: ${radioLinked}/17 · ${locale === 'es' ? 'Datos' : 'Data'}: ${onlineSensors}/17`;
  } else if (simulatorActive) {
    step1BadgeClass = 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300';
    step1DotClass = 'bg-cyan-400 animate-pulse';
    step1Text =
      locale === 'es'
        ? `Demo Virtual · ${onlineSensors}/17 Sensores`
        : `Virtual Demo · ${onlineSensors}/17 Sensors`;
  }

  const handleStep1Reconnect = () => {
    if (awinda?.running && (onlineSensors > 0 || awinda.antenna_state === 'streaming')) {
      if (!window.confirm(t.reconnectConfirm)) {
        return;
      }
    }
    api.reconnectAwinda().catch(() => {});
  };

  const handleToggleTakeRecord = async () => {
    await toggleGuidedTakeRecording();
  };

  const handleProfileChange = async (profileId: string) => {
    try {
      const res = await api.activateProfile(profileId);
      setProfiles(res.profiles);
      setToast(`Perfil activado: ${res.profile?.name ?? profileId}`);
    } catch (err) {
      setToast((err as Error).message);
    }
  };

  const handleCheckUpdates = async () => {
    if (checkingUpdate) return;
    setCheckingUpdate(true);
    try {
      if (window.openMocapDesktop?.checkForUpdates) {
        const res = await window.openMocapDesktop.checkForUpdates();
        if (res && !res.ok && res.message) {
          setToast(res.message);
        }
      } else {
        const resp = await fetch('https://api.github.com/repos/Guti31/openmocap-studio/releases/latest', {
          headers: { Accept: 'application/vnd.github+json' },
        });
        if (!resp.ok) {
          setToast(
            locale === 'es'
              ? 'No hay publicaciones disponibles en GitHub todavía.'
              : 'No GitHub releases published yet.',
          );
          return;
        }
        const data = await resp.json();
        const tag = String(data?.tag_name || '');
        setToast(
          tag
            ? `${locale === 'es' ? 'Última versión en GitHub:' : 'Latest GitHub release:'} ${tag}`
            : locale === 'es'
            ? 'Actualización verificada.'
            : 'Update checked.',
        );
      }
    } catch (err) {
      setToast((err as Error).message);
    } finally {
      setCheckingUpdate(false);
    }
  };

  // --- MODO SIMPLE (POR DEFECTO): FLUJO GUIADO DE 4 PASOS ---
  if (!advancedMode) {
    return (
      <header className="h-14 bg-[#111827] border-b border-slate-800 px-4 flex items-center justify-between gap-3 select-none shrink-0">
        {/* Marca */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow shadow-cyan-500/25">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <div className="leading-tight hidden sm:block">
            <div className="text-sm font-bold tracking-tight text-slate-100">{t.appTitle}</div>
            <div className="text-[10px] text-cyan-400/90 font-medium">{t.guidedSubtitle}</div>
          </div>
        </div>

        {/* 4 Pasos Lineales */}
        <div className="flex items-center gap-2 overflow-x-auto py-1">
          {/* Paso 1: Antena y Traje */}
          <div
            onClick={handleStep1Reconnect}
            title={awinda?.message_es}
            className={`cursor-pointer flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition ${step1BadgeClass}`}
          >
            <span className="text-[10px] font-bold opacity-75">1.</span>
            <span className={`w-2 h-2 rounded-full ${step1DotClass}`} />
            <Radio className="w-3.5 h-3.5" />
            <span className="whitespace-nowrap">{step1Text}</span>
          </div>

          <span className="text-slate-600 text-xs">→</span>

          {/* Paso 2: Calibrar Traje */}
          <button
            onClick={() => setCalibrationModalOpen(true)}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold border transition whitespace-nowrap ${
              isCalibrated
                ? 'bg-emerald-600/20 border-emerald-500/50 text-emerald-300 hover:bg-emerald-600/30'
                : 'bg-amber-500 hover:bg-amber-400 border-amber-400 text-slate-950 shadow shadow-amber-500/20'
            }`}
          >
            <span>2.</span>
            {isCalibrated ? <CheckCircle2 className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
            <span>{isCalibrated ? t.suitCalibrated : t.calibrateSuit}</span>
          </button>

          <span className="text-slate-600 text-xs">→</span>

          {/* Paso 3: Grabar Movimiento + Inicio/Fin Pose T */}
          <div className="flex items-center gap-1.5">
            <button
              disabled={recordingTposePhase !== 'idle'}
              onClick={handleToggleTakeRecord}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-bold border transition whitespace-nowrap disabled:opacity-75 ${
                recordingTposePhase !== 'idle'
                  ? 'bg-amber-600 border-amber-400 text-white animate-pulse'
                  : isTakeRecording
                  ? 'bg-rose-600 hover:bg-rose-500 border-rose-400 text-white shadow-lg shadow-rose-600/30 animate-pulse'
                  : 'bg-rose-600/90 hover:bg-rose-500 border-rose-500 text-white shadow shadow-rose-600/20'
              }`}
            >
              <span>3.</span>
              {isTakeRecording ? (
                <Square className="w-3.5 h-3.5 fill-current" />
              ) : (
                <Circle className="w-3.5 h-3.5 fill-current" />
              )}
              <span>
                {recordingTposePhase === 'lead_in'
                  ? t.studioTposeLeadInBtn
                  : recordingTposePhase === 'lead_out'
                  ? t.studioTposeLeadOutBtn
                  : isTakeRecording
                  ? `${t.stopSimple} (${formatChrono(recElapsedS)})`
                  : t.recordSimple}
              </span>
            </button>
            <label
              title={t.studioTposeToggleTip}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-lg border text-[11px] cursor-pointer whitespace-nowrap transition ${
                studioTposeRecording
                  ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-200'
                  : 'bg-slate-900 border-slate-700 text-slate-400'
              }`}
            >
              <input
                type="checkbox"
                checked={studioTposeRecording}
                onChange={(e) => setStudioTposeRecording(e.target.checked)}
                className="accent-cyan-500"
              />
              <span>{t.studioTposeToggle}</span>
            </label>
          </div>

          <span className="text-slate-600 text-xs">→</span>

          {/* Paso 4: Exportar */}
          <button
            onClick={() => setExportModalOpen(true)}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white shadow shadow-cyan-600/25 transition whitespace-nowrap"
          >
            <span>4.</span>
            <Download className="w-4 h-4" />
            <span>{t.saveExportSimple}</span>
          </button>
        </div>

        {/* Derecha: Actualizaciones + Idioma + Interruptor discreto Modo Avanzado */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleCheckUpdates}
            disabled={checkingUpdate}
            title={t.checkUpdates}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-slate-300 hover:border-cyan-500/50 hover:text-cyan-200 disabled:opacity-50 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${checkingUpdate ? 'animate-spin' : ''}`} />
            <span className="hidden xl:inline">{checkingUpdate ? t.checkingUpdates : t.checkUpdates}</span>
          </button>
          <button
            onClick={() => setLocale(locale === 'es' ? 'en' : 'es')}
            title="ES / EN"
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs font-mono text-slate-300 hover:border-slate-500"
          >
            <Globe className="w-3.5 h-3.5 text-cyan-400" />
            <span>{locale.toUpperCase()}</span>
          </button>
          <button
            onClick={() => setAdvancedMode(true)}
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 hover:border-slate-500 text-xs text-slate-300 transition"
            title={t.advancedModeLabel}
          >
            <Sliders className="w-3.5 h-3.5 text-slate-400" />
            <span className="hidden lg:inline">{t.advancedModeLabel}</span>
            <span className="w-7 h-4 rounded-full bg-slate-700 p-0.5 flex items-center">
              <span className="w-3 h-3 rounded-full bg-slate-300 transition-transform" />
            </span>
          </button>
        </div>
      </header>
    );
  }

  // --- MODO AVANZADO (HERRAMIENTAS COMPLETAS DE INGENIERÍA) ---
  return (
    <header className="h-12 bg-[#111827] border-b border-slate-800 px-3 flex items-center justify-between gap-2 select-none shrink-0">
      <div className="flex items-center gap-2">
        <button
          onClick={toggleLeftPanel}
          title={t.leftPanelToggle}
          className={`p-1.5 rounded-md border text-xs transition ${
            leftPanelOpen
              ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
              : 'bg-slate-800/70 border-slate-700 text-slate-400 hover:text-slate-200'
          }`}
        >
          <PanelLeft className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2 pr-2 border-r border-slate-800">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow shadow-cyan-500/30">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight text-slate-100">{t.appTitle}</div>
            <div className="text-[10px] font-mono text-cyan-400/90">{t.appSubtitle}</div>
          </div>
        </div>

        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
            connected
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
          }`}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'
            }`}
          />
          <span>{connected ? t.connected : t.disconnected}</span>
          <span className="font-mono text-[11px] text-slate-300 ml-1">
            {streamHz > 0 ? `${streamHz.toFixed(0)} Hz` : '-- Hz'}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 bg-slate-900/90 border border-slate-700/80 rounded-md px-2 py-1">
          <span className="text-[11px] text-slate-400">{t.profile}:</span>
          <select
            value={activeProfile?.id ?? 'default_175'}
            onChange={(e) => handleProfileChange(e.target.value)}
            className="bg-transparent text-xs text-slate-100 focus:outline-none cursor-pointer max-w-[165px]"
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id} className="bg-slate-900 text-slate-100">
                {p.name} ({p.height_cm} cm)
              </option>
            ))}
          </select>
          <button
            onClick={() => setProfileModalOpen(true)}
            title={t.manageProfiles}
            className="ml-1 p-1 rounded hover:bg-slate-800 text-cyan-400"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>

        <button
          onClick={() => setCalibrationModalOpen(true)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border transition ${
            isCalibrated
              ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25'
              : 'bg-amber-500/15 border-amber-500/40 text-amber-300 hover:bg-amber-500/25'
          }`}
        >
          <UserCheck className="w-3.5 h-3.5" />
          <span>{t.calibrate}</span>
          <span className="text-[10px] opacity-80">
            ({isCalibrated ? `${calibration?.overall_quality_pct ?? 100}%` : t.calibrationNeeded})
          </span>
        </button>
      </div>

      <div className="flex items-center gap-2">
        <label className="hidden xl:flex items-center gap-1 text-[11px] text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={overlayHudInVideo}
            onChange={(e) => setOverlayHudInVideo(e.target.checked)}
            className="accent-cyan-500"
          />
          <span>{t.overlayHudVideo}</span>
        </label>

        <button
          onClick={onToggleVideoRecord}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium border transition ${
            isVideoRecording
              ? 'bg-rose-600 border-rose-400 text-white animate-pulse'
              : 'bg-slate-800 border-slate-700 text-slate-200 hover:border-cyan-500/50'
          }`}
        >
          {isVideoRecording ? <VideoOff className="w-3.5 h-3.5" /> : <Video className="w-3.5 h-3.5 text-cyan-400" />}
          <span>{isVideoRecording ? t.stopVideo : t.recordVideo}</span>
        </button>

        <button
          onClick={() => setExportModalOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-cyan-600 hover:bg-cyan-500 text-white shadow shadow-cyan-600/20 transition"
        >
          <Download className="w-3.5 h-3.5" />
          <span>{t.exportBlender}</span>
        </button>

        <button
          onClick={handleCheckUpdates}
          disabled={checkingUpdate}
          title={t.checkUpdates}
          className="p-1.5 rounded-md bg-slate-800 border border-slate-700 text-slate-200 hover:border-cyan-500/50 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${checkingUpdate ? 'animate-spin' : ''}`} />
        </button>

        <button
          onClick={() => setLocale(locale === 'es' ? 'en' : 'es')}
          title="Cambiar idioma ES / EN"
          className="flex items-center gap-1 px-2 py-1.5 rounded-md bg-slate-800 border border-slate-700 text-xs font-mono text-slate-200 hover:border-slate-500"
        >
          <Globe className="w-3.5 h-3.5 text-cyan-400" />
          <span>{locale.toUpperCase()}</span>
        </button>

        <button
          onClick={() => setAdvancedMode(false)}
          className="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-cyan-500/15 border border-cyan-500/40 text-xs text-cyan-300"
          title="Volver a Modo Simple"
        >
          <span>Modo Avanzado</span>
          <span className="w-7 h-4 rounded-full bg-cyan-500 p-0.5 flex items-center justify-end">
            <span className="w-3 h-3 rounded-full bg-white" />
          </span>
        </button>

        <button
          onClick={toggleRightPanel}
          title={t.rightPanelToggle}
          className={`p-1.5 rounded-md border text-xs transition ${
            rightPanelOpen
              ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
              : 'bg-slate-800/70 border-slate-700 text-slate-400 hover:text-slate-200'
          }`}
        >
          <PanelRight className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
