# Nivel 2 — Agente Especialista #20: Puente Automatizado Blender .BVH a .FBX (`spec_blender_fbx_bridge`)

- **Orquestador Padre**: `04_orch_export_packaging`
- **Skill Especialista Asociada**: `.agent/skills/spec-blender-fbx-bridge/SKILL.md`

## Responsabilidad Principal
Detectar Blender instalado en el sistema y ejecutar de forma desatendida la conversión de .bvh hacia .fbx limpio listo para motores 3D, Rigify y Mixamo.

## Archivos Bajo Propiedad
- `backend/export/blender_bridge.py`
- `blender_tools/convertir_a_fbx.py`
- `frontend/src/components/ExportModal.tsx`

## Diseño Técnico y Contrato Operativo
Localiza blender.exe en registro estándar de Windows/PATH o ruta seleccionada por el usuario; ejecuta blender --background --python convertir_a_fbx.py; importa BVH (axis_forward='Z', axis_up='Y'), remapea huesos si se solicita y exporta FBX sin leaf bones sobrantes.

## Criterios de Verificación
Compilación sintáctica verificada con py_compile y manejo diagnóstico claro cuando Blender no está instalado.
