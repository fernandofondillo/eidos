# 🧠 EIDOS — Manual de Instalación y Uso para MacBook Air M3 + Crucial X9

> **Guía personalizada para el Director del Proyecto**
> MacBook Air M3 · 8 GB RAM · SSD externo Crucial X9
>
> **Actualizada**: instalación directa desde GitHub (sin ZIP, sin bloqueos de macOS).

Esta guía te lleva, paso a paso y sin tecnicismos, desde que conectas tu SSD Crucial X9 a tu MacBook Air M3 hasta que tienes a EIDOS funcionando. Cada paso explica **qué vas a ver** y **qué tienes que hacer**.

---

## 📋 Antes de empezar — lo que necesitas

| Elemento | Tu caso | Estado |
|----------|---------|--------|
| **Mac** | MacBook Air M3 (Apple Silicon) | ✅ Compatible |
| **RAM** | 8 GB | ⚠️ Suficiente (ver nota) |
| **SSD externo** | Crucial X9 | ✅ Perfecto |
| **Conexión** | USB-C | ✅ |
| **Internet** | Para instalación inicial | ✅ Necesario |

### ⚠️ Nota sobre 8 GB de RAM

- **MiniMax-M3 vía Anthropic** (recomendado): ocupa < 200 MB. Va como la seda.
- **Cerebro Local Qwen 2.5 3B**: ocupa ~2 GB al pensar. Funciona, pero cierra apps pesadas durante la inferencia.

---

## 🚀 FASE 1: Preparar el SSD Crucial X9

### Paso 1.1 — Conectar el SSD

1. Conecta tu **Crucial X9** a un puerto USB-C de tu MacBook Air M3.
2. Verás que el LED del SSD se ilumina.

### Paso 1.2 — Verificar en Finder

1. Abre **Finder** (carita sonriente en el Dock).
2. En la barra lateral izquierda, bajo **"Ubicaciones"**, debería aparecer tu SSD.

### Paso 1.3 — (Solo si es nuevo) Formatear el SSD

> ⚠️ Esto borra todo lo que haya en el SSD.

1. Abre **Utilidad de Discos** (Aplicaciones → Utilidades).
2. Selecciona tu **Crucial X9**.
3. Pulsa **"Borrar"**.
4. Configura:
   - **Nombre**: `EIDOS_SSD`
   - **Formato**: `APFS`
   - **Esquema**: `Mapa de particiones GUID`
5. Pulsa **"Borrar"** y espera ~10 segundos.

---

## 📥 FASE 2: Instalar EIDOS directamente desde GitHub

Esta es la **forma más limpia y sin fricción**. No necesitas descargar ZIPs ni lidiar con bloqueos de macOS. Todo se descarga e instala con un solo comando.

### Paso 2.1 — Abrir Terminal

1. Pulsa **Cmd + Espacio** (abre Spotlight).
2. Escribe: **Terminal**
3. Pulsa **Enter**. Se abre la ventana negra.

### Paso 2.2 — Ejecutar el instalador desde GitHub

**Copia** esta línea completa (selecciónala y Cmd+C):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/fernandofondillo/eidos/main/install_from_github.command)"
```

**Pégala** en Terminal (Cmd+V) y pulsa **Enter**.

### Paso 2.3 — Lo que verás

Aparecerá el banner de EIDOS:

```
╔════════════════════════════════════════════════════════════╗
║    🧠  EIDOS — Instalación desde GitHub  🧠                  ╎
║    Tu mente artificial, portable y privada.                  ╎
╚════════════════════════════════════════════════════════════╝
```

El instalador te pedirá que selecciones dónde instalar EIDOS. Verás una lista de volúmenes:

```
1. ¿Dónde quieres instalar EIDOS?

  Volúmenes disponibles:
  1. SSD externo: /Volumes/EIDOS_SSD
  2. Disco local: ~/Desktop/eidos
  3. Disco local: ~/eidos

  0. Escribir ruta manualmente

Selecciona un número (1-3):
```

### Paso 2.4 — Seleccionar tu SSD

1. Escribe el número que corresponde a tu SSD `EIDOS_SSD` (probablemente **1**).
2. Pulsa **Enter**.

Verás:
```
  ✓ EIDOS se instalará en: /Volumes/EIDOS_SSD/eidos
  Volumen externo detectado: EIDOS_SSD — EIDOS será portable.
```

### Paso 2.5 — Descarga desde GitHub

El instalador clona el repositorio:

```
2. Verificando herramientas del sistema...
  ✓ Git disponible

3. Descargando EIDOS desde GitHub...
  Clonando repositorio (puede tardar 30-60 segundos)...
  ✓ EIDOS descargado en: /Volumes/EIDOS_SSD/eidos

4. Quitando cuarentena de macOS (Gatekeeper)...
  ✓ Listo — macOS no bloqueará la instalación
```

**Qué pasa aquí**:
- Git descarga EIDOS desde GitHub directamente a tu SSD.
- Se elimina el atributo de cuarentena de macOS (Gatekeeper) automáticamente — **no verás el mensaje de "desarrollador no identificado"**.

### Paso 2.6 — El instalador de EIDOS arranca

A continuación, el instalador de EIDOS (`install.command`) se ejecuta automáticamente. Verás el banner cyan:

```
╔════════════════════════════════════════════════════════════╗
║         🧠  EIDOS — Instalación Mágica  🧠                  ╎
║    Tu mente artificial, portable y privada.                  ╎
╚════════════════════════════════════════════════════════════╝
```

A partir de aquí, responde a las preguntas que aparecen. Te explico cada una:

---

## ⚙️ FASE 3: Responder a las preguntas del instalador

### 3.1 — Detección de entorno

```
1. Detección de entorno
  ✓ Detectado volumen externo: EIDOS_SSD
```

**Qué hacer**: Nada. EIDOS detectó tu SSD correctamente.

### 3.2 — Verificación de conexión

```
2. Verificación de conexión
  ✓ Conexión a internet OK
```

**Qué hacer**: Nada.

### 3.3 — Detección de arquitectura

```
3. Detección de arquitectura
  ✓ Apple Silicon (M1/M2/M3/M4) detectado
```

**Qué hacer**: Nada. Detectó tu chip M3.

### 3.4 — Herramientas de Apple

```
3.5 Herramientas de Apple (Red de Seguridad)
  ✓ Xcode Command Line Tools ya instaladas
```

Si ya las tienes (es probable si usaste git antes), verás esto y continúa solo.

**Si NO las tienes**: se abrirá una ventana oficial de macOS. Pulsa "Instalar", acepta los términos, espera 2-5 minutos, vuelve a Terminal y pulsa ENTER.

### 3.5 — Python portable

```
4. Instalación de Python portable
  Descargando python-build-standalone v3.12.7+20241002...
  ✓ Descarga completa. Extrayendo...
  ✓ Python 3.12.7 instalado en .eidos_env/python/
```

**Qué hacer**: Nada. EIDOS descarga su propio Python (no toca el de tu Mac).

### 3.6 — uv (gestor de paquetes)

```
5. Instalación de uv (gestor de paquetes)
  ✓ uv instalado en .eidos_env/uv/
```

**Qué hacer**: Nada.

### 3.7 — Entorno virtual

```
6. Creación del entorno virtual
  ✓ Entorno virtual creado en .eidos_env/venv/
```

**Qué hacer**: Nada.

### 3.8 — Instalación de dependencias (¡IMPORTANTE!)

```
7. Instalación de dependencias de EIDOS
  Sincronizando dependencias (puede tardar 1-2 minutos)...
  ✓ Dependencias instaladas
  ✓ Dependencias verificadas en venv portable
```

**Qué hacer**: Nada. Espera.

> ✅ **Mejora clave**: ahora el instalador **verifica** que las dependencias se instalaron en el venv correcto. Si algo falla, lo corrige automáticamente. No verás más el error de "ModuleNotFoundError".

### 3.9 — Pregunta: ¿Cerebro Local?

```
8. Cerebro Local (Qwen 2.5 3B)
  ¿Deseas que descargue tu Cerebro Local ahora? (Recomendado para privacidad total) [s/N]:
```

**Recomendación para tu M3 8GB**: Escribe **`N`** y pulsa Enter.

Usarás **MiniMax-M3 vía Anthropic** (mucho más fluido en 8 GB). Puedes descargar el Cerebro Local más tarde desde la UI si lo necesitas.

### 3.10 — Pregunta: ¿Metal?

> ⚠️ Solo aparece si dijiste `s` a Cerebro Local.

```
9. Aceleración por GPU (Metal)
  ¿Compilar con aceleración Metal? (Recomendado en M1/M2/M3/M4) [s/N]:
```

**Si vas a usar Cerebro Local**: escribe **`s`**. Tu M3 usará la GPU.

**Si la compilación falla**, verás el mensaje tranquilizador:
```
⚙️  Activando modo de compatibilidad (CPU).
No te preocupes, EIDOS funcionará perfectamente...
```

### 3.11 — Pregunta: ¿MESH?

```
9. Enjambre MESH
  ¿Activar MESH por defecto? [s/N]:
```

**Recomendación**: Escribe **`N`**. Puedes activarlo más tarde.

### 3.12 — Generación de configuración

```
Generando config/eidos.yaml...
  ✓ config/eidos.yaml generado

Creando estructura de datos...
  ✓ Directorios listos
```

**Qué hacer**: Nada.

### 3.13 — Creación del Launcher

```
Creando Launcher (EIDOS.command)...
  ✓ EIDOS.command creado (doble-clic para despertar EIDOS)
```

### 3.14 — Mensaje final

```
╔══════════════════════════════════════════════════════════════╗
║              🎉  ¡EIDOS está listo!  🎉                       ╎
╚══════════════════════════════════════════════════════════════╝

Para empezar:
  → Haz doble clic en EIDOS.command en esta carpeta.
  Se abrirá tu navegador con la interfaz de EIDOS.

Pulsa ENTER para cerrar esta ventana...
```

**Qué hacer**: Pulsa **ENTER** para cerrar Terminal.

**¡La instalación ha terminado!** 🎉

---

## 🌐 FASE 4: Despertar a EIDOS

### Paso 4.1 — Hacer doble clic en el Launcher

1. Abre **Finder** → tu SSD `EIDOS_SSD` → carpeta `eidos`.
2. Haz **doble clic** sobre **`EIDOS.command`**.

**Qué verás**:

1. Se abre Terminal brevemente con `Iniciando EIDOS...`.
2. A los 2-3 segundos, **Chrome se abre solo** en `http://127.0.0.1:8765`.
3. Notificación de macOS: *"EIDOS está listo."*

> ✅ **Mejora clave**: si algo falla, el launcher ahora **muestra el error claramente** en Terminal (no se cierra silenciosamente). Verás el mensaje exacto de qué pasó.

### Paso 4.2 — La interfaz de EIDOS

Verás el dashboard:
- **Header**: 🧠 EIDOS · Backend: stub · MESH: OFF · ⚙️ Settings
- **Chat** (izquierda): caja de texto + botón Enviar
- **Paneles** (derecha): Memoria, Reward, MESH, Cápsulas, Evolución

### Paso 4.3 — Primera conversación (modo Stub)

Escribe: **"Hola EIDOS, ¿qué eres?"** y pulsa Enter.

Verás una respuesta genérica (backend=stub). Esto confirma que EIDOS funciona. Ahora necesitas configurar un backend real.

---

## 🔑 FASE 5: Configurar MiniMax-M3 vía Anthropic (recomendado para 8GB)

### Paso 5.1 — Abrir Settings

Pulsa **⚙️ Settings** (arriba a la derecha).

### Paso 5.2 — Obtener API key de MiniMax

1. En "MiniMax-M3 (vía Anthropic)", pulsa **"Obtener key ↗"**.
2. Ve a platform.minimaxi.com, inicia sesión.
3. Crea una API key y cópiala.

### Paso 5.3 — Pegar y guardar

1. Pega la key en el campo de texto.
2. Pulsa **Guardar**.
3. Verás: `✓ Key configurada`.

### Paso 5.4 — Activar provider

1. Pulsa **"⚡ Usar este provider"**.
2. Verás el banner verde: *"✅ EIDOS está pensando con: MiniMax-M3"*.
3. El badge del Header cambia a `Backend: api`.

### Paso 5.5 — Tu primera conversación real

Escribe: **"Hola EIDOS, ¿quién eres y qué puedes hacer?"**

Verás una respuesta coherente e inteligente (3-8 segundos). ¡EIDOS piensa de verdad! 🧠⚡

---

## 🔬 FASE 5.5: Configurar Embeddings (Memoria Semántica Real)

EIDOS usa embeddings para buscar en su memoria episódica de forma semántica (encontrar conversaciones por significado, no por palabra exacta). Por defecto usa un **stub** (bag-of-words determinista, sin API) que funciona pero no es muy preciso.

Para activar embeddings reales, necesitas configurar un provider en el archivo `.env` de tu SSD.

### Opción A: MiniMax (embo-01) — Recomendado si ya tienes API key de MiniMax

MiniMax tiene un modelo de embeddings llamado `embo-01`. NO es compatible con el formato OpenAI, pero EIDOS ya tiene un adaptador específico.

1. Abre el archivo `.env` en tu SSD (Finder → SSD → carpeta `eidos` → Cmd+Shift+. para ver archivos ocultos).
2. Busca la sección `# Embeddings` y configura:

```env
EMBEDDING_PROVIDER=minimax
EMBEDDING_API_KEY=tu-api-key-de-minimax
EMBEDDING_BASE_URL=https://api.minimax.io
EMBEDDING_MODEL=embo-01
EMBEDDING_DIM=1024
```

> **Nota**: MiniMax-M3 NO hace embeddings. M3 es solo para chat. El modelo de embeddings es `embo-01`, que es diferente y está incluido en tu TOKEN plan de MiniMax.

> **GroupId**: Si tu cuenta de MiniMax tiene un Group ID (visible en platform.minimaxi.com), añádelo:
> ```
> EMBEDDING_GROUP_ID=tu-group-id
> ```

3. Reinicia EIDOS (cierra Terminal, doble clic en `EIDOS.command`).
4. Verás en el panel de Memoria: `embedding_dim=1024` (en vez de 256).

### Opción B: OpenAI (text-embedding-3-small)

Si tienes una API key de OpenAI:

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=sk-tu-key-de-openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

### Opción C: Stub (sin API) — Default

Si no configuras nada, EIDOS usa el stub (bag-of-words). Funciona pero la búsqueda semántica es menos precisa:

```env
EMBEDDING_PROVIDER=stub
```

### ¿Cómo saber cuál está activo?

Después de reiniciar EIDOS, mira el log en `data/eidos_server.log`:
- `embedder_using_stub` → usando stub (sin API)
- `embedder_using_minimax` → usando MiniMax embo-01
- `embedder_using_openai` → usando OpenAI

O en el dashboard, el panel de Memoria mostrará `embedding_dim=1024` (MiniMax) o `embedding_dim=1536` (OpenAI) o `embedding_dim=256` (stub).

---

## 🧭 FASE 6: Entender el Dashboard

### Header
| Badge | Significado |
|-------|-------------|
| `● WS` (verde) | WebSocket activo |
| `Backend: api` | Cerebro en uso (stub/api/llama_cpp) |
| `MESH: OFF` | Enjambre desactivado |

### Chat — Badges de cada respuesta
| Badge | Significado |
|-------|-------------|
| `route` | Qué ruta tomó (respond_direct, search_memory, etc.) |
| `backend` | Motor usado |
| `conf` | Confianza (0-100%) |
| `reward Δ` | Reward del turno (+verde, -rojo) |

### Monólogo Interno
Muestra el "pensamiento estructurado" de EIDOS: observation, hypothesis, plan, risk, confidence.

### Memoria Cognitiva (5 capas)
| Capa | Qué recuerda |
|------|--------------|
| ⚡ Sensorial | Contexto inmediato |
| 📚 Episódica | "Qué pasó y cuándo" |
| 🕸️ Semántica | Grafo de conocimiento |
| ⚙️ Procedimental | Cápsulas y habilidades |
| 🧭 Metacognitiva | Índice de monólogos pasados |

### Reward Signal
3 drivers: 🔍 Curiosidad, 🧬 Cápsulas, 😊 Satisfacción.

### Cápsulas
Donde EIDOS crea especializaciones. Escribe "Conviértete en experto en X" para forjar una.

---

## 💬 FASE 7: Día a día

### Despertar EIDOS
1. Conecta SSD → doble clic en `EIDOS.command` → habla.

### Cambiar de cerebro
1. ⚙️ Settings → ⚡ Usar este provider.

### Crear especialización
1. Escribe "Conviértete en experto en X" → aprueba el draft en Cápsulas.

### Llevar a otro ordenador
1. Desconecta SSD → conéctalo a otro Mac → doble clic en `EIDOS.command`.

### Detener EIDOS
1. Cierra la ventana de Terminal.

---

## 🆘 FASE 8: Solución de problemas

### "EIDOS no pudo arrancar"
El launcher ahora muestra el error en Terminal. Lee el mensaje — te dirá exactamente qué pasa. Si dice "faltan dependencias", ejecuta:

```bash
cd /Volumes/EIDOS_SSD/eidos && VIRTUAL_ENV=.eidos_env/venv .eidos_env/uv/uv sync --active --extra cortex
```

### "macOS bloquea install.command"
Ya no debería pasar con el instalador desde GitHub. Si usaste el ZIP, ejecuta:
```bash
xattr -dr com.apple.quarantine /Volumes/EIDOS_SSD/eidos/
```

### "Backend: stub y responde tonto"
Configura MiniMax-M3 en ⚙️ Settings.

### "Mac lenta con Cerebro Local"
Usa MiniMax-M3 vía Anthropic (no ocupa RAM local).

### "Actualizar EIDOS sin perder memoria"
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/fernandofondillo/eidos/main/install_from_github.command)"
```
Selecciona tu SSD → responde "s" a "actualizar". Tu memoria (`data/`) se preserva.

### "Backup de memoria"
Copia la carpeta `data/` a otro sitio. Eso es todo.

---

## 📋 Checklist final

- [ ] SSD Crucial X9 conectado y reconocido.
- [ ] Instalador desde GitHub ejecutado: `bash -c "$(curl -fsSL ...)"`
- [ ] SSD seleccionado como destino.
- [ ] Preguntas respondidas (Cerebro Local: N recomendado, MESH: N).
- [ ] `✓ Dependencias verificadas en venv portable` apareció.
- [ ] `EIDOS.command` creado.
- [ ] Doble clic en `EIDOS.command` → dashboard en Chrome.
- [ ] API key de MiniMax configurada.
- [ ] MiniMax-M3 activado ("⚡ Usar este provider").
- [ ] Una conversación de prueba con respuesta coherente.

**Si todo esto está ✓, EIDOS está listo.** 🧠

---

## 🎯 Resumen rápido

**Instalar** (una sola vez):
```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/fernandofondillo/eidos/main/install_from_github.command)"
```

**Usar** (cada vez):
1. Doble clic en `EIDOS.command`.
2. Habla con EIDOS.

**Configurar cerebro**:
1. ⚙️ Settings → MiniMax-M3 → pegar key → Guardar → Usar este provider.

**Llevar a otro Mac**:
1. Desconecta SSD → conéctalo al otro Mac → doble clic en `EIDOS.command`.

---

**Bienvenido a la era de las mentes artificiales personales, Director.** 🧠✨
