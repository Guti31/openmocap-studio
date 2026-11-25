export type Locale = 'es' | 'en';

export type CalibrationState =
  | 'uncalibrated'
  | 'capturing_static'
  | 'static_done'
  | 'capturing_straight'
  | 'straight_done'
  | 'capturing_walk'
  | 'calibrated'
  | 'error';

export type CalibrationStage =
  | 'idle'
  | 'static_tpose'
  | 'static_straight'
  | 'dynamic_walk'
  | 'calibrated'
  | 'error';

export type CalibrationMode = 'full' | 'quick';

export type RenderMode = 'mannequin' | 'skeleton' | 'hybrid';
export type CameraPreset = 'perspective' | 'front' | 'side' | 'top';
export type MotionPreset = 'walk' | 'jog' | 'squat' | 'tpose' | 'npose' | 'wave';

export interface SegmentPosePayload {
  pos: [number, number, number];
  quat: [number, number, number, number];
  local_quat: [number, number, number, number];
  end_pos: [number, number, number];
  accel: [number, number, number];
}

export interface SensorDiagnostic {
  sensor_id: string;
  brand: string;
  protocol: string;
  segment: string;
  battery: number;
  rssi: number;
  hz: number;
  status: 'online' | 'degraded' | 'interpolating' | 'lost';
  age_ms: number;
  dropped_frames: number;
}

export interface JointAngleTriple {
  flexion: number;
  abduction: number;
  rotation: number;
}

export interface SegmentCalibrationReport {
  segment: string;
  quality_pct: number;
  static_std_deg: number;
  yaw_correction_deg: number;
  sample_count_static: number;
  sample_count_walk: number;
  method: string;
  mean_gyro_rad_s?: number;
  within_tolerance?: boolean;
  straight_residual_deg?: number;
}

export interface CalibrationStatus {
  ok?: boolean;
  error_es?: string | null;
  state: CalibrationState;
  stage?: CalibrationStage;
  mode?: CalibrationMode;
  pose_type: 'tpose' | 'npose';
  straight_anchored?: boolean;
  transition_seq?: number;
  progress: number;
  remaining_s: number;
  overall_quality_pct: number;
  calibrated_segments: number;
  active_sensors_captured?: number;
  max_static_std_deg?: number;
  mean_static_gyro_rad_s?: number;
  message_es: string;
  reports: Record<string, SegmentCalibrationReport>;
}

export interface RecordingStatus {
  mode: 'live' | 'playback';
  is_recording: boolean;
  recording_name: string;
  active_take_id: string | null;
  fps: number;
  frame_count: number;
  duration_s: number;
  playing: boolean;
  loop: boolean;
  speed: number;
  current_frame: number;
  trim_in: number;
  trim_out: number;
}

export interface ShakeEvent {
  sensor_id: string;
  segment: string;
  brand: string;
  gyro_norm: number;
  timestamp_ms: number;
}

export interface ComPortInfo {
  port: string;
  description: string;
  manufacturer?: string;
  hwid?: string;
  vid?: string | null;
  pid?: string | null;
  priority: number;
  is_xsens: boolean;
  is_ftdi_candidate?: boolean;
}

export interface AwindaStatusPayload {
  driver: string;
  sdk_available: boolean;
  running: boolean;
  connection_mode: 'none' | 'xda' | 'xbus_serial';
  antenna_state: 'disconnected' | 'driver_missing' | 'no_response' | 'connecting' | 'radio_on' | 'streaming' | 'error';
  driver_missing: boolean;
  auto_monitor_running: boolean;
  port: string | null;
  baudrate?: number;
  config_ack?: boolean;
  radio_ack?: boolean;
  measurement_ack?: boolean;
  channel: number;
  locked_channel?: number | null;
  rate_hz: number;
  station_id: string | null;
  detected_mtws: string[];
  connected_sensor_count: number;
  target_sensor_count: number;
  dropped_packets: number;
  all_com_ports?: ComPortInfo[];
  handshake_log?: string[];
  message_es: string;
}

export interface MocapFrame {
  seq: number;
  timestamp_ms: number;
  rate_hz: number;
  mode: 'live' | 'playback';
  root_mode: 'in_place' | 'free_walk';
  min_foot_y: number;
  skeleton_order: string[];
  segments: Record<string, SegmentPosePayload>;
  angles: Record<string, JointAngleTriple>;
  sensors: SensorDiagnostic[];
  calibration: CalibrationStatus;
  recording: RecordingStatus;
  awinda?: AwindaStatusPayload;
  simulator_active?: boolean;
  shake_detected: ShakeEvent | null;
}

export interface AnthropometricProfileDTO {
  id: string;
  name: string;
  height_cm: number;
  arm_span_cm?: number | null;
  hip_height_cm?: number | null;
  knee_height_cm?: number | null;
  ankle_height_cm?: number | null;
  shoulder_width_cm?: number | null;
  foot_length_cm?: number | null;
  hip_width_cm?: number | null;
  shoulder_height_cm?: number | null;
  custom_segments: Array<{
    name: string;
    parent: string;
    offset_m: number[];
    end_site_m?: number[];
    label_es?: string;
  }>;
  dimensions?: Record<string, number>;
  active?: boolean;
}

export interface TakeSummary {
  take_id: string;
  name: string;
  created_at: string;
  fps: number;
  frame_count: number;
  duration_s: number;
  size_kb: number;
}

export interface UpdateStatusPayload {
  state: 'checking' | 'available' | 'up-to-date' | 'downloaded' | 'error';
  currentVersion: string;
  version?: string;
  devMode?: boolean;
  message?: string;
}

export interface UpdateInfoPayload {
  version: string;
  releaseName?: string;
  releaseDate?: string;
  releaseNotes?: string;
  currentVersion: string;
}

export interface UpdateProgressPayload {
  percent: number;
  transferred: number;
  total: number;
  bytesPerSecond: number;
}

declare global {
  interface Window {
    openMocapDesktop?: {
      isElectron: boolean;
      selectBlenderExe: () => Promise<string | null>;
      openPath: (targetPath: string) => Promise<boolean>;
      openExternal?: (url: string) => Promise<boolean>;
      checkBackendHealth: () => Promise<boolean>;
      getAppVersion?: () => Promise<string>;
      checkForUpdates?: () => Promise<{ ok: boolean; devMode?: boolean; currentVersion?: string; version?: string; message?: string }>;
      downloadUpdate?: () => Promise<{ ok: boolean; message?: string }>;
      installUpdateNow?: () => Promise<{ ok: boolean }>;
      onUpdateStatus?: (cb: (payload: UpdateStatusPayload) => void) => () => void;
      onUpdateAvailable?: (cb: (payload: UpdateInfoPayload) => void) => () => void;
      onUpdateProgress?: (cb: (payload: UpdateProgressPayload) => void) => () => void;
      onUpdateDownloaded?: (cb: (payload: UpdateInfoPayload) => void) => () => void;
    };
  }
}

