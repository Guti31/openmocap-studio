import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';
import { calibrationAudio } from './calibrationAudio';

let activeTimers: number[] = [];
let sequenceToken = 0;

export function cancelGuidedTakeSequence(): void {
  sequenceToken += 1;
  for (const tid of activeTimers) {
    window.clearTimeout(tid);
  }
  activeTimers = [];
  useStudioStore.getState().setRecordingTposePhase('idle');
}

export async function toggleGuidedTakeRecording(): Promise<void> {
  const store = useStudioStore.getState();
  const { locale, recording, studioTposeRecording, recordingTposePhase, setTakes, setToast, setRecordingTposePhase } =
    store;

  if (recordingTposePhase !== 'idle') {
    return;
  }

  const isRec = Boolean(recording?.is_recording);

  if (!studioTposeRecording) {
    try {
      if (isRec) {
        const res = await api.stopRecording();
        setToast(
          locale === 'es'
            ? `Grabación guardada (${res.frame_count} cuadros, ${res.duration_s} s)`
            : `Recording saved (${res.frame_count} frames, ${res.duration_s} s)`,
        );
        const tk = await api.listTakes();
        setTakes(tk.takes);
      } else {
        await api.startRecording();
        setToast(locale === 'es' ? 'Grabando movimiento a 120 Hz...' : 'Recording motion at 120 Hz...');
      }
    } catch (err) {
      setToast((err as Error).message);
    }
    return;
  }

  calibrationAudio.ensureReady();
  const myToken = ++sequenceToken;

  if (!isRec) {
    setRecordingTposePhase('lead_in');
    setToast(locale === 'es' ? 'Ponte en Pose T (2.0 s)...' : 'Stand in T-Pose (2.0 s)...');
    calibrationAudio.playCountdownBeep(2);
    calibrationAudio.speak(locale === 'es' ? 'Ponte en Pose T' : 'Stand in T-Pose', { locale });

    const tStartRec = window.setTimeout(async () => {
      if (sequenceToken !== myToken) return;
      try {
        await api.startRecording();
      } catch (err) {
        cancelGuidedTakeSequence();
        setToast((err as Error).message);
      }
    }, 1200);

    const tAction = window.setTimeout(() => {
      if (sequenceToken !== myToken) return;
      setRecordingTposePhase('idle');
      calibrationAudio.playActionCue();
      calibrationAudio.speak(locale === 'es' ? '¡Acción!' : 'Action!', { locale });
      setToast(locale === 'es' ? '¡Acción! Grabando movimiento...' : 'Action! Recording motion...');
    }, 2000);

    activeTimers = [tStartRec, tAction];
  } else {
    setRecordingTposePhase('lead_out');
    setToast(
      locale === 'es' ? 'Vuelve a Pose T para cerrar (2.0 s)...' : 'Return to T-Pose to finish (2.0 s)...',
    );
    calibrationAudio.playCountdownBeep(2);
    calibrationAudio.speak(
      locale === 'es' ? 'Vuelve a Pose T para cerrar' : 'Return to T-Pose to finish',
      { locale },
    );

    const tStop = window.setTimeout(async () => {
      if (sequenceToken !== myToken) return;
      setRecordingTposePhase('idle');
      try {
        const res = await api.stopRecording();
        calibrationAudio.playCompleteChime();
        calibrationAudio.speak(locale === 'es' ? 'Grabación guardada' : 'Recording saved', { locale });
        setToast(
          locale === 'es'
            ? `Grabación guardada (${res.frame_count} cuadros, ${res.duration_s} s)`
            : `Recording saved (${res.frame_count} frames, ${res.duration_s} s)`,
        );
        const tk = await api.listTakes();
        setTakes(tk.takes);
      } catch (err) {
        calibrationAudio.playErrorTone();
        setToast((err as Error).message);
      }
    }, 2000);

    activeTimers = [tStop];
  }
}
