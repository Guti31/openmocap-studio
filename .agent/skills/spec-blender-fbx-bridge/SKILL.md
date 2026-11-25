---
name: spec-blender-fbx-bridge
description: Detectar Blender instalado en el sistema y ejecutar de forma desatendida la conversión de .bvh hacia .fbx limpio listo para motores 3D, Rigify y Mixamo.
---

# Skill Especialista: Puente Automatizado Blender .BVH a .FBX

- **Agente Propietario**: `agents/02_spec_blender_fbx_bridge.md`
- **Orquestador de Dominio**: `04_orch_export_packaging`

## Archivos Objetivo
- `backend/export/blender_bridge.py`
- `blender_tools/convertir_a_fbx.py`
- `frontend/src/components/ExportModal.tsx`

## Especificación Algorítmica y Contratos
Localiza blender.exe en registro estándar de Windows/PATH o ruta seleccionada por el usuario; ejecuta blender --background --python convertir_a_fbx.py; importa BVH (axis_forward='Z', axis_up='Y'), remapea huesos si se solicita y exporta FBX sin leaf bones sobrantes.

## Criterios de Aceptación y Pruebas
Compilación sintáctica verificada con py_compile y manejo diagnóstico claro cuando Blender no está instalado.
