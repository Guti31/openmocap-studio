import React from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Circle,
  FolderOpen,
  Pause,
  Play,
  Radio,
  Repeat,
  Square,
} from 'lucide-react';
import { translations } from '../i18n';
import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';
import { toggleGuidedTakeRecording } from '../utils/studioRecorder';

function formatTimecode(frameIdx: number, fps: number): string {
  const safeFps = Math.max(1, fps);
  const totalSec = frameIdx / safeFps;
  const mins = Math.floor(totalSec / 60);
  const secs = Math.floor(totalSec % 60);
  const sub = Math.floor((totalSec - Math.floor(totalSec)) * 100);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(sub).padStart(2, '0')}`;
}

export const TimelineBar: React.FC = () => {
  const locale = useStudioStore((s) => s.locale);
  const advancedMode = useStudioStore((s) => s.advancedMode);
  const recording = useStudioStore((s) => s.recording);
  const studioTposeRecording = useStudioStore((s) => s.studioTposeRecording);
  const setStudioTposeRecording = useStudioStore((s) => s.setStudioTposeRecording);
  const recordingTposePhase = useStudioStore((s) => s.recordingTposePhase);
  const takes = useStudioStore((s) => s.takes);
  const setToast = useStudioStore((s) => s.setToast);

  const t = translations[locale];
  const isRec = Boolean(recording?.is_recording);
  const isPlayback = recording?.mode === 'playback';
  const isPlaying = Boolean(recording?.playing);
  const frameCount = recording?.frame_count ?? 0;
  const currentFrame = recording?.current_frame ?? 0;
  const fps = recording?.fps ?? 120;
  const speed = recording?.speed ?? 1.0;
  const loop = recording?.loop ?? true;
  const trimIn = recording?.trim_in ?? 0;
  const trimOut = recording?.trim_out ?? Math.max(0, frameCount - 1);

  const handleToggleRecord = async () => {
    await toggleGuidedTakeRecording();
  };

  const handleLoadTake = async (takeId: string) => {
    if (!takeId) return;
    try {
      await api.loadTake(takeId);
      setToast(`Grabación cargada: ${takeId}`);
    } catch (err) {
      setToast((err as Error).message);
    }
  };

  // --- MODO SIMPLE: REPRODUCTOR LIMPIO Y GRABACIONES RECIENTES ---
  if (!advancedMode) {
    return (
      <footer className="h-14 bg-[#111827] border-t border-slate-800 px-4 flex items-center justify-between gap-4 select-none shrink-0">
        <div className="flex items-center gap-2">
          <button
            disabled={frameCount === 0}
            onClick={() => api.playbackControl({ action: isPlaying ? 'pause' : 'play' })}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-xs font-semibold transition"
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
            <span>{isPlaying ? t.pauseSimple : t.playSimple}</span>
          </button>

          {isPlayback && (
            <button
              onClick={() => api.playbackControl({ action: 'live' })}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 text-xs font-medium hover:bg-emerald-600/30"
            >
              <Radio className="w-3.5 h-3.5" />
              <span>{t.returnLiveSimple}</span>
            </button>
          )}
        </div>

        <div className="flex-1 flex items-center gap-3">
          <span className="text-xs font-mono text-cyan-300 w-16 tabular-nums">
            {formatTimecode(currentFrame, fps)}
          </span>
          <input
            type="range"
            min={0}
            max={Math.max(0, frameCount - 1)}
            value={currentFrame}
            disabled={frameCount === 0}
            onChange={(e) => api.playbackControl({ frame_idx: Number(e.target.value) })}
            className="flex-1 accent-cyan-500 h-2 bg-slate-800 rounded-lg cursor-pointer"
          />
          <span className="text-xs font-mono text-slate-400 w-16 text-right tabular-nums">
            {frameCount > 0 ? `${(frameCount / Math.max(1, fps)).toFixed(1)} s` : '0.0 s'}
          </span>
        </div>

        <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5">
          <FolderOpen className="w-3.5 h-3.5 text-cyan-400" />
          <select
            value={recording?.active_take_id ?? ''}
            onChange={(e) => handleLoadTake(e.target.value)}
            className="bg-transparent text-xs text-slate-200 max-w-[200px] focus:outline-none"
          >
            <option value="" className="bg-slate-900">
              {t.recentTakesSimple} ({takes.length})
            </option>
            {takes.map((tk) => (
              <option key={tk.take_id} value={tk.take_id} className="bg-slate-900">
                {tk.name} ({tk.duration_s}s)
              </option>
            ))}
          </select>
        </div>
      </footer>
    );
  }

  // --- MODO AVANZADO: TRANSPORTE COMPLETO ---
  return (
    <footer className="h-20 bg-[#111827] border-t border-slate-800 px-3 py-2 flex flex-col justify-between select-none shrink-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <button
            disabled={recordingTposePhase !== 'idle'}
            onClick={handleToggleRecord}
            className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-semibold transition disabled:opacity-75 ${
              recordingTposePhase !== 'idle'
                ? 'bg-amber-600 text-white animate-pulse'
                : isRec
                ? 'bg-rose-600 text-white animate-pulse'
                : 'bg-rose-600/20 border border-rose-500/40 text-rose-300 hover:bg-rose-600/30'
            }`}
          >
            {isRec ? <Square className="w-3 h-3 fill-current" /> : <Circle className="w-3 h-3 fill-current" />}
            <span>
              {recordingTposePhase === 'lead_in'
                ? t.studioTposeLeadInBtn
                : recordingTposePhase === 'lead_out'
                ? t.studioTposeLeadOutBtn
                : isRec
                ? t.stopTake
                : t.recordTake}
            </span>
          </button>

          <label
            title={t.studioTposeToggleTip}
            className="hidden xl:flex items-center gap-1 text-[11px] text-slate-400 cursor-pointer px-1.5"
          >
            <input
              type="checkbox"
              checked={studioTposeRecording}
              onChange={(e) => setStudioTposeRecording(e.target.checked)}
              className="accent-cyan-500"
            />
            <span>Pose T</span>
          </label>

          <button
            onClick={() => api.playbackControl({ action: 'live' })}
            className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium border transition ${
              !isPlayback
                ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-white'
            }`}
          >
            <Radio className="w-3 h-3" />
            <span>{t.liveMode}</span>
          </button>

          <div className="w-px h-5 bg-slate-700 mx-1" />

          <button
            disabled={frameCount === 0}
            onClick={() => api.playbackControl({ action: 'step_prev' })}
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200"
            title="Cuadro anterior"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <button
            disabled={frameCount === 0}
            onClick={() => api.playbackControl({ action: isPlaying ? 'pause' : 'play' })}
            className="p-1.5 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white"
            title="Reproducir / Pausar (Espacio)"
          >
            {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          </button>
          <button
            disabled={frameCount === 0}
            onClick={() => api.playbackControl({ action: 'stop' })}
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200"
            title="Detener"
          >
            <Square className="w-3.5 h-3.5" />
          </button>
          <button
            disabled={frameCount === 0}
            onClick={() => api.playbackControl({ action: 'step_next' })}
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200"
            title="Cuadro siguiente"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => api.playbackControl({ loop: !loop })}
            className={`p-1.5 rounded border text-xs transition ${
              loop
                ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300'
                : 'bg-slate-800 border-slate-700 text-slate-400'
            }`}
            title={t.loop}
          >
            <Repeat className="w-3.5 h-3.5" />
          </button>

          <select
            value={speed}
            onChange={(e) => api.playbackControl({ speed: Number(e.target.value) })}
            className="bg-slate-900 border border-slate-700 rounded px-1.5 py-1 text-xs font-mono text-slate-200"
            title={t.speed}
          >
            <option value={0.25}>0.25x</option>
            <option value={0.5}>0.5x</option>
            <option value={1}>1.0x</option>
            <option value={1.5}>1.5x</option>
            <option value={2}>2.0x</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <button
            disabled={frameCount === 0}
            onClick={() => api.playbackControl({ trim_in: currentFrame })}
            className="px-2 py-1 rounded text-[11px] font-mono bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 border border-slate-700"
          >
            {t.trimIn} {trimIn}
          </button>
          <button
            disabled={frameCount === 0}
            onClick={() => api.playbackControl({ trim_out: currentFrame })}
            className="px-2 py-1 rounded text-[11px] font-mono bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 border border-slate-700"
          >
            {t.trimOut} {trimOut}
          </button>

          <div className="flex items-center gap-1 bg-slate-900 border border-slate-700 rounded px-2 py-1">
            <FolderOpen className="w-3.5 h-3.5 text-cyan-400" />
            <select
              value={recording?.active_take_id ?? ''}
              onChange={(e) => handleLoadTake(e.target.value)}
              className="bg-transparent text-xs text-slate-200 max-w-[190px] focus:outline-none"
            >
              <option value="" className="bg-slate-900">
                {t.savedTakes} ({takes.length})
              </option>
              {takes.map((tk) => (
                <option key={tk.take_id} value={tk.take_id} className="bg-slate-900">
                  {tk.name} ({tk.duration_s}s)
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-[11px] font-mono text-cyan-300 w-20 tabular-nums">
          {formatTimecode(currentFrame, fps)}
        </span>
        <input
          type="range"
          min={0}
          max={Math.max(0, frameCount - 1)}
          value={currentFrame}
          disabled={frameCount === 0}
          onChange={(e) => api.playbackControl({ frame_idx: Number(e.target.value) })}
          className="flex-1 accent-cyan-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
        />
        <span className="text-[11px] font-mono text-slate-400 w-32 text-right tabular-nums">
          F {currentFrame} / {Math.max(0, frameCount - 1)} ({fps.toFixed(0)} fps)
        </span>
      </div>
    </footer>
  );
};
