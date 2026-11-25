import { create } from 'zustand';
import type {
  AnthropometricProfileDTO,
  AwindaStatusPayload,
  CalibrationStatus,
  CameraPreset,
  JointAngleTriple,
  Locale,
  MocapFrame,
  RecordingStatus,
  RenderMode,
  SensorDiagnostic,
  ShakeEvent,
  TakeSummary,
} from '../types/mocap';

export interface AngleHistoryPoint {
  t: number;
  flexion: number;
  abduction: number;
  rotation: number;
}

/** Referencia mutable leída por Three.js a 60 FPS sin provocar re-renders de React. */
export const liveFrameRef: { current: MocapFrame | null } = { current: null };

interface StudioState {
  locale: Locale;
  advancedMode: boolean;
  connected: boolean;
  streamHz: number;
  leftPanelOpen: boolean;
  rightPanelOpen: boolean;
  renderMode: RenderMode;
  showAxes: boolean;
  showAccel: boolean;
  cameraPreset: CameraPreset;
  cameraResetTick: number;
  followPelvis: boolean;
  rootMode: 'in_place' | 'free_walk';
  selectedSegment: string;
  selectedJoint: string;
  overlayHudInVideo: boolean;
  isVideoRecording: boolean;
  studioTposeRecording: boolean;
  recordingTposePhase: 'idle' | 'lead_in' | 'lead_out';

  profiles: AnthropometricProfileDTO[];
  activeProfile: AnthropometricProfileDTO | null;
  sensors: SensorDiagnostic[];
  calibration: CalibrationStatus | null;
  recording: RecordingStatus | null;
  awinda: AwindaStatusPayload | null;
  simulatorActive: boolean;
  latestAngles: Record<string, JointAngleTriple>;
  angleHistory: Record<string, AngleHistoryPoint[]>;
  takes: TakeSummary[];
  segmentToSensor: Record<string, string>;
  lastShake: ShakeEvent | null;
  toastMessage: string | null;

  calibrationModalOpen: boolean;
  profileModalOpen: boolean;
  exportModalOpen: boolean;

  setLocale: (locale: Locale) => void;
  setAdvancedMode: (v: boolean) => void;
  setConnected: (connected: boolean) => void;
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;
  setRenderMode: (mode: RenderMode) => void;
  setShowAxes: (v: boolean) => void;
  setShowAccel: (v: boolean) => void;
  setCameraPreset: (preset: CameraPreset) => void;
  resetCamera: () => void;
  setFollowPelvis: (v: boolean) => void;
  setRootMode: (mode: 'in_place' | 'free_walk') => void;
  setSelectedSegment: (seg: string) => void;
  setSelectedJoint: (joint: string) => void;
  setOverlayHudInVideo: (v: boolean) => void;
  setIsVideoRecording: (v: boolean) => void;
  setStudioTposeRecording: (v: boolean) => void;
  setRecordingTposePhase: (phase: 'idle' | 'lead_in' | 'lead_out') => void;

  setProfiles: (profiles: AnthropometricProfileDTO[]) => void;
  setTakes: (takes: TakeSummary[]) => void;
  setSegmentToSensor: (map: Record<string, string>) => void;
  setCalibration: (calibration: CalibrationStatus) => void;
  setToast: (msg: string | null) => void;

  setCalibrationModalOpen: (v: boolean) => void;
  setProfileModalOpen: (v: boolean) => void;
  setExportModalOpen: (v: boolean) => void;

  ingestUiFrame: (frame: MocapFrame, measuredHz: number) => void;
}

export const useStudioStore = create<StudioState>((set) => ({
  locale: 'es',
  advancedMode: false,
  connected: false,
  streamHz: 0,
  leftPanelOpen: true,
  rightPanelOpen: false,
  renderMode: 'mannequin',
  showAxes: false,
  showAccel: false,
  cameraPreset: 'perspective',
  cameraResetTick: 0,
  followPelvis: false,
  rootMode: 'in_place',
  selectedSegment: 'PELVIS',
  selectedJoint: 'knee_l',
  overlayHudInVideo: true,
  isVideoRecording: false,
  studioTposeRecording: true,
  recordingTposePhase: 'idle',

  profiles: [],
  activeProfile: null,
  sensors: [],
  calibration: null,
  recording: null,
  awinda: null,
  simulatorActive: false,
  latestAngles: {},
  angleHistory: {},
  takes: [],
  segmentToSensor: {},
  lastShake: null,
  toastMessage: null,

  calibrationModalOpen: false,
  profileModalOpen: false,
  exportModalOpen: false,

  setLocale: (locale) => set({ locale }),
  setAdvancedMode: (advancedMode) =>
    set({
      advancedMode,
      leftPanelOpen: true,
      rightPanelOpen: advancedMode,
      renderMode: advancedMode ? 'hybrid' : 'mannequin',
    }),
  setConnected: (connected) => set({ connected }),
  toggleLeftPanel: () => set((s) => ({ leftPanelOpen: !s.leftPanelOpen })),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
  setRenderMode: (renderMode) => set({ renderMode }),
  setShowAxes: (showAxes) => set({ showAxes }),
  setShowAccel: (showAccel) => set({ showAccel }),
  setCameraPreset: (cameraPreset) => set({ cameraPreset }),
  resetCamera: () => set((s) => ({ cameraPreset: 'perspective', cameraResetTick: s.cameraResetTick + 1 })),
  setFollowPelvis: (followPelvis) => set({ followPelvis }),
  setRootMode: (rootMode) => set({ rootMode }),
  setSelectedSegment: (selectedSegment) => set({ selectedSegment }),
  setSelectedJoint: (selectedJoint) => set({ selectedJoint }),
  setOverlayHudInVideo: (overlayHudInVideo) => set({ overlayHudInVideo }),
  setIsVideoRecording: (isVideoRecording) => set({ isVideoRecording }),
  setStudioTposeRecording: (studioTposeRecording) => set({ studioTposeRecording }),
  setRecordingTposePhase: (recordingTposePhase) => set({ recordingTposePhase }),

  setProfiles: (profiles) =>
    set({
      profiles,
      activeProfile: profiles.find((p) => p.active) ?? profiles[0] ?? null,
    }),
  setTakes: (takes) => set({ takes }),
  setSegmentToSensor: (segmentToSensor) => set({ segmentToSensor }),
  setCalibration: (calibration) => set({ calibration }),
  setToast: (toastMessage) => set({ toastMessage }),

  setCalibrationModalOpen: (calibrationModalOpen) => set({ calibrationModalOpen }),
  setProfileModalOpen: (profileModalOpen) => set({ profileModalOpen }),
  setExportModalOpen: (exportModalOpen) => set({ exportModalOpen }),

  ingestUiFrame: (frame, measuredHz) =>
    set((state) => {
      const nextHistory: Record<string, AngleHistoryPoint[]> = { ...state.angleHistory };
      const tSec = Number((frame.timestamp_ms / 1000).toFixed(2));
      for (const [jKey, ang] of Object.entries(frame.angles)) {
        const arr = nextHistory[jKey] ? [...nextHistory[jKey]] : [];
        arr.push({
          t: tSec,
          flexion: ang.flexion,
          abduction: ang.abduction,
          rotation: ang.rotation,
        });
        if (arr.length > 90) arr.shift();
        nextHistory[jKey] = arr;
      }

      const nextMap: Record<string, string> = { ...state.segmentToSensor };
      for (const sens of frame.sensors) {
        if (sens.segment && sens.segment !== 'UNASSIGNED') {
          nextMap[sens.segment] = sens.sensor_id;
        }
      }

      const prevCal = state.calibration;
      const nextCal = frame.calibration;
      let resolvedCal = nextCal;
      if (prevCal && nextCal) {
        const prevSeq = prevCal.transition_seq ?? -1;
        const nextSeq = nextCal.transition_seq ?? -1;
        if (nextSeq < prevSeq) {
          resolvedCal = prevCal;
        } else if (
          state.calibrationModalOpen &&
          prevCal.state !== 'uncalibrated' &&
          nextCal.state === 'uncalibrated' &&
          nextSeq <= prevSeq
        ) {
          // Protege el asistente abierto frente a tramas WebSocket rezagadas que regresarían a inicio
          resolvedCal = prevCal;
        }
      }

      return {
        connected: true,
        streamHz: measuredHz || frame.rate_hz,
        rootMode: frame.root_mode,
        sensors: frame.sensors,
        calibration: resolvedCal,
        recording: frame.recording,
        awinda: frame.awinda ?? state.awinda,
        simulatorActive: frame.simulator_active ?? state.simulatorActive,
        latestAngles: frame.angles,
        angleHistory: nextHistory,
        segmentToSensor: nextMap,
        lastShake: frame.shake_detected ?? state.lastShake,
      };
    }),
}));

