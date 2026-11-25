# Regla Global 00: Política de Cero Placeholders y Grado Producción

## Alcance Obligatorio
Esta regla aplica a todos los archivos fuente de **OpenMocap Studio (`APLICACION_TRAJE`)**, incluidos Python (`backend/`, `blender_tools/`, `tests/`), TypeScript/React/Electron (`frontend/`), scripts de empaquetado (`build/`) y documentación operativa.

## Directivas Inquebrantables
1. **Cero código incompleto**: Queda estrictamente prohibido dejar comentarios `TODO`, `FIXME`, `XXX`, funciones vacías (`pass`), `NotImplementedError` como marcador o respuestas simuladas que oculten fallos reales.
2. **Tipado estricto**:
   - En Python 3.11+: usar anotaciones completas (`from __future__ import annotations`), `pydantic.BaseModel` o `dataclasses` tipadas en interfaces públicas y validación explícita de límites físicos (división por cero, cuaterniones nulos, índices fuera de rango).
   - En TypeScript: `strict: true`, cero `any` injustificados, interfaces exactas para todos los mensajes REST y WebSocket.
3. **Manejo robusto de errores**:
   - Cada driver de hardware (Xsens XDA, Serial, UDP/OSC, BLE) debe degradar limpiamente con mensajes diagnósticos claros en español cuando falte SDK o dispositivo, sin bloquear el hilo de eventos asyncio ni tumbar el servidor.
   - Todas las operaciones de lectura/escritura de texto en Windows deben especificar explícitamente `encoding="utf-8"`.
4. **Idioma de la interfaz y documentación**:
   - Toda la UI visible por defecto, mensajes de error para el usuario final, asistentes y manuales deben redactarse en español profesional, manteniendo los identificadores técnicos de código, APIs y nombres de huesos estándar en inglés.
5. **Autoverificación continua**:
   - Ningún cambio se considera terminado hasta superar compilación limpia (`tsc --noEmit`, `vite build`, `py_compile`) y las pruebas integrales de la suite (`tests/verify_pipeline.py`).
