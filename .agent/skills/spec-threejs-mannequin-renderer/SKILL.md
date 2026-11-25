---
name: spec-threejs-mannequin-renderer
description: Renderizar a 60 FPS un maniquí anatómico articulado, esqueleto de huesos, tríadas de ejes locales y vectores de aceleración sobre un piso cuadriculado con sombras.
---

# Skill Especialista: Renderizador 3D Three.js de Maniquí y Esqueleto

- **Agente Propietario**: `agents/02_spec_threejs_mannequin_renderer.md`
- **Orquestador de Dominio**: `03_orch_studio_3d_ui`

## Archivos Objetivo
- `frontend/src/components/Viewport3D.tsx`
- `frontend/src/components/MannequinScene.tsx`

## Especificación Algorítmica y Contratos
Lee liveFrameRef directamente dentro de useFrame() sin causar re-renders React por fotograma. Convierte Hamilton [w,x,y,z] a THREE.Quaternion(x,y,z,w), orienta geometrías desde la articulación padre hacia el extremo distal, y ofrece cámaras Perspectiva, Frontal, Lateral, Superior y seguimiento de Pelvis.

## Criterios de Aceptación y Pruebas
Compilación estricta TypeScript sin errores y renderizado limpio con preserveDrawingBuffer para captura MP4.
