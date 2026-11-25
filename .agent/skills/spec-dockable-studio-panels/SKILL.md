---
name: spec-dockable-studio-panels
description: Diseñar la interfaz oscura de 4 pasos ultra-simple por defecto (sin ruido técnico) con interruptor Modo Avanzado que despliega paneles acoplables, telemetría multi-marca y gráficas biomecánicas.
---

# Skill Especialista: Paneles de Estudio Ultra-Simples y Modo Avanzado

- **Agente Propietario**: `agents/02_spec_dockable_studio_panels.md`
- **Orquestador de Dominio**: `03_orch_studio_3d_ui`

## Archivos Objetivo
- `frontend/src/components/TopBar.tsx`
- `frontend/src/components/LeftHardwarePanel.tsx`
- `frontend/src/components/RightBiomechanicsPanel.tsx`
- `frontend/src/components/Viewport3D.tsx`
- `frontend/src/components/TimelineBar.tsx`
- `frontend/src/App.tsx`

## Especificación Algorítmica y Contratos
- Estado `advancedMode: boolean` inicializado en `false` dentro de `useStudioStore.ts`.
- En Modo Simple:
  - `TopBar`: pasos `1. Antena y Traje`, `2. Calibrar Traje`, `3. Grabar Movimiento`, `4. Exportar` + switch `Modo Avanzado`.
  - `LeftHardwarePanel`: estado de antena Awinda con botón único `Encender / Reconectar Antena`, estatura rápida en cm, silueta visual de 17 sensores (verde/amarillo/gris) y enlace de demostración virtual.
  - `Viewport3D`: 3 botones limpios (`Centrar Cámara`, `Vista Frontal`, `Ver Esqueleto / Maniquí`).
  - `RightBiomechanicsPanel`: oculto.
  - `TimelineBar`: controles esenciales de reproducción, barra de progreso y grabaciones recientes.
- En Modo Avanzado: expone todas las capacidades de hardware HAL, mapa corporal por ID, sensores ilimitados, gráficas Recharts y línea de tiempo completa.

## Criterios de Aceptación y Pruebas
- Verificación `npx.cmd tsc --noEmit` y `npm.cmd run build` sin errores.
