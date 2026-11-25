# Nivel 2 — Agente Especialista #15: Arquitectura de Paneles Ultra-Simples y Modo Avanzado (`spec_dockable_studio_panels`)

- **Orquestador Padre**: `03_orch_studio_3d_ui`
- **Skill Especialista Asociada**: `.agent/skills/spec-dockable-studio-panels/SKILL.md`

## Responsabilidad Principal
Implementar la interfaz oscura de OpenMocap Studio con un flujo guiado ultra-simple de 4 pasos en español por defecto (`1. Antena y Traje` -> `2. Calibrar Traje` -> `3. Grabar Movimiento` -> `4. Exportar`) y conmutación instantánea hacia el `Modo Avanzado` completo sin perder ninguna capacidad técnica.

## Archivos Bajo Propiedad
- `frontend/src/components/TopBar.tsx`
- `frontend/src/components/LeftHardwarePanel.tsx`
- `frontend/src/components/RightBiomechanicsPanel.tsx`
- `frontend/src/components/Viewport3D.tsx`
- `frontend/src/components/TimelineBar.tsx`
- `frontend/src/App.tsx`

## Diseño Técnico y Contrato Operativo
- `useStudioStore.ts` mantiene `advancedMode: false` por defecto, estado `awinda` en tiempo real desde WebSocket y `cameraResetTick` para recentrar el visor.
- En Modo Simple: oculta el panel derecho de gráficas, muestra la silueta corporal sin códigos hexadecimales ni baudios, ofrece ajuste directo de estatura (cm), botones únicos de antena/demo virtual, y reduce la barra del visor 3D a `Centrar Cámara`, `Vista Frontal` y `Ver Esqueleto / Maniquí`.
- En Modo Avanzado: habilita todas las pestañas HAL (Xsens RF, Serial COM, UDP/OSC, BLE, mapeo dinámico custom), gráficas Recharts en tiempo real y controles completos de cámara/ejes/aceleración.

## Criterios de Verificación
- Compilación estricta `npx.cmd tsc --noEmit` y `npm.cmd run build` sin errores en ambos modos.
