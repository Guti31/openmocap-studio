/**
 * Motor de audio y síntesis de voz offline para el Asistente de Calibración.
 * Usa únicamente APIs nativas del navegador / Electron (Web Speech API + Web Audio API),
 * sin archivos MP3/WAV externos.
 */

import type { Locale } from '../types/mocap';

class CalibrationAudioEngine {
  private audioCtx: AudioContext | null = null;
  private muted = false;
  private volume = 0.85;
  private cachedVoices: SpeechSynthesisVoice[] = [];
  private listenersBound = false;

  constructor() {
    this.bindVoicesListener();
  }

  private bindVoicesListener(): void {
    if (this.listenersBound || typeof window === 'undefined' || !('speechSynthesis' in window)) {
      return;
    }
    this.listenersBound = true;
    const loadVoices = () => {
      try {
        this.cachedVoices = window.speechSynthesis.getVoices() || [];
      } catch {
        this.cachedVoices = [];
      }
    };
    loadVoices();
    try {
      window.speechSynthesis.addEventListener?.('voiceschanged', loadVoices);
    } catch {
      // Navegador sin addEventListener en speechSynthesis
    }
  }

  private getAudioContext(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    if (!this.audioCtx) {
      const Ctx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctx) return null;
      try {
        this.audioCtx = new Ctx();
      } catch {
        return null;
      }
    }
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume().catch(() => {});
    }
    return this.audioCtx;
  }

  ensureReady(): void {
    this.bindVoicesListener();
    this.getAudioContext();
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (muted) {
      this.stopAll();
    }
  }

  isMuted(): boolean {
    return this.muted;
  }

  setVolume(vol: number): void {
    this.volume = Math.max(0, Math.min(1, vol));
  }

  getVolume(): number {
    return this.volume;
  }

  private selectVoice(locale: Locale): SpeechSynthesisVoice | null {
    if (!this.cachedVoices.length && typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        this.cachedVoices = window.speechSynthesis.getVoices() || [];
      } catch {
        this.cachedVoices = [];
      }
    }
    if (!this.cachedVoices.length) return null;

    if (locale === 'es') {
      return (
        this.cachedVoices.find((v) => v.lang.toLowerCase() === 'es-mx') ??
        this.cachedVoices.find((v) => v.lang.toLowerCase() === 'es-es') ??
        this.cachedVoices.find((v) => v.lang.toLowerCase().startsWith('es')) ??
        null
      );
    }
    return (
      this.cachedVoices.find((v) => v.lang.toLowerCase() === 'en-us') ??
      this.cachedVoices.find((v) => v.lang.toLowerCase().startsWith('en')) ??
      null
    );
  }

  speak(
    text: string,
    opts?: { interrupt?: boolean; rate?: number; pitch?: number; locale?: Locale },
  ): void {
    if (this.muted || !text.trim()) return;
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;

    const locale = opts?.locale ?? 'es';
    const interrupt = opts?.interrupt ?? true;

    try {
      if (interrupt) {
        window.speechSynthesis.cancel();
      }
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = locale === 'es' ? 'es-MX' : 'en-US';
      utter.volume = this.volume;
      utter.rate = opts?.rate ?? 1.02;
      utter.pitch = opts?.pitch ?? 1.0;

      const voice = this.selectVoice(locale);
      if (voice) {
        utter.voice = voice;
      }
      window.speechSynthesis.speak(utter);
    } catch {
      // Ignorar errores de síntesis si el entorno no tiene TTS activo
    }
  }

  private playTone(freqHz: number, durationMs: number, delaySec = 0, peakGain = 0.16): void {
    if (this.muted || this.volume <= 0.01) return;
    const ctx = this.getAudioContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime + delaySec;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freqHz, now);

      const maxVol = Math.max(0.001, peakGain * this.volume);
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(maxVol, now + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + durationMs / 1000);

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + durationMs / 1000 + 0.02);
    } catch {
      // Ignorar fallos de AudioContext
    }
  }

  playCountdownBeep(sec: number): void {
    const freq = sec <= 1 ? 880 : 660;
    this.playTone(freq, sec <= 1 ? 135 : 105, 0, 0.15);
  }

  speakCountdown(secondsLeft: number, locale: Locale = 'es'): void {
    if (this.muted) return;
    const sec = Math.max(1, Math.round(secondsLeft));
    this.playCountdownBeep(sec);

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      if (!window.speechSynthesis.speaking) {
        this.speak(String(sec), { interrupt: false, rate: 1.12, locale });
      }
    }
  }

  playPhaseConfirm(): void {
    this.playTone(587.33, 110, 0, 0.16);
    this.playTone(880.0, 160, 0.12, 0.18);
  }

  playActionCue(): void {
    this.playTone(659.25, 95, 0, 0.17);
    this.playTone(987.77, 175, 0.1, 0.2);
  }

  playCompleteChime(): void {
    this.playTone(523.25, 110, 0, 0.15);
    this.playTone(659.25, 110, 0.11, 0.16);
    this.playTone(783.99, 240, 0.22, 0.19);
  }

  playErrorTone(): void {
    this.playTone(330.0, 140, 0, 0.16);
    this.playTone(246.94, 220, 0.15, 0.16);
  }

  stopAll(): void {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {
        // Ignorar
      }
    }
  }
}

export const calibrationAudio = new CalibrationAudioEngine();
