# Nivel 2 — Agente Especialista #24: Auditor de Calidad y Pruebas End-to-End (`spec_end_to_end_qa_auditor`)

- **Orquestador Padre**: `04_orch_export_packaging`
- **Skill Especialista Asociada**: `.agent/skills/spec-end-to-end-qa-auditor/SKILL.md`

## Responsabilidad Principal
Auditar automáticamente el pipeline completo desde el simulador/HAL hasta el WebSocket, calibración matemática, biomecánica, exportación BVH y compilación de frontend.

## Archivos Bajo Propiedad
- `tests/verify_pipeline.py`

## Diseño Técnico y Contrato Operativo
Levanta servidor FastAPI real en puerto local, mide frecuencia WebSocket real (>= 60 Hz), inyecta correas desalineadas + deriva magnética aleatoria (-40°..+40°), ejecuta T-Pose + Caminata y verifica error < 0.5°, valida Madgwick, shake-to-identify y BVH estructuralmente.

## Criterios de Verificación
Ejecución exitosa con salida 0 de backend\.venv\Scripts\python.exe tests\verify_pipeline.py y auditoría cero TODOs.
