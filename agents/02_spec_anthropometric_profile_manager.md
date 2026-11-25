# Nivel 2 — Agente Especialista #17: Gestor de Perfiles Antropométricos (`spec_anthropometric_profile_manager`)

- **Orquestador Padre**: `03_orch_studio_3d_ui`
- **Skill Especialista Asociada**: `.agent/skills/spec-anthropometric-profile-manager/SKILL.md`

## Responsabilidad Principal
Permitir crear, editar, activar y eliminar perfiles de sujetos con estatura obligatoria y medidas opcionales persistidos en JSON.

## Archivos Bajo Propiedad
- `frontend/src/components/ProfileManagerModal.tsx`
- `backend/kinematics/anthropometry.py`

## Diseño Técnico y Contrato Operativo
Sincroniza formularios React con /api/profiles, calcula y previsualiza inmediatamente longitudes de muslo, pantorrilla, brazo y envergadura estimadas según Winter y actualiza el esqueleto 3D en caliente.

## Criterios de Verificación
Persistencia JSON verificada tras reinicio del servidor.
