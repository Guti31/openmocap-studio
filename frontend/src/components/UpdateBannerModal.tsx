import React, { useEffect, useState } from 'react';
import { ArrowDownToLine, CheckCircle2, RefreshCw, Sparkles, X } from 'lucide-react';
import { translations } from '../i18n';
import { useStudioStore } from '../store/useStudioStore';
import type { UpdateInfoPayload, UpdateProgressPayload, UpdateStatusPayload } from '../types/mocap';

function formatMb(bytes: number): string {
  return `${(Math.max(0, bytes) / (1024 * 1024)).toFixed(1)} MB`;
}

export const UpdateBannerModal: React.FC = () => {
  const locale = useStudioStore((s) => s.locale);
  const setToast = useStudioStore((s) => s.setToast);
  const t = translations[locale];

  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState<UpdateInfoPayload | null>(null);
  const [phase, setPhase] = useState<'available' | 'downloading' | 'downloaded' | 'error'>('available');
  const [progress, setProgress] = useState<UpdateProgressPayload | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    const desktop = window.openMocapDesktop;
    if (!desktop) return;

    const unsubs: Array<() => void> = [];

    if (desktop.onUpdateAvailable) {
      unsubs.push(
        desktop.onUpdateAvailable((payload) => {
          setInfo(payload);
          setPhase('available');
          setProgress(null);
          setErrMsg(null);
          setOpen(true);
        }),
      );
    }

    if (desktop.onUpdateProgress) {
      unsubs.push(
        desktop.onUpdateProgress((prog) => {
          setPhase('downloading');
          setProgress(prog);
        }),
      );
    }

    if (desktop.onUpdateDownloaded) {
      unsubs.push(
        desktop.onUpdateDownloaded((payload) => {
          setInfo(payload);
          setPhase('downloaded');
          setOpen(true);
        }),
      );
    }

    if (desktop.onUpdateStatus) {
      unsubs.push(
        desktop.onUpdateStatus((st: UpdateStatusPayload) => {
          if (st.state === 'up-to-date' && st.message) {
            setToast(st.message);
          } else if (st.state === 'error' && st.message) {
            if (open) {
              setPhase('error');
              setErrMsg(st.message);
            } else {
              setToast(st.message);
            }
          }
        }),
      );
    }

    return () => {
      for (const fn of unsubs) fn();
    };
  }, [open, setToast]);

  if (!open || !info) return null;

  const handleDownload = async () => {
    setErrMsg(null);
    setPhase('downloading');
    const res = await window.openMocapDesktop?.downloadUpdate?.();
    if (res && !res.ok) {
      setPhase('error');
      setErrMsg(res.message || 'Error al descargar la actualización.');
    }
  };

  const handleInstallNow = async () => {
    await window.openMocapDesktop?.installUpdateNow?.();
  };

  const pct = Math.max(0, Math.min(100, progress?.percent ?? 0));

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-[#111827] border border-cyan-500/40 rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
          <div className="flex items-center gap-2 text-cyan-300 font-bold text-sm">
            <Sparkles className="w-4 h-4" />
            <span>{t.updateModalTitle}</span>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="text-slate-400 hover:text-white"
            aria-label={t.close}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between bg-slate-950/70 border border-slate-800 rounded-xl px-4 py-3">
            <div>
              <div className="text-xs text-slate-400">
                {locale === 'es' ? 'Nueva versión disponible' : 'New version available'}
              </div>
              <div className="text-lg font-extrabold text-white font-mono">
                Nueva versión v{info.version} disponible
              </div>
            </div>
            <div className="text-right font-mono text-xs text-slate-400">
              <div>Actual: v{info.currentVersion}</div>
              {info.releaseDate && (
                <div>{new Date(info.releaseDate).toLocaleDateString('es-MX')}</div>
              )}
            </div>
          </div>

          {info.releaseNotes && (
            <div className="rounded-xl bg-slate-900/80 border border-slate-800 p-3 max-h-40 overflow-y-auto text-xs text-slate-200 whitespace-pre-wrap leading-relaxed">
              {info.releaseNotes}
            </div>
          )}

          {phase === 'downloading' && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs text-cyan-300 font-mono">
                <span>Descargando instalador...</span>
                <span>
                  {pct.toFixed(1)}%
                  {progress?.total ? ` (${formatMb(progress.transferred)} / ${formatMb(progress.total)})` : ''}
                </span>
              </div>
              <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 transition-all duration-150"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}

          {phase === 'downloaded' && (
            <div className="flex items-center gap-2 rounded-xl bg-emerald-950/50 border border-emerald-600/50 px-3.5 py-2.5 text-xs text-emerald-300">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>
                Descarga completada. Haz clic en &ldquo;{t.updateInstallNowBtn}&rdquo; para instalar la v{info.version}.
              </span>
            </div>
          )}

          {phase === 'error' && errMsg && (
            <div className="rounded-xl bg-rose-950/60 border border-rose-500/60 px-3.5 py-2.5 text-xs text-rose-200">
              {errMsg}
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/70 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="px-3.5 py-2 rounded-lg text-xs bg-slate-800 hover:bg-slate-700 text-slate-200"
          >
            {t.updateLaterBtn}
          </button>

          {phase === 'downloaded' ? (
            <button
              type="button"
              onClick={handleInstallNow}
              className="px-4 py-2 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 shadow-lg shadow-emerald-600/25"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>{t.updateInstallNowBtn}</span>
            </button>
          ) : (
            <button
              type="button"
              disabled={phase === 'downloading'}
              onClick={handleDownload}
              className="px-4 py-2 rounded-lg text-xs font-bold bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white flex items-center gap-1.5 shadow-lg shadow-cyan-600/25"
            >
              <ArrowDownToLine className="w-3.5 h-3.5" />
              <span>{phase === 'downloading' ? 'Descargando...' : t.updateDownloadBtn}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
