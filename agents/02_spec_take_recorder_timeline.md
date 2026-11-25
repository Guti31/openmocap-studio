# Nivel 2 — Agente Especialista #18: Grabador de Tomas 120 Hz y Línea de Tiempo (`spec_take_recorder_timeline`)

- **Orquestador Padre**: `03_orch_studio_3d_ui`
- **Skill Especialista Asociada**: `.agent/skills/spec-take-recorder-timeline/SKILL.md`

## Responsabilidad Principal
Grabar sesiones cuadro por cuadro a 120 Hz en formato .omocap comprimido, reproducir con control de velocidad, bucle, salto cuadro a cuadro y marcadores de recorte.

## Archivos Bajo Propiedad
- `backend/recording/recorder.py`
- `frontend/src/components/TimelineBar.tsx`

## Diseño Técnico y Contrato Operativo
Almacena segmentos (pos, quat) + ángulos por frame, guarda archivos gzip JSON en backend/data/takes/, reproduce mediante reloj interpolado en MocapEngine y soporta trim_in / trim_out reutilizado al exportar a Blender.

## Criterios de Verificación
Grabación, guardado, recarga y reproducción verificadas en tests/verify_pipeline.py.
