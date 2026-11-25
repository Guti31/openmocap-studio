---
name: global-qa-verification
description: Protocolo de verificación integral automatizada para validar WebSocket >= 60 Hz, error de calibración < 0.5 grados, validez BVH y compilación limpia.
---

# Skill Global: Verificación QA Integral

## Criterios Cuantitativos de Aceptación
1. **Streaming en vivo**: El endpoint `/ws/stream` con 17 sensores activos debe entregar cuadros válidos a `>= 60.0 Hz` verificados por reloj monotónico.
2. **Mapeo Awinda base**: Los 17 IDs exactos (`00B4D904`..`00B4D8FD`) deben mapearse automáticamente al instante al entrar al HAL.
3. **Precisión de Calibración T-Pose + Caminata**: Bajo rotaciones arbitrarias de montaje (`25°–135°`) y deriva magnética interior (`-40° a +40°`) distintas en cada sensor, el error medio y máximo frente al ground truth tras calibrar debe ser `< 0.5°`.
4. **Exportación BVH**: Jerarquía completa con llaves balanceadas, canales exactos por línea (`54` canales para 17 segmentos), sin `NaN/Inf`, y soporte validado para perfiles `openmocap`, `mixamo` y `rigify`.
5. **Compilación**: `npx.cmd tsc --noEmit`, `npm.cmd run build`, `node --check` sobre Electron y `py_compile` sobre scripts Python sin errores ni advertencias críticas.
