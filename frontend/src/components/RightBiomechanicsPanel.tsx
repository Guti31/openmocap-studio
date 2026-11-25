import React from 'react';
import { Activity, Compass, ShieldCheck } from 'lucide-react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { translations } from '../i18n';
import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';

export const RightBiomechanicsPanel: React.FC = () => {
  const locale = useStudioStore((s) => s.locale);
  const selectedJoint = useStudioStore((s) => s.selectedJoint);
  const setSelectedJoint = useStudioStore((s) => s.setSelectedJoint);
  const latestAngles = useStudioStore((s) => s.latestAngles);
  const angleHistory = useStudioStore((s) => s.angleHistory);
  const calibration = useStudioStore((s) => s.calibration);
  const setToast = useStudioStore((s) => s.setToast);

  const t = translations[locale];
  const current = latestAngles[selectedJoint] ?? { flexion: 0, abduction: 0, rotation: 0 };
  const chartData = angleHistory[selectedJoint] ?? [];

  const handleQuickHeadingReset = async () => {
    try {
      const res = await api.headingReset();
      setToast(res.message_es || 'Rumbo reiniciado.');
    } catch (err) {
      setToast((err as Error).message);
    }
  };

  return (
    <aside className="w-[330px] bg-[#111827] border-l border-slate-800 flex flex-col shrink-0 overflow-hidden">
      <div className="px-3 py-2.5 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between">
        <span className="text-xs font-semibold text-cyan-300 flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5" />
          {t.biomechanicsTitle}
        </span>
        <button
          onClick={handleQuickHeadingReset}
          className="text-[11px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-cyan-300 flex items-center gap-1"
        >
          <Compass className="w-3 h-3" />
          {t.quickHeadingReset}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Selector de articulación */}
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">{t.selectJoint}</label>
          <select
            value={selectedJoint}
            onChange={(e) => setSelectedJoint(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded-md px-2.5 py-1.5 text-xs text-slate-100"
          >
            {Object.entries(t.joints).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {/* Lectura instantánea */}
        <div className="grid grid-cols-3 gap-1.5">
          <div className="rounded-md bg-slate-900/90 border border-slate-800 p-2">
            <div className="text-[10px] text-cyan-400 truncate">{t.flexion}</div>
            <div className="text-base font-mono font-semibold text-slate-100 tabular-nums mt-0.5">
              {current.flexion.toFixed(1)}°
            </div>
          </div>
          <div className="rounded-md bg-slate-900/90 border border-slate-800 p-2">
            <div className="text-[10px] text-emerald-400 truncate">{t.abduction}</div>
            <div className="text-base font-mono font-semibold text-slate-100 tabular-nums mt-0.5">
              {current.abduction.toFixed(1)}°
            </div>
          </div>
          <div className="rounded-md bg-slate-900/90 border border-slate-800 p-2">
            <div className="text-[10px] text-amber-400 truncate">{t.rotation}</div>
            <div className="text-base font-mono font-semibold text-slate-100 tabular-nums mt-0.5">
              {current.rotation.toFixed(1)}°
            </div>
          </div>
        </div>

        {/* Gráfica temporal Recharts */}
        <div className="rounded-lg bg-slate-950/90 border border-slate-800 p-2 h-52">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 6, right: 8, left: -24, bottom: 2 }}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey="t" tick={{ fontSize: 10, fill: '#64748b' }} hide />
              <YAxis domain={[-180, 180]} tick={{ fontSize: 10, fill: '#94a3b8' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0f172a',
                  borderColor: '#334155',
                  fontSize: '11px',
                }}
              />
              <Line
                type="monotone"
                dataKey="flexion"
                name={t.flexion}
                stroke="#06b6d4"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="abduction"
                name={t.abduction}
                stroke="#10b981"
                strokeWidth={1.6}
                dot={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="rotation"
                name={t.rotation}
                stroke="#f59e0b"
                strokeWidth={1.6}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Resumen de calibración */}
        <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-2.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              {t.calibrationQuality}
            </span>
            <span className="text-xs font-mono text-emerald-400">
              {calibration?.overall_quality_pct ?? 0}%
            </span>
          </div>
          <div className="text-[11px] text-slate-400 leading-snug">
            {calibration?.message_es ?? 'Ejecute el asistente para calibrar sensores y corregir deriva magnética.'}
          </div>

          {calibration?.reports && Object.keys(calibration.reports).length > 0 && (
            <div className="max-h-40 overflow-y-auto space-y-1 pt-1 border-t border-slate-800">
              {Object.values(calibration.reports).map((rep) => (
                <div
                  key={rep.segment}
                  className="flex items-center justify-between text-[10px] font-mono text-slate-300"
                >
                  <span>{rep.segment}</span>
                  <span>
                    <span className="text-cyan-400">{rep.yaw_correction_deg.toFixed(1)}°</span>
                    <span className="text-slate-600 mx-1">|</span>
                    <span className="text-emerald-400">{rep.quality_pct.toFixed(0)}%</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};

