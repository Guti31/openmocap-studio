---
name: spec-calibration-wizard-ui
description: Guiar al usuario paso a paso en español con lenguaje cotidiano, siluetas animadas y cuentas regresivas grandes (4 s en T y 6 s de caminata) hasta confirmar calibración lista para grabar.
---

# Skill Especialista: Asistente Guiado de Calibración Ultra-Intuitivo

- **Agente Propietario**: `agents/02_spec_calibration_wizard_ui.md`
- **Orquestador de Dominio**: `03_orch_studio_3d_ui`

## Archivos Objetivo
- `frontend/src/components/CalibrationWizardModal.tsx`

## Especificación Algorítmica y Contratos
1. Paso 1 (4 segundos): instrucción clara *"Ponte el traje, párate derecho con los brazos abiertos en T durante 4 segundos"*, silueta SVG ilustrativa y anillo de cuenta regresiva grande (`4... 3... 2... 1`).
2. Paso 2 (6 segundos): instrucción *"Camina 4 pasos hacia adelante, da la vuelta y regresa"* con silueta de caminata y anillo regresivo `6... 5... 4... 3... 2... 1`.
3. Paso 3: pantalla de confirmación *"¡Traje Calibrado! Ya puedes grabar"*, ocultando la tabla numérica técnica tras un desplegable opcional o Modo Avanzado.

## Criterios de Aceptación y Pruebas
- Flujo sin bloqueos conectado a `/api/calibration/start-static`, `/api/calibration/start-walk` y estado WebSocket.
