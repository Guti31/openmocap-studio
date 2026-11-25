import { useEffect } from 'react';
import { api, WS_URL } from '../services/api';
import { liveFrameRef, useStudioStore } from '../store/useStudioStore';
import type { MocapFrame } from '../types/mocap';

export function useMocapStream(): void {
  const setConnected = useStudioStore((s) => s.setConnected);
  const ingestUiFrame = useStudioStore((s) => s.ingestUiFrame);
  const setProfiles = useStudioStore((s) => s.setProfiles);
  const setTakes = useStudioStore((s) => s.setTakes);
  const setSegmentToSensor = useStudioStore((s) => s.setSegmentToSensor);
  const setToast = useStudioStore((s) => s.setToast);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let alive = true;
    let reconnectTimer: number | null = null;
    let lastUiUpdate = 0;
    let rxCount = 0;
    let rxWindowStart = performance.now();
    let measuredHz = 0;

    const bootstrapData = async () => {
      try {
        const [profRes, mapRes, takesRes] = await Promise.all([
          api.listProfiles(),
          api.getMapping(),
          api.listTakes(),
        ]);
        if (!alive) return;
        setProfiles(profRes.profiles);
        setSegmentToSensor(mapRes.mapping?.segment_to_sensor ?? {});
        setTakes(takesRes.takes);
      } catch {
        // El reconector volverá a sincronizar cuando el backend esté listo
      }
    };

    const connect = () => {
      if (!alive) return;
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        if (!alive) return;
        setConnected(true);
        rxCount = 0;
        rxWindowStart = performance.now();
        bootstrapData();
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as MocapFrame;
          if (!parsed || !parsed.segments) return;

          // Actualizar referencia inmediata para Three.js (60 FPS)
          liveFrameRef.current = parsed;

          // Medición real de frecuencia WebSocket
          rxCount += 1;
          const now = performance.now();
          if (now - rxWindowStart >= 1000) {
            measuredHz = Number(((rxCount * 1000) / (now - rxWindowStart)).toFixed(1));
            rxCount = 0;
            rxWindowStart = now;
          }

          if (parsed.shake_detected) {
            setToast(
              `Sensor agitado: ${parsed.shake_detected.sensor_id} (${parsed.shake_detected.segment})`
            );
          }

          // Throttle UI (~15 Hz) para gráficas, barra de tiempo y telemetría
          if (now - lastUiUpdate >= 66) {
            lastUiUpdate = now;
            ingestUiFrame(parsed, measuredHz || parsed.rate_hz);
          }
        } catch {
          // Ignorar mensajes keep-alive o no estructurados
        }
      };

      ws.onclose = () => {
        if (!alive) return;
        setConnected(false);
        reconnectTimer = window.setTimeout(connect, 1000);
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      alive = false;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [ingestUiFrame, setConnected, setProfiles, setSegmentToSensor, setTakes, setToast]);
}

