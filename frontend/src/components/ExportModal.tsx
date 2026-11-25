import React, { useEffect, useState } from 'react';
import { Box, ChevronDown, Download, FileCode2, FolderOpen, Video, VideoOff, X } from 'lucide-react';
import { translations } from '../i18n';
import { API_BASE, api } from '../services/api';
import { useStudioStore } from '../store/useStudioStore';

interface ExportModalProps {
  onToggleVideoRecord: () => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({ onToggleVideoRecord }) => {
  const open = useStudioStore((s) => s.exportModalOpen);
  const setOpen = useStudioStore((s) => s.setExportModalOpen);
  const locale = useStudioStore((s) => s.locale);
  const advancedMode = useStudioStore((s) => s.advancedMode);
  const recording = useStudioStore((s) => s.recording);
  const isVideoRecording = useStudioStore((s) => s.isVideoRecording);
  const setToast = useStudioStore((s) => s.setToast);

  const t = translations[locale];
  const [fileName, setFileName] = useState<string>('captura_estudio');
  const [naming, setNaming] = useState<'openmocap' | 'mixamo' | 'rigify'>('openmocap');
  const [scale, setScale] = useState<number>(1.0);
  const [includeTpose, setIncludeTpose] = useState<boolean>(true);
  const [tposeLeadInOut, setTposeLeadInOut] = useState<boolean>(true);
  const [respectTrim, setRespectTrim] = useState<boolean>(true);
  const [showAdvancedExport, setShowAdvancedExport] = useState<boolean>(false);
  const [blenderStatus, setBlenderStatus] = useState<{
    blender_found: boolean;
    blender_path: string | null;
  }>({ blender_found: false, blender_path: null });
  const [customBlenderInput, setCustomBlenderInput] = useState<string>('');
  const [filesData, setFilesData] = useState<any>(null);
  const [busy, setBusy] = useState<boolean>(false);

  const refreshAll = async () => {
    try {
      const [bl, fl] = await Promise.all([api.blenderStatus(), api.listExportFiles()]);
      setBlenderStatus(bl);
      setFilesData(fl);
      if (bl.blender_path) setCustomBlenderInput(bl.blender_path);
    } catch {
      // ignorar
    }
  };

  useEffect(() => {
    if (open) {
      if (recording?.recording_name) {
        setFileName(recording.recording_name);
      }
      refreshAll();
    }
  }, [open, recording?.recording_name]);

  if (!open) return null;

  const hasFrames = (recording?.frame_count ?? 0) > 0;

  const handleExportBvh = async () => {
    setBusy(true);
    try {
      const res = await api.exportBvh({
        file_name: fileName,
        scale,
        naming,
        include_tpose_frame0: includeTpose,
        respect_trim: respectTrim,
        tpose_lead_in_out: tposeLeadInOut,
      });
      setToast(`Archivo .BVH guardado (${res.frames} cuadros): ${res.file_name}`);
      await refreshAll();
    } catch (err) {
      setToast((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleExportFbx = async () => {
    setBusy(true);
    try {
      const res = await api.exportFbx({
        file_name: fileName,
        scale,
        naming,
        include_tpose_frame0: includeTpose,
        respect_trim: respectTrim,
        tpose_lead_in_out: tposeLeadInOut,
      });
      setToast(`Archivo .FBX creado para Blender: ${res.fbx?.file_name}`);
      await refreshAll();
    } catch (err) {
      setToast((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleBrowseBlender = async () => {
    if (window.openMocapDesktop?.selectBlenderExe) {
      const chosen = await window.openMocapDesktop.selectBlenderExe();
      if (chosen) {
        setCustomBlenderInput(chosen);
        const res = await api.setBlenderPath(chosen);
        setBlenderStatus(res.status);
      }
    } else if (customBlenderInput.trim()) {
      try {
        const res = await api.setBlenderPath(customBlenderInput.trim());
        setBlenderStatus(res.status);
        setToast('Ruta de Blender guardada');
      } catch (err) {
        setToast((err as Error).message);
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-[#111827] border border-slate-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/70">
          <h2 className="text-base font-bold text-slate-100">{t.exportModalTitle}</h2>
          <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4">
          {/* Bloque 1: Video MP4 directo del visor 3D */}
          <div className="rounded-xl bg-slate-900/90 border border-slate-800 p-3.5 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-100">{t.videoMp4SectionTitle}</div>
              <div className="text-xs text-slate-400">
                {t.videoMp4SectionDesc}
              </div>
            </div>
            <button
              onClick={() => {
                onToggleVideoRecord();
                if (!isVideoRecording) setOpen(false);
              }}
              className={`px-4 py-2 rounded-lg text-xs font-bold flex items-center gap-2 shrink-0 transition ${
                isVideoRecording
                  ? 'bg-rose-600 text-white animate-pulse'
                  : 'bg-slate-800 hover:bg-slate-700 border border-slate-700 text-cyan-300'
              }`}
            >
              {isVideoRecording ? <VideoOff className="w-4 h-4" /> : <Video className="w-4 h-4" />}
              <span>{isVideoRecording ? t.stopSaveVideoMp4 : t.startVideoMp4}</span>
            </button>
          </div>

          {/* Bloque 2: Exportación 3D para Blender */}
          {!hasFrames && (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/40 text-xs text-amber-300">
              {t.exportNoFramesHint}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">{t.fileNameLabel}</label>
              <input
                value={fileName}
                onChange={(e) => setFileName(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-100"
              />
            </div>
            <div>
              <label className="block text-[11px] text-slate-400 mb-1">{t.rigNaming}</label>
              <select
                value={naming}
                onChange={(e) => setNaming(e.target.value as 'openmocap' | 'mixamo' | 'rigify')}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-100"
              >
                <option value="openmocap">Estándar (OpenMocap / Blender)</option>
                <option value="mixamo">Mixamo</option>
                <option value="rigify">Blender Rigify</option>
              </select>
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-200 bg-slate-900/70 border border-slate-800 rounded-lg px-3 py-2 cursor-pointer">
            <input
              type="checkbox"
              checked={tposeLeadInOut}
              onChange={(e) => setTposeLeadInOut(e.target.checked)}
              className="accent-cyan-500"
            />
            <span>{t.exportLeadInOutLabel}</span>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <button
              disabled={!hasFrames || busy}
              onClick={handleExportBvh}
              className="py-2.5 px-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-xs font-bold flex items-center justify-center gap-2"
            >
              <FileCode2 className="w-4 h-4" />
              <span>{t.saveBvhBlender}</span>
            </button>
            <button
              disabled={!hasFrames || busy}
              onClick={handleExportFbx}
              className="py-2.5 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-bold flex items-center justify-center gap-2"
            >
              <Box className="w-4 h-4" />
              <span>{t.convertFbxBlender}</span>
            </button>
          </div>

          {(advancedMode || showAdvancedExport) && (
            <div className="rounded-lg bg-slate-900 border border-slate-800 p-3 space-y-2.5">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">{t.scaleFactor}</label>
                  <select
                    value={scale}
                    onChange={(e) => setScale(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100"
                  >
                    <option value={1}>1.0 (Metros - Blender)</option>
                    <option value={100}>100.0 (Centímetros)</option>
                  </select>
                </div>
                <div className="flex flex-col justify-end gap-1 text-slate-300">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={includeTpose}
                      onChange={(e) => setIncludeTpose(e.target.checked)}
                      className="accent-cyan-500"
                    />
                    <span>{t.includeTposeFrame0}</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={respectTrim}
                      onChange={(e) => setRespectTrim(e.target.checked)}
                      className="accent-cyan-500"
                    />
                    <span>{t.respectTrim}</span>
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-800">
                <span className={blenderStatus.blender_found ? 'text-emerald-400' : 'text-amber-300'}>
                  {blenderStatus.blender_found
                    ? `${t.blenderDetected} ${blenderStatus.blender_path}`
                    : t.blenderNotFound}
                </span>
              </div>
              <div className="flex gap-2">
                <input
                  value={customBlenderInput}
                  onChange={(e) => setCustomBlenderInput(e.target.value)}
                  placeholder="C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
                  className="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px] font-mono text-slate-200"
                />
                <button
                  onClick={handleBrowseBlender}
                  className="px-3 py-1 rounded text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200"
                >
                  {t.selectBlenderExe}
                </button>
              </div>
            </div>
          )}

          {!advancedMode && (
            <button
              onClick={() => setShowAdvancedExport(!showAdvancedExport)}
              className="text-[11px] text-slate-400 hover:text-slate-200 inline-flex items-center gap-1"
            >
              <ChevronDown className="w-3 h-3" />
              <span>{showAdvancedExport ? 'Ocultar opciones de Blender y escala' : 'Configurar ruta de Blender y opciones'}</span>
            </button>
          )}

          {/* Archivos recientes */}
          {filesData && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300">{t.savedFilesTitle}</span>
                {filesData?.dirs?.exports && window.openMocapDesktop?.openPath && (
                  <button
                    onClick={() => window.openMocapDesktop?.openPath(filesData.dirs.exports)}
                    className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 text-xs"
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    <span>{t.openExportsFolder}</span>
                  </button>
                )}
              </div>
              <div className="max-h-36 overflow-y-auto border border-slate-800 rounded-lg divide-y divide-slate-800/80">
                {[
                  ...(filesData.bvh ?? []).map((f: any) => ({ ...f, folder: 'bvh' })),
                  ...(filesData.fbx ?? []).map((f: any) => ({ ...f, folder: 'fbx' })),
                  ...(filesData.videos ?? []).map((f: any) => ({ ...f, folder: 'videos' })),
                ].map((item: any) => (
                  <div
                    key={`${item.folder}-${item.name}`}
                    className="px-3 py-1.5 flex items-center justify-between text-xs hover:bg-slate-900/50"
                  >
                    <div className="flex items-center gap-2 font-mono">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] uppercase text-cyan-300">
                        {item.folder}
                      </span>
                      <span className="text-slate-200">{item.name}</span>
                      <span className="text-slate-500 text-[10px]">{item.size_kb} KB</span>
                    </div>
                    <a
                      href={`${API_BASE}/export/download/${item.folder}/${encodeURIComponent(item.name)}`}
                      download={item.name}
                      className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 text-[11px]"
                    >
                      <Download className="w-3.5 h-3.5" />
                      {t.downloadBtn}
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/60 flex justify-end">
          <button
            onClick={() => setOpen(false)}
            className="px-4 py-1.5 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-200"
          >
            {t.close}
          </button>
        </div>
      </div>
    </div>
  );
};
