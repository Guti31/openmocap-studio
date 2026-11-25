import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Battery,
  Bluetooth,
  Cpu,
  Plus,
  Radio,
  RefreshCw,
  RotateCcw,
  Ruler,
  Sparkles,
  Usb,
  Vibrate,
  Wifi,
} from 'lucide-react';
import { translations } from '../i18n';
import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';
import type { MotionPreset } from '../types/mocap';

const BODY_NODES: Array<{ seg: string; x: number; y: number; label: string }> = [
  { seg: 'HEAD', x: 110, y: 26, label: 'Cabeza' },
  { seg: 'STERNUM', x: 110, y: 74, label: 'Pecho' },
  { seg: 'PELVIS', x: 110, y: 122, label: 'Cintura' },
  { seg: 'SHOULDER_L', x: 138, y: 58, label: 'Hombro Izquierdo' },
  { seg: 'UPPER_ARM_L', x: 164, y: 74, label: 'Brazo Izquierdo' },
  { seg: 'FOREARM_L', x: 184, y: 98, label: 'Antebrazo Izquierdo' },
  { seg: 'HAND_L', x: 202, y: 120, label: 'Mano Izquierda' },
  { seg: 'SHOULDER_R', x: 82, y: 58, label: 'Hombro Derecho' },
  { seg: 'UPPER_ARM_R', x: 56, y: 74, label: 'Brazo Derecho' },
  { seg: 'FOREARM_R', x: 36, y: 98, label: 'Antebrazo Derecho' },
  { seg: 'HAND_R', x: 18, y: 120, label: 'Mano Derecha' },
  { seg: 'THIGH_L', x: 130, y: 162, label: 'Muslo Izquierdo' },
  { seg: 'SHIN_L', x: 134, y: 210, label: 'Pierna Izquierda' },
  { seg: 'FOOT_L', x: 142, y: 248, label: 'Pie Izquierdo' },
  { seg: 'THIGH_R', x: 90, y: 162, label: 'Muslo Derecho' },
  { seg: 'SHIN_R', x: 86, y: 210, label: 'Pierna Derecha' },
  { seg: 'FOOT_R', x: 78, y: 248, label: 'Pie Derecho' },
];

export const LeftHardwarePanel: React.FC = () => {
  const locale = useStudioStore((s) => s.locale);
  const advancedMode = useStudioStore((s) => s.advancedMode);
  const sensors = useStudioStore((s) => s.sensors);
  const calibration = useStudioStore((s) => s.calibration);
  const awinda = useStudioStore((s) => s.awinda);
  const simulatorActive = useStudioStore((s) => s.simulatorActive);
  const activeProfile = useStudioStore((s) => s.activeProfile);
  const setProfiles = useStudioStore((s) => s.setProfiles);
  const selectedSegment = useStudioStore((s) => s.selectedSegment);
  const setSelectedSegment = useStudioStore((s) => s.setSelectedSegment);
  const segmentToSensor = useStudioStore((s) => s.segmentToSensor);
  const setSegmentToSensor = useStudioStore((s) => s.setSegmentToSensor);
  const lastShake = useStudioStore((s) => s.lastShake);
  const setToast = useStudioStore((s) => s.setToast);

  const t = translations[locale];
  const [tab, setTab] = useState<'hardware' | 'bodymap'>('hardware');
  const [simPreset, setSimPreset] = useState<MotionPreset>('walk');
  const [simRate, setSimRate] = useState<number>(120);
  const [rfChannel, setRfChannel] = useState<number>(11);
  const [udpPort, setUdpPort] = useState<number>(9000);
  const [selectedPort, setSelectedPort] = useState<string>('');
  const [hwStatus, setHwStatus] = useState<any>(null);
  const [scanResult, setScanResult] = useState<any>(null);
  const [assignSensorId, setAssignSensorId] = useState<string>('');
  const [customSegName, setCustomSegName] = useState<string>('PROP_1');
  const [customParent, setCustomParent] = useState<string>('HAND_L');
  const [customSensorId, setCustomSensorId] = useState<string>('ESP32_PROP1');
  const [shakeListenMode, setShakeListenMode] = useState<boolean>(false);
  const [quickHeightCm, setQuickHeightCm] = useState<string>('175');
  const [reconnecting, setReconnecting] = useState<boolean>(false);
  const [scanningPorts, setScanningPorts] = useState<boolean>(false);
  const [usbScanReport, setUsbScanReport] = useState<any>(null);

  const refreshStatus = async () => {
    try {
      const st = await api.hardwareStatus();
      setHwStatus(st);
      if (st?.mapping?.segment_to_sensor) {
        setSegmentToSensor(st.mapping.segment_to_sensor);
      }
    } catch {
      // backend aún iniciando
    }
  };

  useEffect(() => {
    refreshStatus();
  }, []);

  useEffect(() => {
    if (activeProfile?.height_cm) {
      setQuickHeightCm(String(activeProfile.height_cm));
    }
  }, [activeProfile?.height_cm]);

  useEffect(() => {
    if (awinda?.channel && awinda.channel >= 11 && awinda.channel <= 25) {
      setRfChannel(awinda.channel);
    }
  }, [awinda?.channel]);

  useEffect(() => {
    setAssignSensorId(segmentToSensor[selectedSegment] ?? '');
  }, [selectedSegment, segmentToSensor]);

  useEffect(() => {
    if (shakeListenMode && lastShake) {
      setAssignSensorId(lastShake.sensor_id);
      setToast(`Detectado por agitación: ${lastShake.sensor_id} -> listo para asignar a ${selectedSegment}`);
    }
  }, [lastShake, shakeListenMode, selectedSegment, setToast]);

  const handleScanAll = async () => {
    try {
      const res = await api.hardwareScan();
      setScanResult(res);
      if (res.serial_ports?.length && !selectedPort) {
        setSelectedPort(res.serial_ports[0].port);
      }
      setToast(
        `Escaneo: ${res.xsens_stations?.length ?? 0} Xsens, ${res.serial_ports?.length ?? 0} COM, ${res.ble_devices?.length ?? 0} BLE`
      );
      await refreshStatus();
    } catch (err) {
      setToast((err as Error).message);
    }
  };

  const handleReconnectAntenna = async () => {
    setReconnecting(true);
    try {
      const res = await api.reconnectAwinda();
      setToast(res.message_es || 'Antena revisada');
      await refreshStatus();
    } catch (err) {
      setToast((err as Error).message);
    } finally {
      setReconnecting(false);
    }
  };

  const handleScanAllUsbPorts = async () => {
    setScanningPorts(true);
    try {
      const res = await api.scanAwindaPorts();
      setUsbScanReport(res);
      const ports = res?.all_com_ports ?? [];
      const aw = res?.awinda_status;
      setToast(
        aw?.running
          ? `Antena encontrada y encendida en ${aw.port} (Canal ${aw.channel})`
          : `Puertos detectados: ${ports.length}. ${aw?.message_es ?? ''}`
      );
      await refreshStatus();
    } catch (err) {
      setToast((err as Error).message);
    } finally {
      setScanningPorts(false);
    }
  };

  const handleApplyQuickHeight = async () => {
    const h = Number(quickHeightCm);
    if (!Number.isFinite(h) || h < 80 || h > 250) {
      setToast('Ingresa una estatura válida entre 80 y 250 cm.');
      return;
    }
    try {
      const base = activeProfile ?? { id: 'default_175', name: `Sujeto (${h} cm)` };
      const res = await api.upsertProfile({
        id: base.id,
        name: base.name,
        height_cm: h,
        arm_span_cm: activeProfile?.arm_span_cm ?? null,
        hip_height_cm: activeProfile?.hip_height_cm ?? null,
        knee_height_cm: activeProfile?.knee_height_cm ?? null,
        ankle_height_cm: activeProfile?.ankle_height_cm ?? null,
        shoulder_width_cm: activeProfile?.shoulder_width_cm ?? null,
        foot_length_cm: activeProfile?.foot_length_cm ?? null,
        hip_width_cm: activeProfile?.hip_width_cm ?? null,
        shoulder_height_cm: activeProfile?.shoulder_height_cm ?? null,
        activate: true,
      });
      setProfiles(res.profiles);
      setToast(`Estatura aplicada: ${h} cm`);
    } catch (err) {
      setToast((err as Error).message);
    }
  };

  const handleToggleVirtualDemo = async () => {
    try {
      if (simulatorActive) {
        await api.stopDriver('simulator');
        setToast('Demostración virtual detenida.');
      } else {
        await api.startDriver({ driver: 'simulator', preset: 'walk', rate_hz: 120 });
        setToast('Demostración virtual de 17 sensores iniciada.');
      }
      await refreshStatus();
    } catch (err) {
      setToast((err as Error).message);
    }
  };

  const simRunning = Boolean(hwStatus?.drivers?.simulator?.running ?? simulatorActive);

  // =====================================================================
  // MODO SIMPLE (POR DEFECTO): LIMPIO, CLARO Y SIN RUIDO TÉCNICO
  // =====================================================================
  if (!advancedMode) {
    const onlineCount = sensors.filter((s) => s.status === 'online' || s.status === 'interpolating').length;
    const radioCount = awinda?.connected_sensor_count ?? 0;
    const isDriverMissing = Boolean(awinda?.driver_missing);
    const isAntennaError = awinda?.antenna_state === 'error';
    const isNoResponse = awinda?.antenna_state === 'no_response';
    const isAntennaRunning = Boolean(
      awinda?.running && (awinda.antenna_state === 'radio_on' || awinda.antenna_state === 'streaming')
    );

    const statusColor = isDriverMissing || isAntennaError
      ? 'border-rose-500/50 bg-rose-500/10'
      : isNoResponse
      ? 'border-amber-500/50 bg-amber-500/10'
      : isAntennaRunning
      ? onlineCount > 0
        ? 'border-emerald-500/40 bg-emerald-500/10'
        : 'border-amber-500/40 bg-amber-500/10'
      : simulatorActive
      ? 'border-cyan-500/40 bg-cyan-500/10'
      : 'border-slate-700 bg-slate-900/90';

    const selectedNodeInfo = BODY_NODES.find((n) => n.seg === selectedSegment);

    return (
      <aside className="w-[310px] bg-[#111827] border-r border-slate-800 flex flex-col justify-between shrink-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5">
          {/* Tarjeta Grande: Estado de la Antena Awinda */}
          <section className={`rounded-xl border p-3.5 space-y-2.5 ${statusColor}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                {isDriverMissing || isNoResponse || isAntennaError ? (
                  <AlertTriangle className={`w-5 h-5 shrink-0 ${isDriverMissing || isAntennaError ? 'text-rose-400' : 'text-amber-400'}`} />
                ) : (
                  <Radio
                    className={`w-5 h-5 shrink-0 ${
                      isAntennaRunning ? (onlineCount > 0 ? 'text-emerald-400' : 'text-amber-400') : simulatorActive ? 'text-cyan-400' : 'text-slate-400'
                    }`}
                  />
                )}
                <h3 className="text-sm font-bold text-slate-100 truncate">{t.antennaCardTitle}</h3>
              </div>
              <span
                className={`text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${
                  isDriverMissing || isAntennaError
                    ? 'bg-rose-500/20 text-rose-300'
                    : isNoResponse
                    ? 'bg-amber-500/20 text-amber-300'
                    : isAntennaRunning
                    ? onlineCount > 0
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : 'bg-amber-500/20 text-amber-300'
                    : simulatorActive
                    ? 'bg-cyan-500/20 text-cyan-300'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                {isDriverMissing
                  ? 'Sin driver'
                  : isAntennaError
                  ? 'Error'
                  : isNoResponse
                  ? 'Sin respuesta'
                  : isAntennaRunning
                  ? `Radio ${radioCount}/17 · Datos ${onlineCount}/17`
                  : simulatorActive
                  ? 'Demo virtual'
                  : 'En espera'}
              </span>
            </div>

            {isAntennaRunning && (
              <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                <div className="rounded-md bg-slate-950/60 border border-slate-800 px-2 py-1 flex items-center justify-between">
                  <span className="text-slate-400 truncate">{t.radioLinkedLabel}</span>
                  <span className="font-mono font-bold text-cyan-300">{radioCount}/17</span>
                </div>
                <div className="rounded-md bg-slate-950/60 border border-slate-800 px-2 py-1 flex items-center justify-between">
                  <span className="text-slate-400 truncate">{t.streamingDataLabel}</span>
                  <span className={`font-mono font-bold ${onlineCount > 0 ? 'text-emerald-400' : 'text-amber-300'}`}>
                    {onlineCount}/17
                  </span>
                </div>
              </div>
            )}

            <p className="text-xs text-slate-300 leading-relaxed">
              {awinda?.message_es ??
                'Conecta tu antena USB Xsens Awinda. La radio se encenderá automáticamente.'}
            </p>

            <div className="space-y-1.5">
              <button
                disabled={reconnecting}
                onClick={handleReconnectAntenna}
                className="w-full py-2 px-3 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow shadow-cyan-600/20 transition"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${reconnecting ? 'animate-spin' : ''}`} />
                <span>{t.reconnectBtn}</span>
              </button>

              <button
                disabled={scanningPorts}
                onClick={handleScanAllUsbPorts}
                className="w-full py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-700 text-slate-200 text-xs font-medium flex items-center justify-center gap-2 transition"
              >
                <Usb className={`w-3.5 h-3.5 text-cyan-400 ${scanningPorts ? 'animate-pulse' : ''}`} />
                <span>{scanningPorts ? 'Escaneando puertos USB...' : t.scanUsbBtn}</span>
              </button>
            </div>

            {((usbScanReport?.all_com_ports ?? awinda?.all_com_ports ?? []).length > 0) && (
              <div className="pt-2 border-t border-slate-800/80 space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  Puertos USB / COM detectados
                </div>
                <div className="space-y-1 max-h-24 overflow-y-auto">
                  {(usbScanReport?.all_com_ports ?? awinda?.all_com_ports ?? []).map((cp: any) => {
                    const isActivePort = isAntennaRunning && awinda?.port === cp.port;
                    const isFailedPort = isNoResponse && awinda?.port === cp.port;
                    return (
                      <div
                        key={cp.port}
                        className={`px-2 py-1 rounded text-[10px] flex items-center justify-between border ${
                          isActivePort
                            ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                            : isFailedPort
                            ? 'bg-amber-500/15 border-amber-500/40 text-amber-300'
                            : cp.is_xsens
                            ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-200'
                            : 'bg-slate-950/70 border-slate-800 text-slate-400'
                        }`}
                      >
                        <span className="truncate pr-2">
                          <b className="font-mono">{cp.port}</b> · {cp.description}
                        </span>
                        <span className="shrink-0 font-semibold">
                          {isActivePort
                            ? 'Radio ON'
                            : isFailedPort
                            ? 'Sin ACK'
                            : cp.is_xsens
                            ? 'Xsens'
                            : 'USB'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </section>

          {/* Estatura rápida del usuario */}
          <section className="rounded-xl bg-slate-900/90 border border-slate-800 p-3 space-y-2">
            <label className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
              <Ruler className="w-4 h-4 text-cyan-400" />
              {t.userHeightLabel}
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                min={80}
                max={250}
                value={quickHeightCm}
                onChange={(e) => setQuickHeightCm(e.target.value)}
                className="w-24 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-sm font-mono text-slate-100 text-center"
              />
              <button
                onClick={handleApplyQuickHeight}
                className="flex-1 py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-cyan-300 transition"
              >
                {t.applyMeasuresBtn}
              </button>
            </div>
          </section>

          {/* Silueta Corporal Visual (Verde / Amarillo / Gris) */}
          <section className="rounded-xl bg-slate-900/90 border border-slate-800 p-3 flex flex-col items-center space-y-2">
            <div className="w-full flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-200">{t.suitSensorsTitle}</span>
              <span className="text-slate-400">
                {radioCount > 0 ? `Radio ${radioCount}/17 · ` : ''}{onlineCount}/17 {locale === 'es' ? 'enviando' : 'streaming'}
              </span>
            </div>

            <svg viewBox="0 0 220 270" className="w-full max-w-[205px] h-auto">
              <g stroke="#334155" strokeWidth="3.5" strokeLinecap="round">
                <line x1="110" y1="26" x2="110" y2="122" />
                <line x1="82" y1="58" x2="138" y2="58" />
                <line x1="138" y1="58" x2="202" y2="120" />
                <line x1="82" y1="58" x2="18" y2="120" />
                <line x1="90" y1="122" x2="130" y2="122" />
                <line x1="130" y1="122" x2="134" y2="210" />
                <line x1="134" y1="210" x2="142" y2="248" />
                <line x1="90" y1="122" x2="86" y2="210" />
                <line x1="86" y1="210" x2="78" y2="248" />
              </g>
              {BODY_NODES.map((node) => {
                const sid = segmentToSensor[node.seg];
                const diag = sensors.find((s) => s.sensor_id === sid);
                const isAlive = diag && (diag.status === 'online' || diag.status === 'interpolating');
                const isLowBattery = Boolean(
                  diag && ((diag.battery >= 0 && diag.battery <= 20) || diag.status === 'degraded')
                );
                const isSel = selectedSegment === node.seg;
                const fill = isAlive
                  ? isLowBattery
                    ? '#f59e0b'
                    : '#10b981'
                  : '#475569';

                return (
                  <g
                    key={node.seg}
                    onClick={() => setSelectedSegment(node.seg)}
                    className="cursor-pointer"
                  >
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={isSel ? 9 : 7}
                      fill={fill}
                      stroke={isSel ? '#ffffff' : '#0f172a'}
                      strokeWidth={isSel ? 2.5 : 1.5}
                    />
                    <title>
                      {`${node.label}: ${
                        isAlive
                          ? isLowBattery
                            ? 'Batería baja o señal débil'
                            : 'Conectado'
                          : 'Apagado / Sin señal'
                      }`}
                    </title>
                  </g>
                );
              })}
            </svg>

            <div className="text-[11px] text-slate-300 font-medium">
              {selectedNodeInfo ? selectedNodeInfo.label : 'Selecciona un punto del cuerpo'}
            </div>

            <div className="flex items-center justify-center gap-3 text-[10px] text-slate-400 pt-1">
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" /> Conectado
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500" /> Batería baja
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-full bg-slate-600" /> Apagado
              </span>
            </div>
          </section>
        </div>

        {/* Pie discreto: Demostración virtual */}
        <div className="p-3 border-t border-slate-800 bg-slate-900/60 space-y-2">
          {simulatorActive && (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-slate-400">{t.demoActionLabel}:</span>
              <select
                value={simPreset}
                onChange={async (e) => {
                  const p = e.target.value as MotionPreset;
                  setSimPreset(p);
                  await api.configSimulator({ preset: p, rate_hz: 120 });
                }}
                className="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
              >
                <option value="walk">{t.presets.walk}</option>
                <option value="squat">{t.presets.squat}</option>
                <option value="wave">{t.presets.wave}</option>
                <option value="tpose">{t.presets.tpose}</option>
              </select>
            </div>
          )}
          <button
            onClick={handleToggleVirtualDemo}
            className={`w-full py-2 px-2.5 rounded-lg text-[11px] font-medium flex items-center justify-center gap-1.5 border transition ${
              simulatorActive
                ? 'bg-slate-800 border-slate-700 text-rose-300 hover:bg-slate-700'
                : 'bg-slate-900 border-slate-700/80 text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span>
              {simulatorActive ? t.virtualDemoStop : t.virtualDemoAsk}
            </span>
          </button>
        </div>
      </aside>
    );
  }

  // =====================================================================
  // MODO AVANZADO: PANEL TÉCNICO COMPLETO
  // =====================================================================
  return (
    <aside className="w-[330px] bg-[#111827] border-r border-slate-800 flex flex-col shrink-0 overflow-hidden">
      <div className="grid grid-cols-2 border-b border-slate-800 bg-slate-900/60">
        <button
          onClick={() => setTab('hardware')}
          className={`py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 border-b-2 transition ${
            tab === 'hardware'
              ? 'border-cyan-500 text-cyan-300 bg-slate-800/40'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Cpu className="w-3.5 h-3.5" />
          <span>{t.hardwareTab}</span>
        </button>
        <button
          onClick={() => setTab('bodymap')}
          className={`py-2.5 text-xs font-semibold flex items-center justify-center gap-1.5 border-b-2 transition ${
            tab === 'bodymap'
              ? 'border-cyan-500 text-cyan-300 bg-slate-800/40'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          <span>{t.bodyMapTab}</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {tab === 'hardware' ? (
          <>
            <section className="rounded-lg bg-slate-900/80 border border-slate-800 p-2.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-cyan-300 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5" />
                  {t.simulatorTitle}
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                    simRunning ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-300'
                  }`}
                >
                  {simRunning ? 'ACTIVO' : 'OFF'}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                <div>
                  <label className="block text-[10px] text-slate-400 mb-0.5">{t.motionPreset}</label>
                  <select
                    value={simPreset}
                    onChange={async (e) => {
                      const p = e.target.value as MotionPreset;
                      setSimPreset(p);
                      await api.configSimulator({ preset: p, rate_hz: simRate });
                      refreshStatus();
                    }}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
                  >
                    {Object.entries(t.presets).map(([k, lbl]) => (
                      <option key={k} value={k}>
                        {lbl}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-slate-400 mb-0.5">{t.sampleRate}</label>
                  <select
                    value={simRate}
                    onChange={async (e) => {
                      const hz = Number(e.target.value);
                      setSimRate(hz);
                      await api.configSimulator({ preset: simPreset, rate_hz: hz });
                      refreshStatus();
                    }}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
                  >
                    <option value={60}>60 Hz</option>
                    <option value={100}>100 Hz</option>
                    <option value={120}>120 Hz</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-1.5">
                <button
                  onClick={async () => {
                    if (simRunning) await api.stopDriver('simulator');
                    else await api.startDriver({ driver: 'simulator', preset: simPreset, rate_hz: simRate });
                    refreshStatus();
                  }}
                  className={`flex-1 py-1.5 rounded text-xs font-medium transition ${
                    simRunning
                      ? 'bg-rose-600/80 hover:bg-rose-600 text-white'
                      : 'bg-cyan-600 hover:bg-cyan-500 text-white'
                  }`}
                >
                  {simRunning ? t.stopSim : t.startSim}
                </button>
                <button
                  onClick={async () => {
                    const target = segmentToSensor[selectedSegment] || '00B4D904';
                    await api.triggerSimulatorShake(target);
                    setToast(`Agitación simulada en ${target} (${selectedSegment})`);
                  }}
                  title={t.simulateShake}
                  className="px-2 py-1.5 rounded text-xs bg-amber-600/20 border border-amber-500/40 text-amber-300 hover:bg-amber-600/30"
                >
                  <Vibrate className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="flex gap-1.5">
                <button
                  onClick={async () => {
                    await api.configSimulator({ randomize_imperfections: true, noise_std_rad: 0.002 });
                    setToast('Inyectadas correas desalineadas + deriva magnética interior');
                    refreshStatus();
                  }}
                  className="flex-1 py-1 px-2 rounded text-[11px] bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-300"
                >
                  {t.injectImperfections}
                </button>
                <button
                  onClick={async () => {
                    await api.configSimulator({ clear_imperfections: true });
                    setToast('Sensores ideales restaurados');
                    refreshStatus();
                  }}
                  className="py-1 px-2 rounded text-[11px] bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300"
                  title={t.clearImperfections}
                >
                  <RotateCcw className="w-3 h-3" />
                </button>
              </div>
            </section>

            {/* Bloque Xsens Awinda USB (XDA + Xbus) */}
            <section className="rounded-lg bg-slate-900/80 border border-slate-800 p-2.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-cyan-400" />
                  {t.xsensTitle}
                </span>
                <button
                  onClick={handleScanAll}
                  className="text-[11px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
                >
                  <RefreshCw className="w-3 h-3" />
                  {t.scanHardware}
                </button>
              </div>
              <div className="text-[11px] text-slate-400 leading-snug">
                {awinda?.message_es ?? hwStatus?.drivers?.xsens_awinda?.message_es ?? 'Verificando Awinda...'}
              </div>
              <button
                disabled={scanningPorts}
                onClick={handleScanAllUsbPorts}
                className="w-full py-1 px-2 rounded text-[11px] bg-slate-800 hover:bg-slate-700 border border-slate-700 text-cyan-300 flex items-center justify-center gap-1.5"
              >
                <Usb className="w-3 h-3" />
                <span>Escanear Todos los Puertos USB</span>
              </button>
              <div className="flex items-center gap-1.5">
                <label className="text-[11px] text-slate-400">{t.rfChannel}:</label>
                <input
                  type="number"
                  min={11}
                  max={25}
                  value={rfChannel}
                  onChange={(e) => setRfChannel(Number(e.target.value))}
                  className="w-14 bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-xs text-slate-100"
                />
                <button
                  onClick={async () => {
                    const isUp = hwStatus?.drivers?.xsens_awinda?.running;
                    const res = isUp
                      ? await api.stopDriver('xsens_awinda')
                      : await api.reconnectAwinda(rfChannel);
                    setToast(res.message_es || 'Xsens actualizado');
                    refreshStatus();
                  }}
                  className="flex-1 py-1 px-2 rounded text-xs font-medium bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200"
                >
                  {hwStatus?.drivers?.xsens_awinda?.running ? t.disconnect : t.connect}
                </button>
              </div>
            </section>

            <section className="rounded-lg bg-slate-900/80 border border-slate-800 p-2.5 space-y-2">
              <div className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                <Usb className="w-3.5 h-3.5 text-cyan-400" />
                {t.serialUdpTitle}
              </div>
              <div className="flex gap-1.5">
                <select
                  value={selectedPort}
                  onChange={(e) => setSelectedPort(e.target.value)}
                  className="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
                >
                  <option value="">Auto COM</option>
                  {(scanResult?.serial_ports ?? hwStatus?.drivers?.serial_imu?.available_ports ?? []).map(
                    (p: any) => (
                      <option key={p.port} value={p.port}>
                        {p.port} - {p.description}
                      </option>
                    )
                  )}
                </select>
                <button
                  onClick={async () => {
                    const isUp = hwStatus?.drivers?.serial_imu?.running;
                    const res = isUp
                      ? await api.stopDriver('serial_imu')
                      : await api.startDriver({ driver: 'serial_imu', port: selectedPort, baudrate: 0 });
                    setToast(res.message_es);
                    refreshStatus();
                  }}
                  className="px-2.5 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200"
                >
                  {hwStatus?.drivers?.serial_imu?.running ? t.disconnect : 'COM'}
                </button>
              </div>

              <div className="flex items-center gap-1.5">
                <Wifi className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                <input
                  type="number"
                  value={udpPort}
                  onChange={(e) => setUdpPort(Number(e.target.value))}
                  className="w-20 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
                />
                <button
                  onClick={async () => {
                    const isUp = hwStatus?.drivers?.udp_osc?.running;
                    const res = isUp
                      ? await api.stopDriver('udp_osc')
                      : await api.startDriver({ driver: 'udp_osc', udp_port: udpPort });
                    setToast(res.message_es);
                    refreshStatus();
                  }}
                  className="flex-1 py-1 px-2 rounded text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200"
                >
                  {hwStatus?.drivers?.udp_osc?.running ? t.disconnect : t.listenUdp}
                </button>
              </div>

              <div className="flex items-center gap-1.5 pt-1 border-t border-slate-800">
                <Bluetooth className="w-3.5 h-3.5 text-blue-400 shrink-0" />
                <span className="text-[11px] text-slate-300 flex-1 truncate">{t.bleTitle}</span>
                {hwStatus?.drivers?.ble_imu?.running ? (
                  <button
                    onClick={async () => {
                      const res = await api.disconnectBle();
                      setToast(res.message_es || 'BLE desconectado');
                      refreshStatus();
                    }}
                    className="px-2.5 py-1 rounded text-xs bg-rose-600/20 hover:bg-rose-600/30 border border-rose-500/40 text-rose-300"
                  >
                    {t.disconnectBle}
                  </button>
                ) : (
                  <button
                    onClick={async () => {
                      const res = await api.startDriver({ driver: 'ble_imu' });
                      setToast(res.message_es);
                      refreshStatus();
                    }}
                    className="px-2.5 py-1 rounded text-xs bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/40 text-blue-300"
                  >
                    {t.scanBle}
                  </button>
                )}
              </div>
            </section>

            <section className="space-y-1.5">
              <div className="flex items-center justify-between text-[11px] text-slate-400 px-0.5">
                <span>
                  {t.sensorsActive} ({sensors.length})
                </span>
                <span>ID / Hz / Bat</span>
              </div>
              <div className="space-y-1 max-h-56 overflow-y-auto pr-0.5">
                {sensors.map((s) => (
                  <button
                    key={s.sensor_id}
                    onClick={() => {
                      if (s.segment !== 'UNASSIGNED') setSelectedSegment(s.segment);
                    }}
                    className={`w-full text-left px-2 py-1.5 rounded border text-[11px] flex items-center justify-between transition ${
                      selectedSegment === s.segment
                        ? 'bg-cyan-500/10 border-cyan-500/50'
                        : 'bg-slate-900/70 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="font-semibold text-slate-200 truncate">{s.segment}</div>
                      <div className="font-mono text-[10px] text-slate-400">
                        {s.sensor_id} · {s.protocol}
                      </div>
                    </div>
                    <div className="text-right font-mono shrink-0">
                      <div
                        className={
                          s.status === 'online'
                            ? 'text-emerald-400'
                            : s.status === 'lost'
                            ? 'text-rose-400'
                            : 'text-amber-400'
                        }
                      >
                        {s.hz.toFixed(0)} Hz
                      </div>
                      <div className="text-[10px] text-slate-400 flex items-center justify-end gap-1">
                        <Battery className="w-3 h-3" />
                        {s.battery >= 0 ? `${s.battery.toFixed(0)}%` : 'USB'}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </section>
          </>
        ) : (
          <div className="space-y-3">
            <div className="rounded-lg bg-slate-950/90 border border-slate-800 p-2 flex flex-col items-center">
              <svg viewBox="0 0 220 270" className="w-full max-w-[235px] h-auto">
                <g stroke="#334155" strokeWidth="3" strokeLinecap="round">
                  <line x1="110" y1="26" x2="110" y2="122" />
                  <line x1="82" y1="58" x2="138" y2="58" />
                  <line x1="138" y1="58" x2="202" y2="120" />
                  <line x1="82" y1="58" x2="18" y2="120" />
                  <line x1="90" y1="122" x2="130" y2="122" />
                  <line x1="130" y1="122" x2="134" y2="210" />
                  <line x1="134" y1="210" x2="142" y2="248" />
                  <line x1="90" y1="122" x2="86" y2="210" />
                  <line x1="86" y1="210" x2="78" y2="248" />
                </g>
                {BODY_NODES.map((node) => {
                  const sid = segmentToSensor[node.seg];
                  const diag = sensors.find((s) => s.sensor_id === sid);
                  const isCal = Boolean(calibration?.reports?.[node.seg]);
                  const isSel = selectedSegment === node.seg;
                  const fill =
                    diag?.status === 'online'
                      ? isCal
                        ? '#10b981'
                        : '#06b6d4'
                      : sid
                      ? '#f59e0b'
                      : '#475569';
                  return (
                    <g
                      key={node.seg}
                      onClick={() => setSelectedSegment(node.seg)}
                      className="cursor-pointer"
                    >
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={isSel ? 9 : 7}
                        fill={fill}
                        stroke={isSel ? '#ffffff' : '#0f172a'}
                        strokeWidth={isSel ? 2.5 : 1.5}
                      />
                      <title>{`${node.label} (${node.seg}): ${sid ?? 'Sin asignar'}`}</title>
                    </g>
                  );
                })}
              </svg>
              <div className="text-[11px] text-slate-400 mt-1">
                Segmento: <span className="font-mono text-cyan-300">{selectedSegment}</span>
              </div>
            </div>

            <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-2.5 space-y-2">
              <button
                onClick={() => setShakeListenMode(!shakeListenMode)}
                className={`w-full py-1.5 px-2 rounded text-xs font-medium flex items-center justify-center gap-1.5 border transition ${
                  shakeListenMode
                    ? 'bg-amber-500/20 border-amber-400 text-amber-300 animate-pulse'
                    : 'bg-slate-800 border-slate-700 text-slate-200 hover:border-amber-500/50'
                }`}
              >
                <Vibrate className="w-3.5 h-3.5" />
                <span>{t.shakePrompt}</span>
              </button>

              <div className="flex gap-1.5">
                <input
                  value={assignSensorId}
                  onChange={(e) => setAssignSensorId(e.target.value)}
                  placeholder={t.sensorIdLabel}
                  className="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
                <button
                  onClick={async () => {
                    if (!assignSensorId.trim()) return;
                    const res = await api.assignSensor(assignSensorId.trim(), selectedSegment);
                    setSegmentToSensor(res.segment_to_sensor);
                    setToast(`Asignado ${assignSensorId.toUpperCase()} -> ${selectedSegment}`);
                  }}
                  className="px-3 py-1 rounded text-xs font-medium bg-cyan-600 hover:bg-cyan-500 text-white"
                >
                  {t.assignSensor}
                </button>
              </div>

              <button
                onClick={async () => {
                  const res = await api.resetDefaultMapping();
                  setSegmentToSensor(res.segment_to_sensor);
                  setToast('Restaurados los 17 IDs Xsens Awinda predeterminados');
                }}
                className="w-full py-1 rounded text-[11px] bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300"
              >
                {t.resetDefaultAwinda}
              </button>
            </div>

            <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-2.5 space-y-2">
              <div className="text-xs font-semibold text-slate-200 flex items-center gap-1">
                <Plus className="w-3.5 h-3.5 text-cyan-400" />
                {t.addCustomSensor}
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <input
                  value={customSegName}
                  onChange={(e) => setCustomSegName(e.target.value)}
                  placeholder={t.segmentName}
                  className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
                <select
                  value={customParent}
                  onChange={(e) => setCustomParent(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
                >
                  {BODY_NODES.map((n) => (
                    <option key={n.seg} value={n.seg}>
                      {n.seg}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex gap-1.5">
                <input
                  value={customSensorId}
                  onChange={(e) => setCustomSensorId(e.target.value)}
                  placeholder={t.sensorIdLabel}
                  className="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
                <button
                  onClick={async () => {
                    try {
                      const res = await api.addCustomSegment({
                        name: customSegName,
                        parent: customParent,
                        offset_m: [0.08, 0.0, 0.0],
                        sensor_id: customSensorId,
                      });
                      if (res.mapping?.segment_to_sensor) {
                        setSegmentToSensor(res.mapping.segment_to_sensor);
                      }
                      setToast(`Sensor personalizado ${customSegName.toUpperCase()} agregado`);
                    } catch (err) {
                      setToast((err as Error).message);
                    }
                  }}
                  className="px-3 py-1 rounded text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white"
                >
                  +
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
