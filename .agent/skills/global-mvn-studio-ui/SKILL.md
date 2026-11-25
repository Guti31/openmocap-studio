---
name: global-mvn-studio-ui
description: Estética de estudio oscuro profesional con UX ultra-simple en español de 4 pasos por defecto (Conectar, Calibrar, Grabar, Exportar) y Modo Avanzado opcional para ingeniería biomecánica.
---

# Skill Global: Arquitectura Visual de Estudio Oscuro 3D y UX Ultra-Simple

## Lineamientos de Diseño
- **Flujo Lineal de 4 Pasos en Español (Por Defecto)**:
  1. **Antena y Traje**: estado claro en español (*"Antena Encendida · 17/17 Sensores Listos"* / *"Conecta tu antena USB"*).
  2. **Calibrar Traje**: asistente guiado visual de 10 segundos.
  3. **Grabar Movimiento**: botón grande rojo con cronómetro en vivo.
  4. **Exportar**: guardado directo para Blender (`.bvh` / `.fbx`) y video `.mp4`.
- **Modo Simple vs Modo Avanzado**:
  - Por defecto (`advancedMode = false`), la interfaz oculta puertos COM, IPs, baudios, hexadecimales, ejes locales, vectores y gráficas articulares para dejar un visor 3D amplio y una silueta intuitiva verde/amarillo/gris.
  - Al activar **`Modo Avanzado`** en la esquina superior derecha, se muestran todos los paneles de hardware multi-marca, sensores personalizados, gráficas Recharts y controles de estudio.
- **Paleta Oscura de Alto Contraste**:
  - Fondo `#0b0f17`, paneles `#111827`, bordes `#1f2937`, acento `#06b6d4`, estados `#10b981` (listo), `#f59e0b` (atención), `#ef4444` (grabando/error).
