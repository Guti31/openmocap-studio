import { useEffect, useRef } from 'react';
import { translations } from '../i18n';
import { api } from '../services/api';
import { liveFrameRef, useStudioStore } from '../store/useStudioStore';

export function useVideoRecorder() {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const rafRef = useRef<number | null>(null);

  const locale = useStudioStore((s) => s.locale);
  const isVideoRecording = useStudioStore((s) => s.isVideoRecording);
  const overlayHud = useStudioStore((s) => s.overlayHudInVideo);
  const setIsVideoRecording = useStudioStore((s) => s.setIsVideoRecording);
  const setToast = useStudioStore((s) => s.setToast);

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        try {
          recorderRef.current.stop();
        } catch {
          // ignorar
        }
      }
    };
  }, []);

  const startVideoRecording = (sourceCanvas: HTMLCanvasElement | null) => {
    if (!sourceCanvas) {
      setToast('No se encontró el lienzo 3D para grabar video.');
      return;
    }

    const t = translations[locale];
    let stream: MediaStream;
    if (overlayHud) {
      const compCanvas = document.createElement('canvas');
      compCanvas.width = sourceCanvas.width || 1280;
      compCanvas.height = sourceCanvas.height || 720;
      const ctx = compCanvas.getContext('2d');

      const drawComposite = () => {
        if (ctx) {
          if (compCanvas.width !== sourceCanvas.width || compCanvas.height !== sourceCanvas.height) {
            compCanvas.width = sourceCanvas.width;
            compCanvas.height = sourceCanvas.height;
          }
          ctx.drawImage(sourceCanvas, 0, 0, compCanvas.width, compCanvas.height);

          const f = liveFrameRef.current;
          ctx.fillStyle = 'rgba(11, 15, 23, 0.72)';
          ctx.fillRect(16, 16, 360, 68);
          ctx.strokeStyle = 'rgba(6, 182, 212, 0.7)';
          ctx.strokeRect(16, 16, 360, 68);

          ctx.fillStyle = '#06b6d4';
          ctx.font = 'bold 14px monospace';
          ctx.fillText('OPENMOCAP STUDIO - APLICACION_TRAJE', 28, 38);

          ctx.fillStyle = '#e2e8f0';
          ctx.font = '12px monospace';
          const hz = f?.rate_hz?.toFixed(1) ?? '0.0';
          const cal = f?.calibration?.state === 'calibrated' ? t.calibrationOk.toUpperCase() : (f?.calibration?.state ?? 'LIVE');
          const kneeL = f?.angles?.knee_l?.flexion?.toFixed(1) ?? '0.0';
          ctx.fillText(`${hz} Hz | ${cal} | ${t.hudKneeLabel}: ${kneeL}°`, 28, 62);
        }
        rafRef.current = requestAnimationFrame(drawComposite);
      };
      drawComposite();
      stream = compCanvas.captureStream(60);
    } else {
      stream = sourceCanvas.captureStream(60);
    }

    const mimeCandidates = [
      'video/webm;codecs=vp9',
      'video/webm;codecs=vp8',
      'video/webm',
    ];
    const mimeType = mimeCandidates.find((m) => MediaRecorder.isTypeSupported(m)) ?? 'video/webm';

    chunksRef.current = [];
    const mr = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 8_000_000 });
    mr.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
    };
    mr.onstop = async () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      setIsVideoRecording(false);
      const blob = new Blob(chunksRef.current, { type: mimeType });
      const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const fname = `openmocap_visor_${stamp}`;
      try {
        setToast('Transcodificando video a .MP4 H.264...');
        const res = await api.convertVideoMp4(blob, fname, 60);
        setToast(res.message_es || `Video guardado: ${res.file_name}`);
      } catch (err) {
        setToast(`Error al guardar video MP4: ${(err as Error).message}`);
      }
    };

    recorderRef.current = mr;
    mr.start(250);
    setIsVideoRecording(true);
    setToast('Grabando video 60 FPS desde el visor 3D...');
  };

  const stopVideoRecording = () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }
  };

  return {
    isVideoRecording,
    startVideoRecording,
    stopVideoRecording,
  };
}

