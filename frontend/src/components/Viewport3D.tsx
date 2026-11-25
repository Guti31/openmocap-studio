import React from 'react';
import { Canvas } from '@react-three/fiber';
import { Camera, Compass, Eye, Footprints, Layers, LocateFixed } from 'lucide-react';
import { translations } from '../i18n';
import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';
import type { CameraPreset, RenderMode } from '../types/mocap';
import { MannequinScene } from './MannequinScene';

interface Viewport3DProps {
  onCanvasReady: (canvas: HTMLCanvasElement | null) => void;
}

export const Viewport3D: React.FC<Viewport3DProps> = ({ onCanvasReady }) => {
  const locale = useStudioStore((s) => s.locale);
  const advancedMode = useStudioStore((s) => s.advancedMode);
  const renderMode = useStudioStore((s) => s.renderMode);
  const setRenderMode = useStudioStore((s) => s.setRenderMode);
  const showAxes = useStudioStore((s) => s.showAxes);
  const setShowAxes = useStudioStore((s) => s.setShowAxes);
  const showAccel = useStudioStore((s) => s.showAccel);
  const setShowAccel = useStudioStore((s) => s.setShowAccel);
  const cameraPreset = useStudioStore((s) => s.cameraPreset);
  const setCameraPreset = useStudioStore((s) => s.setCameraPreset);
  const cameraResetTick = useStudioStore((s) => s.cameraResetTick);
  const resetCamera = useStudioStore((s) => s.resetCamera);
  const followPelvis = useStudioStore((s) => s.followPelvis);
  const setFollowPelvis = useStudioStore((s) => s.setFollowPelvis);
  const rootMode = useStudioStore((s) => s.rootMode);
  const setRootMode = useStudioStore((s) => s.setRootMode);
  const streamHz = useStudioStore((s) => s.streamHz);
  const calibration = useStudioStore((s) => s.calibration);
  const recording = useStudioStore((s) => s.recording);
  const isVideoRecording = useStudioStore((s) => s.isVideoRecording);

  const t = translations[locale];

  const handleRootModeToggle = async () => {
    const next = rootMode === 'in_place' ? 'free_walk' : 'in_place';
    setRootMode(next);
    try {
      await api.setRootMode(next);
    } catch {
      // ignorar si aún está desconectado
    }
  };

  const renderModes: { id: RenderMode; label: string }[] = [
    { id: 'mannequin', label: t.viewMannequin },
    { id: 'skeleton', label: t.viewSkeleton },
    { id: 'hybrid', label: t.viewHybrid },
  ];

  const cameraPresets: { id: CameraPreset; label: string }[] = [
    { id: 'perspective', label: t.cameraPerspective },
    { id: 'front', label: t.cameraFront },
    { id: 'side', label: t.cameraSide },
    { id: 'top', label: t.cameraTop },
  ];

  return (
    <div className="relative flex-1 bg-[#0b0f17] overflow-hidden">
      {/* Barra flotante superior: 3 botones simples en Modo Simple, controles completos en Modo Avanzado */}
      {!advancedMode ? (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 pointer-events-auto flex items-center gap-1.5 bg-slate-900/85 backdrop-blur border border-slate-700/80 rounded-xl p-1.5 shadow-lg">
          <button
            onClick={resetCamera}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-200 hover:bg-slate-800 transition"
          >
            <LocateFixed className="w-3.5 h-3.5 text-cyan-400" />
            <span>{t.centerCamera}</span>
          </button>
          <button
            onClick={() => setCameraPreset(cameraPreset === 'front' ? 'perspective' : 'front')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              cameraPreset === 'front'
                ? 'bg-cyan-600 text-white'
                : 'text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
            <span>{t.frontView}</span>
          </button>
          <button
            onClick={() => setRenderMode(renderMode === 'skeleton' ? 'mannequin' : 'skeleton')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              renderMode === 'skeleton'
                ? 'bg-cyan-600 text-white'
                : 'text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>{renderMode === 'skeleton' ? t.viewAsMannequin : t.viewAsSkeleton}</span>
          </button>
        </div>
      ) : (
        <div className="absolute top-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
          <div className="pointer-events-auto flex items-center gap-1 bg-slate-900/85 backdrop-blur border border-slate-700/80 rounded-lg p-1">
            <Layers className="w-3.5 h-3.5 text-cyan-400 mx-1" />
            {renderModes.map((m) => (
              <button
                key={m.id}
                onClick={() => setRenderMode(m.id)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition ${
                  renderMode === m.id
                    ? 'bg-cyan-600 text-white'
                    : 'text-slate-300 hover:bg-slate-800'
                }`}
              >
                {m.label}
              </button>
            ))}
            <div className="w-px h-4 bg-slate-700 mx-1" />
            <button
              onClick={() => setShowAxes(!showAxes)}
              className={`px-2 py-1 rounded text-xs transition ${
                showAxes ? 'bg-indigo-600/80 text-white' : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              {t.showAxes}
            </button>
            <button
              onClick={() => setShowAccel(!showAccel)}
              className={`px-2 py-1 rounded text-xs transition ${
                showAccel ? 'bg-amber-600/80 text-white' : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              {t.showAccel}
            </button>
          </div>

          <div className="pointer-events-auto flex items-center gap-1 bg-slate-900/85 backdrop-blur border border-slate-700/80 rounded-lg p-1">
            <Camera className="w-3.5 h-3.5 text-cyan-400 mx-1" />
            {cameraPresets.map((c) => (
              <button
                key={c.id}
                onClick={() => setCameraPreset(c.id)}
                className={`px-2 py-1 rounded text-xs transition ${
                  cameraPreset === c.id
                    ? 'bg-slate-700 text-cyan-300 font-medium'
                    : 'text-slate-300 hover:bg-slate-800'
                }`}
              >
                {c.label}
              </button>
            ))}
            <button
              onClick={() => setFollowPelvis(!followPelvis)}
              className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition ${
                followPelvis ? 'bg-cyan-600 text-white' : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              <Eye className="w-3 h-3" />
              <span>{t.followPelvis}</span>
            </button>
            <button
              onClick={handleRootModeToggle}
              className={`flex items-center gap-1 px-2 py-1 rounded text-xs transition ${
                rootMode === 'free_walk'
                  ? 'bg-emerald-600/80 text-white'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              <Footprints className="w-3 h-3" />
              <span>{rootMode === 'free_walk' ? t.rootModeFreeWalk : t.rootModeInPlace}</span>
            </button>
          </div>
        </div>
      )}

      {/* Indicador de grabación / telemetría */}
      <div className="absolute bottom-3 right-3 z-10 pointer-events-none flex items-center gap-2">
        {(recording?.is_recording || isVideoRecording) && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-rose-600/90 text-white text-xs font-mono font-semibold shadow">
            <span className="w-2 h-2 rounded-full bg-white animate-ping" />
            <span>{isVideoRecording ? 'REC MP4' : 'GRABANDO'}</span>
          </div>
        )}
        {advancedMode && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-900/80 backdrop-blur border border-slate-800 text-[11px] font-mono text-slate-300">
            <Compass className="w-3.5 h-3.5 text-cyan-400" />
            <span>{streamHz.toFixed(1)} Hz</span>
            <span className="text-slate-600">|</span>
            <span className={calibration?.state === 'calibrated' ? 'text-emerald-400' : 'text-amber-400'}>
              {calibration?.state === 'calibrated' ? t.calibrationOk : t.calibrationNeeded}
            </span>
          </div>
        )}
      </div>

      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{ position: [2.1, 1.65, 2.4], fov: 45, near: 0.05, far: 50 }}
        gl={{ preserveDrawingBuffer: true, antialias: true }}
        onCreated={({ gl }) => onCanvasReady(gl.domElement)}
      >
        <MannequinScene
          renderMode={renderMode}
          showAxes={advancedMode ? showAxes : false}
          showAccel={advancedMode ? showAccel : false}
          cameraPreset={cameraPreset}
          cameraResetTick={cameraResetTick}
          followPelvis={followPelvis}
        />
      </Canvas>
    </div>
  );
};
