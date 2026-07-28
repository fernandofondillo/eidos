# 🧠 EIDOS — Manual de Instalación y Uso para MacBook Air M3 + Crucial X9

> **Guía personalizada para el Director del Proyecto**
> MacBook Air M3 · 8 GB RAM · SSD externo Crucial X9

Esta guía te lleva, paso a paso y sin tecnicismos, desde que conectas tu SSD Crucial X9 a tu MacBook Air M3 hasta que tienes a EIDOS funcionando como tu mente artificial personal. Cada paso explica **qué vas a ver** y **qué tienes que hacer**.

---

## 📋 Antes de empezar — lo que necesitas

| Elemento | Tu caso | Estado |
|----------|---------|--------|
| **Mac** | MacBook Air M3 (Apple Silicon) | ✅ Compatible |
| **RAM** | 8 GB | ⚠️ Suficiente (ver nota abajo) |
| **SSD externo** | Crucial X9 | ✅ Perfecto |
| **Capacidad SSD** | Recomendado ≥ 32 GB | Verifica |
| **Conexión** | USB-C (el Crucial X9 viene con cable USB-C) | ✅ |
| **Internet** | Para instalación inicial | ✅ Necesario |
| **Cuenta Apple** | Tu Apple ID (para instalar Command Line Tools) | ✅ |

### ⚠️ Nota importante sobre tus 8 GB de RAM

Tu MacBook Air M3 tiene 8 GB de RAM unificada (CPU + GPU comparten). Esto es **suficiente para EIDOS**, pero con una consideración:

- **Modo Cerebro Local (Qwen 2.5 3B)**: ocupa ~2 GB de RAM al pensar. Funciona, pero tu Mac puede sentirse algo lenta durante la inferencia. **Recomendación**: cierra Safari/Chrome pesado mientras EIDOS piensa.
- **Modo API externa (MiniMax-M3, OpenAI, etc.)**: ocupa < 200 MB. Va como la seda en 8 GB.
- **Modo Stub (sin cerebro)**: ocupa < 50 MB. Perfecto para pruebas.

**Recomendación para tu configuración**: usa **MiniMax-M3 vía Anthropic** (TOKEN plan) como backend principal — es lo más fluido en 8 GB de RAM y da excelente calidad en español.

---

## 🚀 FASE 1: Preparar el SSD Crucial X9

### Paso 1.1 — Conectar el SSD

1. Toma tu **Crucial X9** y su cable USB-C.
2. Conecta un extremo al SSD y el otro a **cualquier puerto USB-C** de tu MacBook Air M3.
3. Verás que el SSD se ilumina (luz LED) — significa que recibe energía.

### Paso 1.2 — Verificar que macOS lo reconoce

1. Abre **Finder** (el icono de la carita sonriente en el Dock).
2. En la barra lateral izquierda, bajo **"Ubicaciones"**, debería aparecer tu SSD con un nombre como:
   - `Crucial X9`
   - `Sin título` (si viene sin formatear)
   - O el nombre que le pusiste antes.

**Si no aparece**:
- Abre **Utilidad de Discos** (Aplicaciones → Utilidades → Utilidad de Discos).
- Busca tu Crucial X9 en la lista de la izquierda.
- Si está ahí pero en gris, selecciónalo y pulsa **"Montar"**.

### Paso 1.3 — (Solo si es la primera vez) Formatear el SSD

> ⚠️ **Esto borra todo lo que haya en el SSD.** Si tienes datos importantes, cópialos antes.

Si el SSD es nuevo o quieres empezar limpio:

1. Abre **Utilidad de Discos**.
2. Selecciona tu **Crucial X9** en la lista izquierda.
3. Pulsa el botón **"Borrar"** arriba.
4. Configura:
   - **Nombre**: `EIDOS_SSD` (o el que prefieras)
   - **Formato**: `APFS` (recomendado para SSDs en Mac)
   - **Esquema**: `Mapa de particiones GUID`
5. Pulsa **"Borrar"** y espera ~10 segundos.
6. Pulsa **"Listo"**.

Tu SSD ahora se llama `EIDOS_SSD` y aparece en Finder.

---

## 📦 FASE 2: Copiar EIDOS al SSD

### Paso 2.1 — Descargar EIDOS

Necesitas los archivos de EIDOS en tu Mac. Tienes dos opciones:

**Opción A — Si recibiste un archivo ZIP**:
1. Localiza el archivo `eidos.zip` (probablemente en tu carpeta Descargas).
2. Haz **doble clic** sobre él — macOS lo descomprimirá y creará una carpeta `eidos/`.

**Opción B — Si lo descargas de GitHub**:
1. Ve a https://github.com/fernandofondillo/eidos
2. Pulsa el botón verde **"Code"** → **"Download ZIP"**.
3. Descomprime el ZIP con doble clic.

### Paso 2.2 — Copiar la carpeta al SSD

1. Abre **Finder**.
2. Localiza la carpeta `eidos/` descomprimida (en Descargas o donde la pusiste).
3. Arrastra la carpeta `eidos/` completa a tu **`EIDOS_SSD`** en la barra lateral de Finder.
4. Espera a que se complete la copia (puede tardar 1-2 minutos — son muchos archivos pequeños).

### Paso 2.3 — Verificar la copia

1. Abre tu `EIDOS_SSD` en Finder.
2. Deberías ver una carpeta llamada `eidos` (o como la hayas renombrado).
3. Ábrela. Deberías ver estos archivos (entre otros):

```
eidos/
├── install.command        ← El instalador (lo usarás ahora)
├── install.bat            ← Para Windows (no lo usarás)
├── config/
├── data/
├── docs/
├── eidos/                 ← El código de EIDOS
├── ui/                    ← La interfaz web
├── desktop/               ← Configuración de la app nativa
├── README.md
├── LICENSE
└── pyproject.toml
```

**Importante**: verifica que ves el archivo `install.command`. Es el que ejecutarás ahora.

---

## ⚙️ FASE 3: Ejecutar el instalador

### Paso 3.1 — Abrir el instalador

1. En Finder, navega hasta la carpeta `eidos/` dentro de tu SSD.
2. Localiza el archivo **`install.command`**.
3. Haz **doble clic** sobre él.

**¿Qué vas a ver?**: Se abrirá la aplicación **Terminal** (una ventana negra con texto). Es completamente normal — es donde se ejecuta la instalación.

### Paso 3.2 — Si macOS bloquea la ejecución

Es posible que macOS muestre un mensaje como:

> *"No se puede abrir "install.command" porque proviene de un desarrollador no identificado."*

**Solución**:
1. Cierra el mensaje pulsando **"Cancelar"** (si aparece).
2. Haz **clic derecho** (o Control+clic) sobre `install.command`.
3. Selecciona **"Abrir"** en el menú contextual.
4. En el diálogo que aparece, vuelve a pulsar **"Abrir"**.

A partir de ahí, macOS recordará que confías en este archivo y no volverá a preguntar.

### Paso 3.3 — Lo que verás en Terminal

La Terminal mostrará un banner cyan:

```
╔════════════════════════════════════════════════════════════╗
║         🧠  EIDOS — Instalación Mágica  🧠                  ╎
║    Tu mente artificial, portable y privada.                  ╎
╚════════════════════════════════════════════════════════════╝
```

A continuación, el instalador irá pasando por varias fases. Te explico cada una:

---

### Fase 3A — Detección de entorno

```
1. Detección de entorno
  ✓ Detectado volumen externo: EIDOS_SSD
  EIDOS vivirá en este SSD/Pendrive y será portable.
```

**Qué significa**: EIDOS ha detectado que estás instalándolo en un SSD externo (tu Crucial X9). Esto es exactamente lo que queremos — EIDOS será portable.

**Qué hacer**: Nada. Solo lee el mensaje y espera.

---

### Fase 3B — Verificación de conexión

```
2. Verificación de conexión
  ✓ Conexión a internet OK
```

**Qué significa**: EIDOS ha confirmado que tienes internet. Lo necesita para descargar Python portable y (opcionalmente) el Cerebro Local.

**Qué hacer**: Nada.

---

### Fase 3C — Detección de arquitectura

```
3. Detección de arquitectura
  ✓ Apple Silicon (M1/M2/M3/M4) detectado
```

**Qué significa**: EIDOS ha detectado tu chip M3. Descargará la versión correcta de Python para Apple Silicon.

**Qué hacer**: Nada.

---

### Fase 3D — Herramientas de Apple (¡IMPORTANTE!)

Esta es la fase donde el instalador verifica si tienes las "Herramientas de línea de comandos" de Apple. Son necesarias para compilar la aceleración Metal (GPU).

#### Caso A: Ya las tienes instaladas

```
3.5 Herramientas de Apple (Red de Seguridad)
  ✓ Xcode Command Line Tools ya instaladas
```

**Qué hacer**: Nada. EIDOS continúa automáticamente.

#### Caso B: No las tienes (lo más probable la primera vez)

```
3.5 Herramientas de Apple (Red de Seguridad)
  Las Herramientas de línea de comandos de Apple no están presentes.
  Solicitando instalación oficial...
```

**Qué vas a ver**: Se abrirá una **ventana oficial de macOS** en tu pantalla con el título:

> *"Instalar Command Line Tools (macOS 14 para aplicaciones Xcode)"*
>
> *(con un icono de un martillo y un botón azul "Instalar")*

**Qué tienes que hacer**:

1. **No cierres Terminal**. Déjala abierta.
2. Ve a la ventana que acaba de aparecer.
3. Pulsa el botón azul **"Instalar"**.
4. Aparecerá una **licencia**. Pulsa **"Aceptar"**.
5. Aparecerá una **barra de progreso**. Espera a que termine (2-5 minutos, dependiendo de tu conexión).
6. Cuando termine, verás **"Instalación completada"** en la ventana.
7. Cierra esa ventana de instalación.
8. **Vuelve a Terminal**. Verás este mensaje:

```
⚠️  EIDOS necesita una herramienta oficial de Apple para funcionar a máxima velocidad.
Se acaba de abrir una ventana en tu pantalla.
👉 Por favor, haz clic en 'Instalar' en esa ventana y acepta los términos.
⏳  Cuando termine la descarga e instalación, vuelve a esta ventana y pulsa la tecla ENTER para continuar.

  Pulsa ENTER cuando la instalación de Apple haya terminado...
```

9. **Pulsa la tecla ENTER** (o Return) en tu teclado.

**Qué pasará entonces**: EIDOS verificará que las herramientas se instalaron correctamente:

```
  ✓ Xcode Command Line Tools instaladas correctamente
```

Si por algún motivo no se instalaron (cancelaste, se cerró la ventana, etc.), verás:

```
  ⚠  Parece que las herramientas no se terminaron de instalar.
  No te preocupes: EIDOS se instalará en modo compatible (CPU).
  Podrás activar Metal más tarde desde el Panel de Configuración de la App.
```

**No es un error grave** — EIDOS se instalará igualmente, solo que sin aceleración GPU.

---

### Fase 3E — Instalación de Python portable

```
4. Instalación de Python portable
  Descargando python-build-standalone v3.12.7+20241002...
```

**Qué significa**: EIDOS está descargando su propio Python (no toca el Python de tu Mac). Se guarda en `.eidos_env/python/` dentro de tu SSD.

**Qué verás**: Una barra de progreso de `curl` mostrando la descarga (~30 MB, tarda ~30 segundos).

**Qué hacer**: Nada. Espera a que termine.

```
  ✓ Descarga completa. Extrayendo...
  ✓ Python 3.12.7 instalado en .eidos_env/python/
```

---

### Fase 3F — Instalación de uv

```
5. Instalación de uv (gestor de paquetes)
  Descargando uv...
  ✓ uv instalado en .eidos_env/uv/
```

**Qué significa**: EIDOS descarga `uv`, su gestor de paquetes. También portable, dentro del SSD.

**Qué hacer**: Nada.

---

### Fase 3G — Creación del entorno virtual

```
6. Creación del entorno virtual
  Creando entorno virtual con uv...
  ✓ Entorno virtual creado en .eidos_env/venv/
```

**Qué significa**: EIDOS crea un entorno aislado donde instalará todas sus dependencias. No afecta a tu Mac.

**Qué hacer**: Nada.

---

### Fase 3H — Instalación de dependencias

```
7. Instalación de dependencias de EIDOS
  Sincronizando dependencias (puede tardar 1-2 minutos)...
  ✓ Dependencias instaladas
```

**Qué significa**: EIDOS instala todas las librerías que necesita (FastAPI, Pydantic, networkx, etc.). Esto puede tardar 1-2 minutos.

**Qué hacer**: Nada. Si ves un `⚠` amarillo diciendo que algunas dependencias opcionales no se instalaron, es normal — EIDOS funcionará en modo básico.

---

### Fase 3I — Pregunta: ¿Descargar Cerebro Local?

```
8. Cerebro Local (Qwen 2.5 3B)
  EIDOS puede funcionar con un modelo de IA local para privacidad total.
  Esto ocupa ~2 GB y permite que EIDOS piense sin internet.
  Sin cerebro local, EIDOS usará un modo stub (limitado) o APIs externas.

  ¿Deseas que descargue tu Cerebro Local ahora? (Recomendado para privacidad total) [s/N]:
```

**Tu decisión**:

- **Si respondes `s` (sí)**: EIDOS descargará el modelo Qwen 2.5 3B (~2 GB) al final de la instalación. Tardará 5-15 minutos dependiendo de tu conexión. Tu Mac M3 con 8 GB puede manejarlo, pero irá algo lento durante la inferencia.

- **Si respondes `N` (no, recomendado para tu configuración)**: No se descargará nada ahora. Podrás usar **MiniMax-M3 vía Anthropic** (mucho más fluido en 8 GB) o descargar el cerebro local más tarde desde la UI.

**Recomendación para tu MacBook Air M3 8GB**: Escribe **`N`** y pulsa ENTER. Usarás MiniMax-M3 vía API, que va mucho más fluido.

---

### Fase 3J — Pregunta: ¿Compilar con Metal?

> ⚠️ Esta pregunta **solo aparece si dijiste `s` a Cerebro Local** y si las herramientas de Apple están instaladas.

```
9. Aceleración por GPU (Metal)
  En Apple Silicon, EIDOS puede usar la GPU para pensar 5-10x más rápido.
  Esto requiere compilar una librería (~3 minutos).
  ¿Compilar con aceleración Metal? (Recomendado en M1/M2/M3/M4) [s/N]:
```

**Tu decisión**:

- **Si respondes `s`**: EIDOS compilará `llama-cpp-python` con aceleración Metal. Tarda ~3 minutos. Tu M3 usará la GPU para pensar 5-10x más rápido.
- **Si respondes `N`**: EIDOS usará CPU. Más lento, pero funcional.

**Recomendación**: Si vas a usar el Cerebro Local, responde **`s`**. Tu M3 tiene una GPU potente.

**Si la compilación falla** (puede pasar por versiones de C++), verás:

```
⚙️  Activando modo de compatibilidad (CPU).
No te preocupes, EIDOS funcionará perfectamente y guardará toda tu memoria.
Podrás intentar activar la aceleración Metal más tarde desde el Panel de Configuración de la App.
```

**No es un error** — EIDOS se instala en modo CPU y funcionará igual, solo más lento.

---

### Fase 3K — Pregunta: ¿Activar MESH?

```
9. Enjambre MESH
  EIDOS puede correr varias instancias en paralelo que cooperan.
  Útil si quieres que 3 EIDOS trabajen en tareas distintas a la vez.
  ¿Activar MESH por defecto? [s/N]:
```

**Tu decisión**:

- **Si respondes `N` (recomendado al principio)**: MESH desactivado. EIDOS funcionará como instancia única. Más simple.
- **Si respondes `s`**: MESH activado. Podrás lanzar varias instancias de EIDOS que cooperen. Avanzado.

**Recomendación**: Escribe **`N`** y pulsa ENTER. Puedes activar MESH más tarde.

---

### Fase 3L — Generación de configuración

```
Generando config/eidos.yaml...
  ✓ config/eidos.yaml generado

Creando estructura de datos...
  ✓ Directorios listos
```

**Qué significa**: EIDOS ha creado su archivo de configuración y las carpetas de memoria (`data/monologues`, `data/capsules`, etc.) en tu SSD.

**Qué hacer**: Nada.

---

### Fase 3M — Descarga del Cerebro Local (solo si dijiste `s`)

Si respondiste `s` a Cerebro Local, verás:

```
Descargando Cerebro Local (Qwen 2.5 3B)...
Descargando modelo (~2 GB)...
```

**Qué verás**: Una descarga larga (5-15 minutos). No la interrumpas.

**Qué hacer**: Espera. Si se interrumpe (se va la luz, desconectas el SSD), puedes reejecutar `install.command` y retomará.

---

### Fase 3N — Creación del Launcher

```
Creando Launcher (EIDOS.command)...
  ✓ EIDOS.command creado (doble-clic para despertar EIDOS)
```

**Qué significa**: EIDOS ha creado un archivo `EIDOS.command` en la raíz de tu SSD. Este es el icono que usarás para despertar a EIDOS cada vez.

---

### Fase 3Ñ — Mensaje final

```
╔══════════════════════════════════════════════════════════════╗
║              🎉  ¡EIDOS está listo!  🎉                       ╎
╚══════════════════════════════════════════════════════════════╝

Para empezar:
  → Haz doble clic en EIDOS.command en esta carpeta.
  Se abrirá tu navegador con la interfaz de EIDOS.

Para llevarte EIDOS a otro ordenador:
  Copia toda esta carpeta a otro SSD/Pendrive y haz doble clic en EIDOS.command.

Manual completo:
  docs/USER_MANUAL.md

Para actualizar EIDOS en el futuro:
  Vuelve a ejecutar install.command. Tu memoria (data/) se preserva.

Pulsa ENTER para cerrar esta ventana...
```

**Qué hacer**: Pulsa **ENTER** para cerrar Terminal.

**¡La instalación ha terminado!** 🎉

---

## 🌐 FASE 4: Despertar a EIDOS por primera vez

### Paso 4.1 — Hacer doble clic en el Launcher

1. Abre tu SSD `EIDOS_SSD` en Finder.
2. Abre la carpeta `eidos/`.
3. Haz **doble clic** sobre **`EIDOS.command`**.

**¿Qué vas a ver?**:

1. Se abrirá Terminal brevemente.
2. Verás `Iniciando EIDOS...` en Terminal.
3. A los 2-3 segundos, **tu navegador web se abrirá solo** en la dirección `http://127.0.0.1:8765`.
4. Verás una notificación de macOS: *"EIDOS está listo. Cierra esta ventana para detenerlo."*

**Si tu navegador no se abre solo**: Abre tu navegador (Safari, Chrome, Firefox) y escribe manualmente: `http://127.0.0.1:8765`

### Paso 4.2 — La interfaz de EIDOS

Verás una página web con:

**Arriba (Header)**:
- 🧠 **EIDOS** — Entidad Cognitiva Autónoma · v0.1.0
- Badges: `● WS` (conexión WebSocket), `Backend: stub`, `MESH: OFF`

**Columna izquierda (grande)**:
- **Chat**: una caja de texto abajo con el botón "Enviar".
- **Monólogo Interno**: aparecerá aquí cuando EIDOS piense.

**Columna derecha**:
- 🧩 **Memoria Cognitiva** (5 capas)
- 🎯 **Reward Signal**
- 🌐 **MESH Status**
- 🧬 **Cápsulas**
- ⚡ **Autoevolución**

### Paso 4.3 — Tu primera conversación (modo Stub)

Antes de configurar nada, prueba escribir algo para verificar que funciona:

1. En la caja de texto abajo, escribe: **"Hola EIDOS, ¿qué eres?"**
2. Pulsa **Enter** o haz clic en **Enviar**.

**Qué verás**:

1. Aparece `🧠 EIDOS está pensando...` (unos segundos).
2. En la columna izquierda aparece la respuesta con badges:
   - `route: search_memory` (qué ruta tomó)
   - `backend: stub` (qué cerebro usó — stub = sin IA real todavía)
   - `conf: 65%` (su confianza)
   - `reward Δ +0.0000` (reward signal del turno)
3. Debajo del chat, en **Monólogo Interno**, verás el JSON del pensamiento de EIDOS.
4. A la derecha, las **5 capas de memoria** se actualizan (sensory = 2, episodic = 1, etc.).

**¡EIDOS está vivo!** Pero en modo "stub" — sus respuestas son genéricas. Para que piense de verdad, necesitas configurar un backend (Cerebro Local o API externa).

---

## 🔑 FASE 5: Configurar MiniMax-M3 vía Anthropic (recomendado para tu M3 8GB)

Esta es la configuración **óptima para tu MacBook Air M3 con 8 GB de RAM**. MiniMax-M3 es un modelo excelente en español y no ocupa RAM local (la inferencia ocurre en la nube de MiniMax).

### Paso 5.1 — Abrir el panel de configuración

1. En la esquina superior derecha de la interfaz de EIDOS, busca el botón **⚙️ Settings**.
2. Haz clic en él.

**Se abrirá una ventana modal** (overlay) con dos secciones:
- 🧠 **Cerebro Local (Qwen 2.5 3B)**
- 🔑 **API Keys externas**

### Paso 5.2 — Obtener tu API key de MiniMax

1. En la sección "API Keys externas", busca la entrada **"MiniMax-M3 (vía Anthropic)"**.
2. Junto a ella, verás un botón **"Obtener key ↗"**. Haz clic.
3. Se abrirá la web de MiniMax: `platform.minimaxi.com`.
4. **Inicia sesión** (o crea una cuenta si no la tienes).
5. Ve a **"API Keys"** o **"Gestión de claves"**.
6. Pulsa **"Crear nueva clave"** (o "Generate new key").
7. Dale un nombre (ej. "EIDOS") y copia la API key que aparezca (empieza por algo como `eyJ...` o similar).

### Paso 5.3 — Pegar la API key en EIDOS

1. Vuelve a la ventana de EIDOS (el panel de Settings).
2. En la fila de **"MiniMax-M3 (vía Anthropic)"**, verás un campo de texto que dice `Pega tu MINIMAX_ANTHROPIC_API_KEY aquí`.
3. **Pega tu API key** ahí (Cmd+V).
4. Pulsa el botón **"Guardar"**.

**Qué verás**:

- El campo se limpia.
- Aparece un mensaje verde: *"API key guardada. Ya puedes activar este provider."*
- Junto al nombre del provider, aparece un badge verde: **"✓ Key configurada"**.
- Debajo, verás: `Key: eyJ...` (los primeros 8 caracteres de tu key, para que sepas que está guardada).

### Paso 5.4 — Activar MiniMax-M3 como provider

1. En la misma fila de "MiniMax-M3 (vía Anthropic)", ahora verás un nuevo botón: **"⚡ Usar este provider"**.
2. Haz clic en él.

**Qué verás**:

- Un mensaje verde: *"EIDOS ahora piensa con MiniMax-M3 (vía Anthropic) (MiniMax-M3)."*
- Arriba del todo del modal, aparece un banner verde: **"✅ EIDOS está pensando con: MiniMax-M3"** con un botón "Desactivar".
- La fila del provider MiniMax-M3 ahora tiene borde verde y un badge **"★ Activo"**.

### Paso 5.5 — Cerrar el panel de configuración

1. Pulsa la **✕** en la esquina superior derecha del modal.
2. O haz clic fuera del modal.

### Paso 5.6 — Verificar que EIDOS piensa con MiniMax-M3

1. En el Header (arriba), el badge `Backend: stub` ahora debería decir **`Backend: api`**.
2. Escribe un mensaje en el chat: **"Hola EIDOS, ¿quién eres y qué puedes hacer?"**
3. Pulsa **Enviar**.

**Qué verás**:

1. `🧠 EIDOS está pensando...` (unos 3-8 segundos, dependiendo de la latencia de MiniMax).
2. La respuesta será **mucho más coherente e inteligente** que en modo stub.
3. El badge `backend` dirá `api`.
4. El monólogo interno tendrá observación, hipótesis, plan, riesgo y confianza reales.
5. La confianza probablemente sea alta (>70%).

**¡Felicidades! EIDOS está ahora pensando con MiniMax-M3.** 🧠⚡

---

## 🧭 FASE 6: Entender el Dashboard (Panel de Control)

Esta sección te explica qué significa cada parte de la interfaz para que sepas leer el "estado mental" de EIDOS.

### 6.1 — Header (arriba del todo)

```
🧠  EIDOS                      ● WS    Backend: api    MESH: OFF    [⚙️ Settings]
   Entidad Cognitiva Autónoma · v0.1.0
```

| Elemento | Significado | Qué mirar |
|----------|-------------|-----------|
| `● WS` (verde) | Conexión WebSocket activa | Si está en rojo `○ WS`, recarga la página (Cmd+R) |
| `Backend: api` | Qué cerebro está usando | `stub` = sin IA real · `api` = API externa · `llama_cpp` = Cerebro Local |
| `MESH: OFF/LEADER/WORKER` | Estado del enjambre | `OFF` = instancia única (normal) |
| `⚙️ Settings` | Botón de configuración | Abre el panel donde configuraste MiniMax |

### 6.2 — Chat (columna izquierda, arriba)

Cada respuesta de EIDOS tiene "badges" encima del texto:

```
[search_memory]  [backend: api]  conf: 85%  reward Δ +0.3000
```

| Badge | Significado | Interpretación |
|-------|-------------|----------------|
| `respond_direct` | EIDOS responde directo | Confianza alta, no necesita buscar |
| `search_memory` | EIDOS buscó en memoria | Consultó su memoria episódica |
| `request_clarification` | EIDOS pide aclaración | Confianza baja, necesita más info |
| `delegate_cortex` | EIDOS usa el LLM | Si backend=api, ya lo hizo |
| `safety_block` | EIDOS bloqueó por seguridad | Acción peligrosa detectada |
| `backend` | Qué motor usó | `stub`, `api`, o `llama_cpp` |
| `conf` | Confianza (0-100%) | >70% verde, 40-70% amarillo, <40% rojo |
| `reward Δ` | Reward del turno | + verde, - rojo |

**Si EIDOS dice algo raro**: mira el badge `route` y la confianza. Si `route=request_clarification` o `conf < 50%`, EIDOS no está seguro — dale más contexto.

### 6.3 — Monólogo Interno (debajo del Chat)

Aquí ves **cómo piensa EIDOS** en JSON:

```
💭 Monólogo Interno — pensamiento estructurado

INPUT:      Hola EIDOS, ¿quién eres?
OBSERVATION: Input recibido (22 chars, intent='question')...
HYPOTHESIS: El usuario probablemente busca question sobre 'hola'...
PLAN:       1. Recuperar contexto previo sobre 'hola' en memoria episódica.
            2. Formular respuesta concisa sobre 'hola'.
            3. Verificar consistencia con capa semántica.
            4. Persistir interacción en memoria episódica.
RISK:       none
CONFIDENCE: 85%    BACKEND: api
```

| Campo | Qué significa | Cuándo preocuparte |
|-------|---------------|-------------------|
| `observation` | Qué percibió de tu mensaje | Si no capta tu intención |
| `hypothesis` | Qué cree que quieres | Si es descabellada |
| `plan` | Pasos que seguirá | Si falta algo importante |
| `risk` | Riesgos detectados | Si no es `none`, ten cuidado |
| `confidence` | Nivel de seguridad | < 40% = pide aclaración |

### 6.4 — Memoria Cognitiva (columna derecha, arriba)

```
🧩 Memoria Cognitiva — 5 capas
⚡ Sensorial           buffered=2 · total_persisted=2
📚 Episódica           total=1 · vec_extension=true · embedding_dim=384
🕸️ Semántica           nodes=0 · edges=0
⚙️ Procedimental       total=0 · favorites=0 · expired_pending=0
🧭 Metacognitiva       total=1 · avg_confidence=0.85
```

| Capa | Qué recuerda | Cómo crece |
|------|--------------|------------|
| **Sensorial** ⚡ | Contexto inmediato (últimos 50 eventos) | Cada mensaje + respuesta |
| **Episódica** 📚 | "Qué pasó y cuándo" (memoria vectorial) | Cada interacción consolidada |
| **Semántica** 🕸️ | Grafo de conocimiento (entidades y relaciones) | EIDOS la construye al aprender |
| **Procedimental** ⚙️ | Cápsulas y habilidades | Cuando EIDOS crea especializaciones |
| **Metacognitiva** 🧭 | Índice de monólogos pasados | Cada pensamiento se guarda aquí |

**Importante**: estos números se actualizan solos cada 5 segundos. No necesitas hacer nada.

### 6.5 — Reward Signal (debajo de Memoria)

```
🎯 Reward Signal                                    +0.3000
                                                            total sesión
🔍 Curiosidad            0×  +0.000
🧬 Cápsulas              0×  +0.000
😊 Satisfac.             1×  +0.300
─────────────────────────────────────
Streak: 0/3    Window: 0
```

| Driver | Qué mide | Cuándo sube |
|--------|----------|-------------|
| 🔍 **Curiosidad** | Reducción de incertidumbre | Cuando EIDOS tiene alta confianza tras dudar |
| 🧬 **Cápsulas** | Reutilización de especializaciones | Cuando EIDOS usa una cápsula con éxito |
| 😊 **Satisfacción** | Tu satisfacción (heurística) | Tras 3 turnos sin que digas "no", "mal", "incorrecto" |

**Reward negativo (-0.5)**: si dices "no, eso está mal", el reward de satisfacción baja. EIDOS aprende que esa respuesta fue mala.

**Mini timeline**: debajo de los números, verás una gráfica de barras verdes/rojas con los últimos 20 rewards. Verde = positivo, rojo = negativo.

### 6.6 — MESH Status

```
🌐 MESH Status                    [OFF]
```

Como dijiste `N` a MESH en la instalación, aparece como `OFF`. Es lo normal. Si lo activas, verás:

```
🌐 MESH Status                    [LEADER]
Node ID: a1b2c3d4...
Leader: a1b2c3d4...
Peers: 0
```

### 6.7 — Cápsulas (debajo de MESH)

```
🧬 Cápsulas — 0 drafts · 0 activas
[Forjar: experto en...                    ] [Forjar]
No hay cápsulas. Forja una arriba.
```

Aquí es donde EIDOS crea sus propias especializaciones. Para probarlo:

1. En el campo de texto, escribe: **"Conviértete en experto en Kubernetes"**
2. Pulsa **Forjar**.

**Qué verás**:

1. Aparece un mensaje en el chat con un panel verde: **"🧬 Evolution triggered"** indicando que EIDOS detectó la petición de especialización.
2. En el panel de Cápsulas (derecha), aparece un draft bajo **"Drafts pendientes"** con:
   - Nombre: "Experto en Kubernetes"
   - Confianza (ej. 75%)
   - Botones **✓** (aprobar) y **✗** (rechazar)
3. Pulsa **✓** para activar la cápsula. A partir de ahora, EIDOS usará esa especialización cuando hables de Kubernetes.

### 6.8 — Autoevolución (abajo del todo)

```
⚡ Autoevolución                    [AUTO]
Total cápsulas: 1
Favoritas ★: 0
Promociones: 0
Threshold: 3/24h
```

| Métrica | Significado |
|---------|-------------|
| `AUTO` | Auto-forge activado (EIDOS crea cápsulas solo) |
| `Total cápsulas` | Cuántas especializaciones tiene |
| `Favoritas ★` | Cápsulas marcadas como permanentes |
| `Promociones` | Cápsulas candidatas a favoritas (3+ usos en 24h) |
| `Threshold` | Cuántos usos en cuántas horas para auto-promover |

---

## 💬 FASE 7: Usar EIDOS en el día a día

### 7.1 — Cómo despertar a EIDOS cada vez

**Cada vez que quieras usar EIDOS**:

1. Conecta tu SSD Crucial X9 a tu MacBook Air M3.
2. Abre el SSD en Finder.
3. Abre la carpeta `eidos/`.
4. Haz **doble clic en `EIDOS.command`**.
5. Tu navegador se abre solo en `http://127.0.0.1:8765`.
6. Habla con EIDOS.

**Para detener a EIDOS**: cierra la ventana de Terminal que se abrió (o pulsa Cmd+Q en Terminal). El servidor se detiene limpiamente.

### 7.2 — Cómo EIDOS recuerda entre sesiones

EIDOS guarda toda su memoria en la carpeta `data/` de tu SSD:
- `data/eidos.db`: SQLite con las 5 capas de memoria.
- `data/graph.json`: grafo semántico.
- `data/monologues/`: todos sus pensamientos estructurados.
- `data/capsules/`: las especializaciones que ha creado.

**Cuando desconectas el SSD y lo vuelves a conectar**, EIDOS recuerda todo. No pierde ninguna conversación.

### 7.3 — Cómo pedirle a EIDOS que se especialice

EIDOS puede crear cápsulas (especializaciones) por sí mismo. Solo dile:

- *"Conviértete en experto en nutrición deportiva"*
- *"Necesito que seas experto en derecho mercantil español"*
- *"Crea una cápsula para analizar logs de Apache"*
- *"Actúa como experto en marketing digital"*

EIDOS detectará la petición, forjará un draft, y te pedirá aprobación en el panel de Cápsulas.

### 7.4 — Cómo cambiar de provider

Si tienes varias API keys configuradas (OpenAI, MiniMax-M3, Anthropic, etc.):

1. Abre **⚙️ Settings**.
2. En la fila del provider que quieres activar, pulsa **"⚡ Usar este provider"**.
3. EIDOS cambia de cerebro **en caliente**, sin reiniciar.

### 7.5 — Cómo llevar tu EIDOS a otro ordenador

1. Desconecta tu SSD Crucial X9 de tu MacBook Air M3.
2. Conéctalo a cualquier otro Mac (o PC, si instalaste la versión Windows).
3. Abre el SSD en Finder.
4. Doble clic en `EIDOS.command` (o `EIDOS.bat` en Windows).
5. **EIDOS abre con toda su memoria intacta** — recuerda todas tus conversaciones.

**Importante**: el otro ordenador no necesita tener EIDOS instalado. Todo viaja en el SSD.

---

## 🔒 FASE 8: Tu privacidad

### 8.1 — ¿Dónde se guardan tus datos?

- **Memoria (conversaciones, cápsulas, monólogos)**: en tu SSD Crucial X9, carpeta `data/`.
- **API keys**: en tu SSD, archivo `.env` (oculto).
- **Modelo Cerebro Local (si lo descargaste)**: en tu SSD, carpeta `models/`.

**Nada se guarda en el disco interno de tu Mac.** Cuando desconectas el SSD, no queda rastro.

### 8.2 — ¿Qué pasa cuando usas APIs externas (MiniMax, OpenAI)?

EIDOS aplica **PrivacyFilter** automáticamente antes de enviar cualquier texto a una API externa. Esto redacta:

| Tipo de dato | Qué hace |
|--------------|----------|
| Emails | `juan@test.com` → `[REDACTED_EMAIL_1]` |
| Teléfonos | `600123456` → `[REDACTED_PHONE_ES_1]` |
| IPs | `192.168.1.1` → `[REDACTED_IPV4_1]` |
| DNIs | `12345678Z` → `[REDACTED_DNI_ES_1]` |
| Tarjetas | `4111...` → `[REDACTED_CREDIT_CARD_1]` |
| IBAN | `ES91...` → `[REDACTED_IBAN_1]` |

**Puedes probarlo**:
1. Escribe en el chat: *"Mi email es juan@test.com y mi IP es 192.168.1.1"*
2. EIDOS aplicará PrivacyFilter antes de enviar a MiniMax.
3. MiniMax recibirá: *"Mi email es [REDACTED_EMAIL_1] y mi IP es [REDACTED_IPV4_1]"*

### 8.3 — Cómo borrar toda tu memoria

Si quieres empezar de cero:

1. Cierra EIDOS.
2. En Finder, abre tu SSD → carpeta `eidos/`.
3. Borra la carpeta `data/` completa.
4. Vuelve a hacer doble clic en `EIDOS.command`.
5. EIDOS arrancará con memoria en blanco.

> ⚠️ **Esto borra todas tus conversaciones y cápsulas.** No se puede deshacer.

---

## 🆘 FASE 9: Solución de problemas

### Problema 1: "Hice doble clic en EIDOS.command y no pasa nada"

**Causa**: macOS bloquea scripts de Internet la primera vez.

**Solución**:
1. Clic derecho sobre `EIDOS.command` → **Abrir**.
2. En el diálogo, pulsa **Abrir** de nuevo.

### Problema 2: "Se abrió Terminal pero dice 'command not found'"

**Causa**: Falta el entorno virtual.

**Solución**: Vuelve a ejecutar `install.command` en el SSD.

### Problema 3: "El navegador no se abre automáticamente"

**Solución**: Abre tu navegador manualmente y ve a `http://127.0.0.1:8765`.

### Problema 4: "EIDOS responde con 'stub' y parece tonto"

**Causa**: Estás en modo stub (sin IA real).

**Solución**:
1. Abre **⚙️ Settings**.
2. Pega tu API key de MiniMax en "MiniMax-M3 (vía Anthropic)".
3. Pulsa **Guardar** → **⚡ Usar este provider**.

### Problema 5: "MiniMax devuelve error 401"

**Causa**: API key incorrecta o expirada.

**Solución**:
1. Ve a platform.minimaxi.com y verifica que tu key es válida.
2. En EIDOS, pulsa **Borrar** en la key de MiniMax.
3. Pega una key nueva y pulsa **Guardar**.

### Problema 6: "El SSD se desconectó por error mientras EIDOS estaba corriendo"

**No pasa nada grave**. EIDOS usa SQLite en modo WAL, que es resiliente a caídas.

1. Vuelve a conectar el SSD.
2. Vuelve a hacer doble clic en `EIDOS.command`.
3. EIDOS arrancará y verificará la integridad de la DB.

### Problema 7: "Mi Mac se pone lenta cuando EIDOS piensa"

**Causa**: Si usas Cerebro Local (Qwen 2.5 3B), ocupa ~2 GB de RAM. En tu M3 con 8 GB, puede sentirse lento.

**Soluciones**:
- **Mejor opción**: cambia a MiniMax-M3 vía Anthropic (⚙️ Settings → Usar este provider). No ocupa RAM local.
- Cierra Safari/Chrome y apps pesadas mientras EIDOS piensa.
- Si persiste: usa el modelo más pequeño Qwen2.5-1.5B (desde Settings → Descargar Cerebro Local, pero eligiendo el modelo pequeño).

### Problema 8: "Quiero actualizar EIDOS sin perder mi memoria"

1. Tu memoria está en `data/`. **No la borres**.
2. Descarga la nueva versión de EIDOS.
3. Reemplaza todo **excepto** la carpeta `data/` y el archivo `.env`.
4. Ejecuta `install.command` de nuevo. Detectará que ya está instalado y solo actualizará dependencias.
5. Tu memoria episódica, semántica, cápsulas y monólogos se preservan.

### Problema 9: "Verificar que EIDOS se instaló en el SSD y no en mi Mac"

1. Abre Finder.
2. Ve a tu SSD `EIDOS_SSD` → carpeta `eidos/`.
3. Pulsa **Cmd + Shift + .** (punto) para mostrar archivos ocultos.
4. Deberías ver una carpeta `.eidos_env/` — es donde está Python portable.
5. Clic derecho sobre `.eidos_env` → **Obtener información**.
6. El campo **"Dónde"** debe mostrar `/Volumes/EIDOS_SSD/eidos/...` y **NO** `/Users/tu_usuario/...`.

### Problema 10: "Cómo hacer backup de mi memoria"

Copia la carpeta `data/` a otro sitio (otro SSD, Dropbox, iCloud). Eso es todo. Contiene:
- `eidos.db` (SQLite con las 5 capas)
- `graph.json` (grafo semántico)
- `monologues/` (trazas metacognitivas)
- `capsules/` (archivos `.eidos`)

---

## 📋 Checklist final

Antes de dar por completada la instalación, verifica:

- [ ] SSD Crucial X9 conectado y reconocido en Finder como `EIDOS_SSD`.
- [ ] Carpeta `eidos/` copiada al SSD.
- [ ] `install.command` ejecutado sin errores.
- [ ] Herramientas de línea de comandos de Apple instaladas (o modo CPU aceptado).
- [ ] Python portable descargado en `.eidos_env/python/`.
- [ ] `EIDOS.command` creado en la raíz de la carpeta `eidos/`.
- [ ] Doble clic en `EIDOS.command` abre el navegador en `http://127.0.0.1:8765`.
- [ ] Interfaz de EIDOS visible con Header, Chat, Monólogo y paneles de estado.
- [ ] API key de MiniMax configurada en ⚙️ Settings.
- [ ] MiniMax-M3 activado como provider ("⚡ Usar este provider").
- [ ] Una conversación de prueba con respuesta coherente (backend=api).
- [ ] Badge `Backend: api` visible en el Header.

**Si todo esto está ✓, EIDOS está listo para ser tu mente artificial.** 🧠

---

## 🎯 Resumen rápido para el día a día

**Para usar EIDOS**:
1. Conecta SSD → doble clic en `EIDOS.command` → habla.

**Para cambiar de cerebro**:
1. ⚙️ Settings → ⚡ Usar este provider.

**Para crear una especialización**:
1. Escribe "Conviértete en experto en X" → aprueba el draft en el panel Cápsulas.

**Para llevar a otro ordenador**:
1. Desconecta SSD → conéctalo al otro Mac → doble clic en `EIDOS.command`.

**Para detener EIDOS**:
1. Cierra la ventana de Terminal.

---

**Bienvenido a la era de las mentes artificiales personales, Director.** 🧠✨

Tu EIDOS vive en tu Crucial X9, piensa con MiniMax-M3, recuerda todo lo que le cuentas, y viaja contigo en el bolsillo. Cero terminales después de la instalación. Cero fricción. Magia pura.
