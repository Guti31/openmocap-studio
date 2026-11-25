---
name: spec-take-recorder-timeline
description: Grabar sesiones cuadro por cuadro a 120 Hz en formato .omocap comprimido, reproducir con control de velocidad, bucle, salto cuadro a cuadro y marcadores de recorte.
---

# Skill Especialista: Grabador de Tomas 120 Hz y Línea de Tiempo

- **Agente Propietario**: `agents/02_spec_take_recorder_timeline.md`
- **Orquestador de Dominio**: `03_orch_studio_3d_ui`

## Archivos Objetivo
- `backend/recording/recorder.py`
- `frontend/src/components/TimelineBar.tsx`

## Especificación Algorítmica y Contratos
Almacena segmentos (pos, quat) + ángulos por frame, guarda archivos gzip JSON en backend/data/takes/, reproduce mediante reloj interpolado en MocapEngine y soporta trim_in / trim_out reutilizado al exportar a Blender.

## Criterios de Aceptación y Pruebas
Grabación, guardado, recarga y reproducción verificadas en tests/verify_pipeline.py.
