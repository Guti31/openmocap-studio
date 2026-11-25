import React, { useEffect, useRef } from 'react';
import { CalibrationWizardModal } from './components/CalibrationWizardModal';
import { ExportModal } from './components/ExportModal';
import { LeftHardwarePanel } from './components/LeftHardwarePanel';
import { ProfileManagerModal } from './components/ProfileManagerModal';
import { RightBiomechanicsPanel } from './components/RightBiomechanicsPanel';
import { TimelineBar } from './components/TimelineBar';
import { TopBar } from './components/TopBar';
import { UpdateBannerModal } from './components/UpdateBannerModal';
import { Viewport3D } from './components/Viewport3D';
import { useMocapStream } from './hooks/useMocapStream';
import { useVideoRecorder } from './hooks/useVideoRecorder';
import { api } from './services/api';
import { useStudioStore } from './store/useStudioStore';

export const App: React.FC = () => {
  useMocapStream();

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const { isVideoRecording, startVideoRecording, stopVideoRecording } = useVideoRecorder();

  const advancedMode = useStudioStore((s) => s.advancedMode);
  const leftPanelOpen = useStudioStore((s) => s.leftPanelOpen);
  const rightPanelOpen = useStudioStore((s) => s.rightPanelOpen);
  const toastMessage = useStudioStore((s) => s.toastMessage);
  const setToast = useStudioStore((s) => s.setToast);
  const setCameraPreset = useStudioStore((s) => s.setCameraPreset);

  useEffect(() => {
    if (!toastMessage) return;
    const timer = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(timer);
  }, [toastMessage, setToast]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      if (e.code === 'Space') {
        e.preventDefault();
        const rec = useStudioStore.getState().recording;
        if (rec?.frame_count) {
          api.playbackControl({ action: rec.playing ? 'pause' : 'play' }).catch(() => {});
        }
      } else if (e.key === '1') {
        setCameraPreset('perspective');
      } else if (e.key === '2') {
        setCameraPreset('front');
      } else if (e.key === '3') {
        setCameraPreset('side');
      } else if (e.key === '4') {
        setCameraPreset('top');
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [setCameraPreset]);

  const handleToggleVideoRecord = () => {
    if (isVideoRecording) {
      stopVideoRecording();
    } else {
      startVideoRecording(canvasRef.current);
    }
  };

  return (
    <div className="h-screen w-screen bg-[#0b0f17] text-slate-100 flex flex-col overflow-hidden">
      <TopBar onToggleVideoRecord={handleToggleVideoRecord} />

      <main className="flex-1 flex min-h-0 overflow-hidden">
        {(leftPanelOpen || !advancedMode) && <LeftHardwarePanel />}
        <Viewport3D onCanvasReady={(el) => (canvasRef.current = el)} />
        {advancedMode && rightPanelOpen && <RightBiomechanicsPanel />}
      </main>

      <TimelineBar />

      {/* Modales del estudio */}
      <CalibrationWizardModal />
      <ProfileManagerModal />
      <ExportModal onToggleVideoRecord={handleToggleVideoRecord} />
      <UpdateBannerModal />

      {/* Notificación flotante */}
      {toastMessage && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg bg-slate-900/95 border border-cyan-500/50 text-xs text-cyan-200 shadow-xl backdrop-blur">
          {toastMessage}
        </div>
      )}
    </div>
  );
};

export default App;

