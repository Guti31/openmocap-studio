import type { AnthropometricProfileDTO, MotionPreset } from '../types/mocap';

export const API_BASE = 'http://127.0.0.1:8000/api';
export const WS_URL = 'ws://127.0.0.1:8000/ws/stream';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = `Error HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // ignorar si no es JSON
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; ffmpeg_available: boolean; blender: { blender_found: boolean; blender_path: string | null } }>('/health'),

  hardwareStatus: () => request<any>('/hardware/status'),
  hardwareScan: () => request<any>('/hardware/scan', { method: 'POST' }),
  awindaStatus: () => request<any>('/hardware/awinda/status'),
  scanAwindaPorts: () => request<any>('/hardware/awinda/scan', { method: 'POST' }),
  reconnectAwinda: (channel?: number) =>
    request<any>('/hardware/awinda/reconnect', {
      method: 'POST',
      body: JSON.stringify(channel !== undefined ? { channel } : {}),
    }),

  startDriver: (payload: Record<string, unknown>) =>
    request<any>('/hardware/driver/start', { method: 'POST', body: JSON.stringify(payload) }),
  stopDriver: (driver: string) =>
    request<any>('/hardware/driver/stop', { method: 'POST', body: JSON.stringify({ driver }) }),
  disconnectBle: () => request<any>('/hardware/ble/disconnect', { method: 'POST' }),

  configSimulator: (payload: {
    preset?: MotionPreset;
    rate_hz?: number;
    randomize_imperfections?: boolean;
    clear_imperfections?: boolean;
    noise_std_rad?: number;
    seed?: number;
  }) => request<any>('/hardware/simulator/config', { method: 'POST', body: JSON.stringify(payload) }),

  triggerSimulatorShake: (sensor_id: string) =>
    request<any>('/hardware/simulator/shake', { method: 'POST', body: JSON.stringify({ sensor_id, duration_s: 0.7 }) }),

  getMapping: () => request<any>('/mapping'),
  assignSensor: (sensor_id: string, segment: string) =>
    request<any>('/mapping/assign', { method: 'POST', body: JSON.stringify({ sensor_id, segment }) }),
  unassignSensor: (sensor_id: string) =>
    request<any>(`/mapping/unassign?sensor_id=${encodeURIComponent(sensor_id)}`, { method: 'POST' }),
  addCustomSegment: (payload: {
    name: string;
    parent: string;
    offset_m: number[];
    end_site_m?: number[];
    label_es?: string;
    sensor_id?: string;
  }) => request<any>('/mapping/add-custom', { method: 'POST', body: JSON.stringify(payload) }),
  resetDefaultMapping: () => request<any>('/mapping/reset-default', { method: 'POST' }),

  listProfiles: () => request<{ profiles: AnthropometricProfileDTO[]; active_skeleton: any }>('/profiles'),
  upsertProfile: (profile: Partial<AnthropometricProfileDTO> & { activate?: boolean }) =>
    request<any>('/profiles', { method: 'POST', body: JSON.stringify(profile) }),
  activateProfile: (profileId: string) =>
    request<any>(`/profiles/${encodeURIComponent(profileId)}/activate`, { method: 'POST' }),
  deleteProfile: (profileId: string) =>
    request<any>(`/profiles/${encodeURIComponent(profileId)}`, { method: 'DELETE' }),

  startStaticCalibration: (pose_type: 'tpose' | 'npose', duration_s = 4.0, mode: 'full' | 'quick' = 'full') =>
    request<any>('/calibration/start-static', { method: 'POST', body: JSON.stringify({ pose_type, duration_s, mode }) }),
  startStraightCalibration: (duration_s = 3.0, complete_after = false) =>
    request<any>('/calibration/start-straight', {
      method: 'POST',
      body: JSON.stringify({ duration_s, complete_after }),
    }),
  completeQuickCalibration: () => request<any>('/calibration/complete-quick', { method: 'POST' }),
  startWalkCalibration: (duration_s = 6.0) =>
    request<any>('/calibration/start-walk', { method: 'POST', body: JSON.stringify({ duration_s }) }),
  resetCalibration: () => request<any>('/calibration/reset', { method: 'POST' }),
  headingReset: () => request<any>('/calibration/heading-reset', { method: 'POST' }),

  startRecording: (name?: string) =>
    request<any>('/recording/start', { method: 'POST', body: JSON.stringify({ name }) }),
  stopRecording: () => request<any>('/recording/stop', { method: 'POST' }),
  listTakes: () => request<{ takes: any[]; status: any }>('/recording/takes'),
  loadTake: (takeId: string) => request<any>(`/recording/load/${encodeURIComponent(takeId)}`, { method: 'POST' }),

  playbackControl: (payload: Record<string, unknown>) =>
    request<any>('/playback/control', { method: 'POST', body: JSON.stringify(payload) }),
  setRootMode: (mode: 'in_place' | 'free_walk') =>
    request<any>('/fk/mode', { method: 'POST', body: JSON.stringify({ mode }) }),

  blenderStatus: () => request<{ blender_found: boolean; blender_path: string | null }>('/export/blender-status'),
  setBlenderPath: (blender_path: string) =>
    request<any>('/export/blender-path', { method: 'POST', body: JSON.stringify({ blender_path }) }),
  exportBvh: (payload: Record<string, unknown>) =>
    request<any>('/export/bvh', { method: 'POST', body: JSON.stringify(payload) }),
  exportFbx: (payload: Record<string, unknown>) =>
    request<any>('/export/fbx', { method: 'POST', body: JSON.stringify(payload) }),
  listExportFiles: () => request<any>('/export/files'),

  convertVideoMp4: async (blob: Blob, filename: string, fps = 60) => {
    const fd = new FormData();
    fd.append('file', blob, `${filename}.webm`);
    fd.append('filename', filename);
    fd.append('fps', String(fps));
    const res = await fetch(`${API_BASE}/video/convert-mp4`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`Error convirtiendo video (${res.status})`);
    return res.json();
  },
};

