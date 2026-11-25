# Nivel 2 — Agente Especialista #14: Renderizador 3D Three.js de Maniquí y Esqueleto (`spec_threejs_mannequin_renderer`)

- **Orquestador Padre**: `03_orch_studio_3d_ui`
- **Skill Especialista Asociada**: `.agent/skills/spec-threejs-mannequin-renderer/SKILL.md`

## Responsabilidad Principal
Renderizar a 60 FPS un maniquí anatómico articulado, esqueleto de huesos, tríadas de ejes locales y vectores de aceleración sobre un piso cuadriculado con sombras.

## Archivos Bajo Propiedad
- `frontend/src/components/Viewport3D.tsx`
- `frontend/src/components/MannequinScene.tsx`

## Diseño Técnico y Contrato Operativo
Lee liveFrameRef directamente dentro de useFrame() sin causar re-renders React por fotograma. Convierte Hamilton [w,x,y,z] a THREE.Quaternion(x,y,z,w), orienta geometrías desde la articulación padre hacia el extremo distal, y ofrece cámaras Perspectiva, Frontal, Lateral, Superior y seguimiento de Pelvis.

## Criterios de Verificación
Compilación estricta TypeScript sin errores y renderizado limpio con preserveDrawingBuffer para captura MP4.
