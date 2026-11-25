---
name: spec-end-to-end-qa-auditor
description: Auditar automáticamente el pipeline completo desde el simulador/HAL hasta el WebSocket, calibración matemática, biomecánica, exportación BVH y compilación de frontend.
---

# Skill Especialista: Auditor de Calidad y Pruebas End-to-End

- **Agente Propietario**: `agents/02_spec_end_to_end_qa_auditor.md`
- **Orquestador de Dominio**: `04_orch_export_packaging`

## Archivos Objetivo
- `tests/verify_pipeline.py`

## Especificación Algorítmica y Contratos
Levanta servidor FastAPI real en puerto local, mide frecuencia WebSocket real (>= 60 Hz), inyecta correas desalineadas + deriva magnética aleatoria (-40°..+40°), ejecuta T-Pose + Caminata y verifica error < 0.5°, valida Madgwick, shake-to-identify y BVH estructuralmente.

## Criterios de Aceptación y Pruebas
Ejecución exitosa con salida 0 de backend\.venv\Scripts\python.exe tests\verify_pipeline.py y auditoría cero TODOs.
