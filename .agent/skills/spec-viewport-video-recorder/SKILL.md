---
name: spec-viewport-video-recorder
description: Capturar video fluido a 60 FPS directamente desde el visor 3D con opción de superponer telemetría en pantalla y transcodificarlo a .mp4 H.264.
---

# Skill Especialista: Grabador de Video en Tiempo Real .MP4 (60 FPS)

- **Agente Propietario**: `agents/02_spec_viewport_video_recorder.md`
- **Orquestador de Dominio**: `04_orch_export_packaging`

## Archivos Objetivo
- `frontend/src/hooks/useVideoRecorder.ts`
- `backend/export/video_converter.py`

## Especificación Algorítmica y Contratos
Usa canvas.captureStream(60) sobre un lienzo compuesto opcional (escena 3D + HUD de telemetría), graba con MediaRecorder VP9/VP8, sube el blob a /api/video/convert-mp4 y lo convierte con ffmpeg (incluido vía imageio-ffmpeg) usando libx264 + faststart.

## Criterios de Aceptación y Pruebas
Disponibilidad de ejecutable ffmpeg en backend/.venv y endpoint funcional de conversión MP4.
