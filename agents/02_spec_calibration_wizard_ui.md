# Nivel 2 — Agente Especialista #16: Asistente Guiado de Calibración en Español (`spec_calibration_wizard_ui`)

- **Orquestador Padre**: `03_orch_studio_3d_ui`
- **Skill Especialista Asociada**: `.agent/skills/spec-calibration-wizard-ui/SKILL.md`

## Responsabilidad Principal
Ofrecer un asistente visual sumamente claro y sin jerga técnica en español: postura inicial con brazos abiertos en T durante 4 segundos con cuenta regresiva gigante (`4... 3... 2... 1`), caminata recta de 6 segundos (`6... 5... 4...`) y confirmación visual inmediata *"¡Traje Calibrado! Ya puedes grabar"*.

## Archivos Bajo Propiedad
- `frontend/src/components/CalibrationWizardModal.tsx`

## Diseño Técnico y Contrato Operativo
- Siluetas SVG ilustrativas para postura estática y caminata.
- Anillo circular y números grandes de cuenta regresiva sincronizados con `/api/calibration/start-static` y `/api/calibration/start-walk`.
- Mantiene acceso opcional a postura N-Pose y tabla de diagnóstico por sensor dentro de un detalle colapsable o en Modo Avanzado.

## Criterios de Verificación
- Flujo completo ejecutable en 2 clics desde estado sin calibrar hasta calibración activa, compilando limpio en TypeScript.
