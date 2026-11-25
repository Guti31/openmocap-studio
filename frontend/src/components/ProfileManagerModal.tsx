import React, { useEffect, useState } from 'react';
import { Check, Plus, Trash2, UserPlus, X } from 'lucide-react';
import { translations } from '../i18n';
import { api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';
import type { AnthropometricProfileDTO } from '../types/mocap';

export const ProfileManagerModal: React.FC = () => {
  const open = useStudioStore((s) => s.profileModalOpen);
  const setOpen = useStudioStore((s) => s.setProfileModalOpen);
  const locale = useStudioStore((s) => s.locale);
  const profiles = useStudioStore((s) => s.profiles);
  const activeProfile = useStudioStore((s) => s.activeProfile);
  const setProfiles = useStudioStore((s) => s.setProfiles);
  const setToast = useStudioStore((s) => s.setToast);

  const t = translations[locale];
  const [editingId, setEditingId] = useState<string>('');
  const [name, setName] = useState<string>('Nuevo Sujeto');
  const [heightCm, setHeightCm] = useState<string>('175');
  const [armSpanCm, setArmSpanCm] = useState<string>('');
  const [hipHeightCm, setHipHeightCm] = useState<string>('');
  const [kneeHeightCm, setKneeHeightCm] = useState<string>('');
  const [ankleHeightCm, setAnkleHeightCm] = useState<string>('');
  const [shoulderWidthCm, setShoulderWidthCm] = useState<string>('');
  const [footLengthCm, setFootLengthCm] = useState<string>('');

  const loadIntoForm = (p: AnthropometricProfileDTO) => {
    setEditingId(p.id);
    setName(p.name);
    setHeightCm(String(p.height_cm));
    setArmSpanCm(p.arm_span_cm != null ? String(p.arm_span_cm) : '');
    setHipHeightCm(p.hip_height_cm != null ? String(p.hip_height_cm) : '');
    setKneeHeightCm(p.knee_height_cm != null ? String(p.knee_height_cm) : '');
    setAnkleHeightCm(p.ankle_height_cm != null ? String(p.ankle_height_cm) : '');
    setShoulderWidthCm(p.shoulder_width_cm != null ? String(p.shoulder_width_cm) : '');
    setFootLengthCm(p.foot_length_cm != null ? String(p.foot_length_cm) : '');
  };

  useEffect(() => {
    if (open && activeProfile) {
      loadIntoForm(activeProfile);
    }
  }, [open, activeProfile]);

  if (!open) return null;

  const numOrNull = (val: string) => {
    const n = Number(val);
    return val.trim() !== '' && Number.isFinite(n) && n > 0 ? n : null;
  };

  const handleSave = async () => {
    const h = Number(heightCm);
    if (!Number.isFinite(h) || h < 80 || h > 250) {
      setToast('La estatura es obligatoria (80 - 250 cm).');
      return;
    }
    try {
      const res = await api.upsertProfile({
        id: editingId || undefined,
        name: name.trim() || `Sujeto ${h} cm`,
        height_cm: h,
        arm_span_cm: numOrNull(armSpanCm),
        hip_height_cm: numOrNull(hipHeightCm),
        knee_height_cm: numOrNull(kneeHeightCm),
        ankle_height_cm: numOrNull(ankleHeightCm),
        shoulder_width_cm: numOrNull(shoulderWidthCm),
        foot_length_cm: numOrNull(footLengthCm),
        activate: true,
      });
      setProfiles(res.profiles);
      setToast(`Perfil guardado y activado: ${res.profile.name}`);
    } catch (err) {
      setToast((err as Error).message);
    }
  };

  const handleNew = () => {
    setEditingId('');
    setName('Sujeto Nuevo');
    setHeightCm('172');
    setArmSpanCm('');
    setHipHeightCm('');
    setKneeHeightCm('');
    setAnkleHeightCm('');
    setShoulderWidthCm('');
    setFootLengthCm('');
  };

  const hMeters = (Number(heightCm) || 175) / 100;
  const previewThigh = numOrNull(hipHeightCm) && numOrNull(kneeHeightCm)
    ? ((Number(hipHeightCm) - Number(kneeHeightCm)) / 100).toFixed(3)
    : (0.245 * hMeters).toFixed(3);
  const previewShin = numOrNull(kneeHeightCm) && numOrNull(ankleHeightCm)
    ? ((Number(kneeHeightCm) - Number(ankleHeightCm)) / 100).toFixed(3)
    : (0.246 * hMeters).toFixed(3);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-3xl bg-[#111827] border border-slate-700 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/70">
          <h2 className="text-sm font-semibold text-slate-100">{t.profilesModalTitle}</h2>
          <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 flex-1 overflow-hidden">
          {/* Lista de perfiles */}
          <div className="border-r border-slate-800 p-3 space-y-2 overflow-y-auto bg-slate-950/40">
            <button
              onClick={handleNew}
              className="w-full py-1.5 px-2.5 rounded-md bg-cyan-600/20 border border-cyan-500/40 text-cyan-300 text-xs font-medium flex items-center justify-center gap-1.5 hover:bg-cyan-600/30"
            >
              <UserPlus className="w-3.5 h-3.5" />
              {t.createNewProfile}
            </button>

            <div className="space-y-1.5">
              {profiles.map((p) => (
                <div
                  key={p.id}
                  onClick={() => loadIntoForm(p)}
                  className={`p-2 rounded-md border cursor-pointer transition ${
                    p.id === editingId
                      ? 'bg-slate-800 border-cyan-500/60'
                      : 'bg-slate-900/80 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-100 truncate">{p.name}</span>
                    {p.active && <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                  </div>
                  <div className="text-[11px] font-mono text-slate-400">{p.height_cm} cm</div>
                  <div className="flex gap-1 mt-1.5">
                    {!p.active && (
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          const res = await api.activateProfile(p.id);
                          setProfiles(res.profiles);
                        }}
                        className="px-2 py-0.5 rounded text-[10px] bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30"
                      >
                        {t.activate}
                      </button>
                    )}
                    {p.id !== 'default_175' && (
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          const res = await api.deleteProfile(p.id);
                          setProfiles(res.profiles);
                        }}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-rose-600/20 text-rose-300 hover:bg-rose-600/30 ml-auto"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Formulario */}
          <div className="md:col-span-2 p-4 overflow-y-auto space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">{t.subjectNameLabel}</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-100"
                />
              </div>
              <div>
                <label className="block text-[11px] text-cyan-300 font-medium mb-1">{t.heightCm}</label>
                <input
                  type="number"
                  value={heightCm}
                  onChange={(e) => setHeightCm(e.target.value)}
                  className="w-full bg-slate-950 border border-cyan-600/50 rounded px-2.5 py-1.5 text-xs font-mono text-slate-100"
                />
              </div>
            </div>

            <div className="text-[11px] text-slate-400 pt-1 border-t border-slate-800">
              {t.optionalWinterHint}
            </div>

            <div className="grid grid-cols-3 gap-2.5">
              <div>
                <label className="block text-[10px] text-slate-400 mb-0.5">{t.armSpanCm}</label>
                <input
                  type="number"
                  placeholder={`${(Number(heightCm) || 175).toFixed(0)}`}
                  value={armSpanCm}
                  onChange={(e) => setArmSpanCm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-400 mb-0.5">{t.hipHeightCm}</label>
                <input
                  type="number"
                  placeholder={`${((Number(heightCm) || 175) * 0.53).toFixed(1)}`}
                  value={hipHeightCm}
                  onChange={(e) => setHipHeightCm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-400 mb-0.5">{t.kneeHeightCm}</label>
                <input
                  type="number"
                  placeholder={`${((Number(heightCm) || 175) * 0.285).toFixed(1)}`}
                  value={kneeHeightCm}
                  onChange={(e) => setKneeHeightCm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-400 mb-0.5">{t.ankleHeightCm}</label>
                <input
                  type="number"
                  placeholder={`${((Number(heightCm) || 175) * 0.039).toFixed(1)}`}
                  value={ankleHeightCm}
                  onChange={(e) => setAnkleHeightCm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-400 mb-0.5">{t.shoulderWidthCm}</label>
                <input
                  type="number"
                  placeholder={`${((Number(heightCm) || 175) * 0.258).toFixed(1)}`}
                  value={shoulderWidthCm}
                  onChange={(e) => setShoulderWidthCm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-400 mb-0.5">{t.footLengthCm}</label>
                <input
                  type="number"
                  placeholder={`${((Number(heightCm) || 175) * 0.152).toFixed(1)}`}
                  value={footLengthCm}
                  onChange={(e) => setFootLengthCm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
                />
              </div>
            </div>

            <div className="rounded-lg bg-slate-900 border border-slate-800 p-3 text-xs space-y-1">
              <div className="font-semibold text-cyan-300">{t.winterPreview}</div>
              <div className="grid grid-cols-3 gap-2 font-mono text-[11px] text-slate-300">
                <div>Muslo: {previewThigh} m</div>
                <div>Pantorrilla: {previewShin} m</div>
                <div>Brazo: {(0.186 * hMeters).toFixed(3)} m</div>
                <div>Antebrazo: {(0.146 * hMeters).toFixed(3)} m</div>
                <div>Pelvis Y: {(0.53 * hMeters).toFixed(3)} m</div>
                <div>Pie: {(0.152 * hMeters).toFixed(3)} m</div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setOpen(false)}
                className="px-4 py-1.5 rounded text-xs bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                {t.close}
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-1.5 rounded text-xs font-semibold bg-cyan-600 hover:bg-cyan-500 text-white flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                {t.save} y {t.activate}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

