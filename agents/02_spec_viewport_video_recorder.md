# Nivel 2 — Agente Especialista #21: Grabador de Video en Tiempo Real .MP4 (60 FPS) (`spec_viewport_video_recorder`)

- **Orquestador Padre**: `04_orch_export_packaging`
- **Skill Especialista Asociada**: `.agent/skills/spec-viewport-video-recorder/SKILL.md`

## Responsabilidad Principal
Capturar video fluido a 60 FPS directamente desde el visor 3D con opción de superponer telemetría en pantalla y transcodificarlo a .mp4 H.264.

## Archivos Bajo Propiedad
- `frontend/src/hooks/useVideoRecorder.ts`
- `backend/export/video_converter.py`

## Diseño Técnico y Contrato Operativo
Usa canvas.captureStream(60) sobre un lienzo compuesto opcional (escena 3D + HUD de telemetría), graba con MediaRecorder VP9/VP8, sube el blob a /api/video/convert-mp4 y lo convierte con ffmpeg (incluido vía imageio-ffmpeg) usando libx264 + faststart.

## Criterios de Verificación
Disponibilidad de ejecutable ffmpeg en backend/.venv y endpoint funcional de conversión MP4.
