---
name: spec-anthropometric-profile-manager
description: Permitir crear, editar, activar y eliminar perfiles de sujetos con estatura obligatoria y medidas opcionales persistidos en JSON.
---

# Skill Especialista: Gestor de Perfiles Antropométricos

- **Agente Propietario**: `agents/02_spec_anthropometric_profile_manager.md`
- **Orquestador de Dominio**: `03_orch_studio_3d_ui`

## Archivos Objetivo
- `frontend/src/components/ProfileManagerModal.tsx`
- `backend/kinematics/anthropometry.py`

## Especificación Algorítmica y Contratos
Sincroniza formularios React con /api/profiles, calcula y previsualiza inmediatamente longitudes de muslo, pantorrilla, brazo y envergadura estimadas según Winter y actualiza el esqueleto 3D en caliente.

## Criterios de Aceptación y Pruebas
Persistencia JSON verificada tras reinicio del servidor.
