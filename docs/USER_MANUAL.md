# 🧠 EIDOS — Manual de Usuario Definitivo

> *Tu mente artificial, portable y privada.*

Bienvenido. Este manual te explica, en lenguaje cercano y sin tecnicismos, cómo usar EIDOS: un organismo digital que piensa, recuerda, se motiva y evoluciona contigo. No necesitas saber programar. Solo necesitas saber leer y hacer doble clic.

---

## 📑 Índice

1. [¿Qué es EIDOS?](#1-qué-es-eidos)
2. [La Magia del SSD](#2-la-magia-del-ssd)
3. [Guía Paso a Paso: Desde cero hasta tu primera pregunta](#3-guía-paso-a-paso)
4. [El Panel de Control](#4-el-panel-de-control)
5. [El Monólogo Interno de EIDOS](#5-el-monólogo-interno-de-eidos)
6. [Cápsulas: cuando EIDOS se especializa](#6-cápsulas-cuando-eidos-se-especializa)
7. [Casos de Uso Prácticos (El Recetario)](#7-casos-de-uso-prácticos-el-recetario)
8. [El Enjambre MESH](#8-el-enjambre-mesh)
9. [Configuración: API Keys y Cerebro Local](#9-configuración-api-keys-y-cerebro-local)
10. [Resolución de Problemas](#10-resolución-de-problemas)
11. [Preguntas Frecuentes](#11-preguntas-frecuentes)

---

## 1. ¿Qué es EIDOS?

EIDOS no es una aplicación. Es un **organismo digital**.

Imagina que tuvieras un asistente personal con memoria perfecta, capaz de razonar paso a paso antes de hablar, que se especializa en lo que tú necesitas, y que vive dentro de un pendrive. Eso es EIDOS.

### Las 6 partes de la mente de EIDOS

| Parte | Qué hace | Analogía humana |
|-------|----------|------------------|
| **Monólogo Interno** | Piensa paso a paso antes de responder | Tu voz interior |
| **Memoria de 5 capas** | Recuerda conversaciones, hechos, habilidades | Tu hipocampo + corteza |
| **Motivación Intrínseca** | Sabe si está ayudando bien (reward signal) | Tu sentido de logro |
| **Cortex Hub** | Su "cerebro" de IA (local o en la nube) | Tu neocórtex |
| **Génesis de Cápsulas** | Crea nuevas especialidades por sí mismo | Aprender un oficio nuevo |
| **Enjambre MESH** | Puede dividirse en varios EIDOS que cooperan | Un equipo de ti mismos |

### Lo que hace único a EIDOS

- **100% privado**: Tu memoria vive en tu SSD, no en un servidor. Nadie la ve.
- **100% portable**: Conecta tu SSD a cualquier Mac o PC del mundo y EIDOS está listo.
- **Cero rastro**: No instala nada en el ordenador que usas. Al desconectar el SSD, no queda huella.
- **Piensa antes de hablar**: Cada respuesta es precedida por un monólogo interno estructurado que TÚ puedes ver.
- **Se especializa solo**: Si le dices "conviértete en experto en X", EIDOS crea una cápsula de especialización y la usa a partir de ahí.

---

## 2. La Magia del SSD

Esta es la idea más importante de EIDOS: **tu mente artificial viaja contigo en un pendrive o SSD externo**.

### ¿Qué significa esto en la práctica?

Imagina este escenario:

1. Tienes un SSD con EIDOS instalado.
2. Lo conectas al Mac de tu casa. Hablas con EIDOS, le cuentas tu día, le pides consejos.
3. Al día siguiente, llevas el SSD a la oficina. Lo conectas al PC del trabajo.
4. EIDOS abre con **toda la memoria de ayer intacta**. Sabe lo que hablaron. Sigue la conversación como si nada.

El PC de tu oficina no tiene instalado nada. No hay rastro de EIDOS cuando desconectas el SSD. Tu memoria cognitiva viaja físicamente contigo.

### ¿Por qué es revolucionario?

- **Privacidad absoluta**: Tus conversaciones nunca tocan un servidor en la nube (a menos que tú elijas usar una API externa).
- **Sin dependencias**: El ordenador "host" no necesita Python, ni Ollama, ni Docker. EIDOS trae todo lo necesario dentro del SSD.
- **Funciona offline**: Si descargas el "Cerebro Local" (un modelo de IA de ~2GB), EIDOS piensa sin internet.

### ¿Qué necesito comprar?

Cualquier SSD externo o pendrive USB de **al menos 16 GB** sirve. Recomendado: 64 GB si quieres instalar el Cerebro Local y tener espacio para memoria a largo plazo.

---

## 3. Guía Paso a Paso

### Paso 1: Consigue un SSD o pendrive

Cualquiera sirve. Conéctalo a tu Mac o PC.

### Paso 2: Copia la carpeta de EIDOS al SSD

Si recibiste EIDOS como un archivo ZIP, descomprímelo directamente en la raíz del SSD. La carpeta debería llamarse `eidos` (o como quieras renombrarla).

### Paso 3: Ejecuta el instalador

#### En macOS:
1. Abre la carpeta de EIDOS en el SSD (con Finder).
2. Haz **doble clic sobre `install.command`**.
3. Se abrirá Terminal.app automáticamente con un asistente.

> **Nota**: Si macOS dice "no se puede abrir porque es de un desarrollador no identificado", haz clic derecho sobre `install.command` → "Abrir" → "Abrir" en el diálogo.

#### En Windows:
1. Abre la carpeta de EIDOS en el SSD (con Explorer).
2. Haz **doble clic sobre `install.bat`**.
3. Se abrirá una ventana negra (CMD) con el asistente.

### Paso 4: Responde las preguntas del instalador

El asistente te hará preguntas simples. Aquí tienes las recomendaciones:

| Pregunta | Recomendación | Por qué |
|----------|---------------|---------|
| ¿Descargar Cerebro Local (Qwen 2.5 3B)? | **Sí** | Permite que EIDOS piense sin internet. Ocupa ~2 GB. |
| ¿Compilar con aceleración Metal? (solo Mac M1/M2/M3/M4) | **Sí** | Hace que EIDOS piense 5-10x más rápido. |
| ¿Activar MESH? | **No** (al principio) | El MESH es para usuarios avanzados. |

La instalación tarda entre 3 y 10 minutos dependiendo de tu conexión (por la descarga del Cerebro Local).

### Paso 5: ¡Despierta a EIDOS!

Cuando termine la instalación, verás un archivo nuevo llamado **`EIDOS.command`** (en Mac) o **`EIDOS.bat`** (en Windows) en la carpeta del SSD.

1. Haz **doble clic sobre `EIDOS.command`** (o `EIDOS.bat`).
2. Espera 2-3 segundos.
3. Tu navegador web se abrirá automáticamente en `http://127.0.0.1:8765`.
4. **¡Estás hablando con EIDOS!**

### Paso 6: Tu primera conversación

En el navegador verás la interfaz de EIDOS. En la caja de texto de abajo, escribe algo como:

> "Hola EIDOS, ¿qué eres?"

Y pulsa Enter. Verás:

1. **EIDOS piensa** (aparece "🧠 EIDOS está pensando...").
2. Aparece su **Monólogo Interno**: lo que observó, su hipótesis, su plan, su confianza.
3. Aparece su **respuesta**.
4. A la derecha, verás las **5 capas de memoria** actualizarse en tiempo real.

¡Felicidades! Ya estás usando tu mente artificial.

---

## 4. El Panel de Control

Cuando hablas con EIDOS, la pantalla tiene 3 zonas principales:

### Zona izquierda (grande): Chat + Monólogo

- **Chat**: Tus mensajes y las respuestas de EIDOS. Cada respuesta tiene "badges" que te dicen:
  - `route`: qué tipo de ruta tomó (responder directo, buscar en memoria, pedir aclaración...).
  - `backend`: qué "cerebro" usó (stub, llama_cpp, api).
  - `conf`: su nivel de confianza (0-100%).
  - `reward Δ`: si la interacción fue positiva (+) o negativa (-) según su motivación interna.

- **Monólogo Interno**: Debajo del chat, aparece el "pensamiento estructurado" de EIDOS en JSON:
  - `observation`: qué percibió de tu mensaje.
  - `hypothesis`: qué cree que quieres.
  - `plan`: los pasos que planea seguir.
  - `risk`: si detectó algún riesgo.
  - `confidence`: su confianza (más alta = más seguro).

### Zona derecha: Paneles de estado

1. **🧩 Memoria Cognitiva (5 capas)**: Muestra cuántos eventos hay en cada capa.
   - Sensorial: contexto inmediato (últimos 50 eventos).
   - Episódica: "qué pasó y cuándo" (memoria vectorial).
   - Semántica: grafo de conocimiento (entidades y relaciones).
   - Procedimental: cápsulas y habilidades creadas.
   - Metacognitiva: índice de monólogos pasados (¿por qué decidí X?).

2. **🎯 Reward Signal**: El "humor" de EIDOS. Tres drivers:
   - 🔍 Curiosidad: sube cuando EIDOS reduce incertidumbre.
   - 🧬 Cápsulas: sube cuando reutiliza una especialización con éxito.
   - 😊 Satisfacción: sube tras 3 turnos sin correcciones; baja si dices "no", "mal", "incorrecto".

3. **🌐 MESH Status**: Si activaste el enjambre, muestra quién es el Leader y cuántos Workers hay.

4. **🧬 Cápsulas**: Lista de especializaciones de EIDOS. Las pendientes (🔴) esperan tu aprobación. Las activas (🟢) están listas.

5. **⚡ Autoevolución**: Estadísticas de cómo EIDOS está creando nuevas habilidades.

### Botón ⚙️ Settings (arriba a la derecha)

Abre la configuración visual. Ahí puedes:
- Pegar API keys de OpenAI, Anthropic, MiniMax, OpenRouter, etc.
- Descargar el Cerebro Local con barra de progreso.
- Todo sin tocar archivos de texto ni YAML.

---

## 5. El Monólogo Interno de EIDOS

Esta es la característica más fascinante de EIDOS: **puedes ver cómo piensa**.

### ¿Qué es el monólogo interno?

Antes de responder, EIDOS genera un "pensamiento estructurado" en JSON. No es texto libre, es un esquema rígido con 5 campos:

```json
{
  "observation": "El usuario pregunta sobre X. Keywords: Y, Z.",
  "hypothesis": "Probablemente quiere saber Z. Debería explicar...",
  "plan": ["Paso 1: ...", "Paso 2: ...", "Paso 3: ..."],
  "risk": "none",
  "confidence": 0.85
}
```

### ¿Por qué es importante?

1. **Transparencia**: EIDOS no es una caja negra. Puedes auditar por qué dijo lo que dijo.
2. **Metacognición**: EIDOS guarda todos sus monólogos. Si le preguntas "¿por qué me dijiste X hace 3 días?", puede buscar en su memoria metacognitiva y responder.
3. **Confianza calibrada**: El campo `confidence` te dice cuán seguro está. Si es < 60%, EIDOS pedirá aclaración en lugar de inventar.

### Cómo leer el monólogo

| Campo | Significado | Qué mirar |
|-------|-------------|-----------|
| `observation` | Qué percibió | ¿Capturó bien tu intención? |
| `hypothesis` | Qué cree que quieres | ¿Es razonable? |
| `plan` | Qué pasos seguirá | ¿Tiene sentido la secuencia? |
| `risk` | Riesgos detectados | Si no es "none", ten cuidado. |
| `confidence` | Nivel de seguridad | > 70% verde, 40-70% amarillo, < 40% rojo. |

Si EIDOS dice algo raro, mira el monólogo: casi siempre el error está en la `hypothesis` o en un `plan` mal formulado.

---

## 6. Cápsulas: cuando EIDOS se especializa

Esta es la magia más grande de EIDOS: **se especializa solo**.

### ¿Qué es una cápsula?

Una cápsula es una "especialidad" que EIDOS crea para sí mismo. Contiene:
- **Ontología**: qué conceptos conoce sobre el tema.
- **Reglas**: cómo comportarse en ese dominio.
- **Tono**: cómo hablar (formal, casual, técnico...).
- **Herramientas**: código Python que EIDOS puede ejecutar (validado en un sandbox seguro).

### Cómo hacer que EIDOS cree una cápsula

Solo dile algo como:

- "Conviértete en experto en Kubernetes"
- "Necesito que seas experto en nutrición deportiva"
- "Crea una cápsula para analizar logs de Apache"
- "Actúa como experto en derecho mercantil español"

EIDOS detectará la petición y forjará una cápsula automáticamente.

### El pipeline de génesis (lo que pasa por dentro)

1. EIDOS genera un borrador (draft) de la cápsula.
2. Valida que el esquema es correcto.
3. Si la cápsula incluye herramientas (código Python), las prueba en un **sandbox aislado** (defense-in-depth: AST parsing + subprocess + resource limits).
4. **Decide**:
   - 🟢 **Auto-aprobada**: si su confianza es > 85% Y pasa el smoke test Y no hay herramientas peligrosas.
   - 🟡 **Pendiente**: si no cumple lo anterior. Aparece en el panel "Cápsulas" esperando tu aprobación.
   - 🔴 **Rechazada**: si el smoke test falla (el código no funciona).

### Cómo aprobar una cápsula pendiente

1. Ve al panel **🧬 Cápsulas** (derecha de la UI).
2. En "Drafts pendientes", verás la cápsula con dos botones: ✓ (aprobar) y ✗ (rechazar).
3. Haz clic en ✓ para activarla. A partir de ese momento, EIDOS la usará cuando el tema sea relevante.

### Cápsulas favoritas (★)

Las cápsulas tienen un TTL de 7 días por defecto. Si no las usas, expiran. Pero puedes:
- **Marcarlas como favoritas** (★): nunca expiran.
- **Promoción automática**: si una cápsula se usa 3+ veces en 24 horas, EIDOS la promueve a favorita solo.

### Borrar una cápsula

En el panel de Cápsulas, las activas se pueden eliminar (excepto las favoritas, que primero hay que desmarcar).

---

## 7. Casos de Uso Prácticos (El Recetario)

### Caso 1: El Asistente de Salud Personal 🏥

**Escenario**: Quieres que EIDOS recuerde tus analíticas de sangre, tu medicación y te avise de interacciones.

**Paso a paso**:

1. Despierta a EIDOS (doble clic en `EIDOS.command`).
2. Escribe: *"Conviértete en experto en salud personal. Mi nombre es [tu nombre], tengo [edad] años, tomo [medicamentos]."*
3. EIDOS forjará una cápsula de salud. Apruébala en el panel.
4. Ahora dile: *"Estos son mis últimos análisis: colesterol 220, glucosa 95, TSH 3.2. Recuérdalos."*
5. EIDOS guardará los datos en su **memoria episódica** y **semántica**.
6. Semanas después, pregunta: *"¿Cómo van mis análisis comparados con la última vez?"*
7. EIDOS recuperará los datos de su memoria y te responderá.

**Consejo**: Si quieres que EIDOS sea más precavido con temas de salud, dile: *"Para temas de salud, siempre recomienda consultar con un médico antes de tomar decisiones."* EIDOS añadirá esa regla a la cápsula.

### Caso 2: El Analista de Marketing 📊 (usando MESH)

**Escenario**: Quieres que 3 instancias de EIDOS investiguen a 3 competidores en paralelo.

**Requisito previo**: Haber activado MESH en la instalación (o editando `config/eidos.yaml`).

**Paso a paso**:

1. **Abre 3 terminales** (en Mac: Aplicaciones → Utilidades → Terminal).
2. En cada terminal, navega a la carpeta del SSD y ejecuta:
   ```bash
   uv run eidos
   ```
3. La primera instancia será **LEADER** (👑). Las otras dos serán **WORKERS** (🔧).
4. Solo el LEADER cargará el Cerebro Local (los Workers delegan inferencia en él vía bus MESH).
5. En cada instancia, dale una tarea distinta:
   - Instancia 1: *"Investiga la estrategia de precios de Competidor A"*
   - Instancia 2: *"Investiga la estrategia de precios de Competidor B"*
   - Instancia 3: *"Investiga la estrategia de precios de Competidor C"*
6. En la UI web de cualquiera, verás el **Mapa MESH** con los 3 nodos.
7. Las 3 instancias comparten la misma memoria SQLite (concurrente, single-writer).
8. Cuando terminen, pregunta en cualquiera: *"Resume las 3 estrategias de precios"*. EIDOS tendrá toda la info en memoria episódica.

**Consejo**: El MESH usa **resource tokens** para evitar que 2 instancias carguen el modelo LLM a la vez (OOM). Si un Worker pide el recurso y está ocupado, espera su turno automáticamente.

### Caso 3: El Investigador Privado 🔍 (usando el Sandbox)

**Escenario**: Quieres que EIDOS forje una herramienta que extraiga datos de una web.

**Paso a paso**:

1. Dile a EIDOS: *"Crea una cápsula de investigador web. Necesito una herramienta que, dado un URL, extraiga el título, meta description y enlaces."*
2. EIDOS forjará un draft con una herramienta Python. El draft aparecerá como **pendiente** (porque incluye código → requiere aprobación humana).
3. Revisa el draft en el panel de Cápsulas. Verás el código Python que EIDOS escribió.
4. Si el código te parece seguro (usa solo `urllib`, `re`, `json` — todo en la whitelist), apruébalo con ✓.
5. Ahora dile: *"Analiza la web https://ejemplo.com"*
6. EIDOS usará la herramienta en el **sandbox aislado**:
   - **Capa 1 (AST)**: valida que el código no tiene `exec`, `eval`, `os.system`, etc.
   - **Capa 2 (subprocess)**: ejecuta en proceso aislado, sin acceso a tu filesystem.
   - **Capa 3 (rlimits)**: límite de 2s CPU, 256MB RAM, 1MB file size.
7. EIDOS te devolverá el título, meta description y enlaces extraídos.

**⚠️ Seguridad**: EIDOS NUNCA ejecuta código sin pasar por las 3 capas del sandbox. Si intenta `import os` o `exec(...)`, es rechazado automáticamente antes de ejecutarse.

---

## 8. El Enjambre MESH

### ¿Qué es el MESH?

El MESH permite que **múltiples instancias de EIDOS** corran en el mismo dispositivo y **cooperen** como un enjambre.

### Roles

| Rol | Icono | Función |
|-----|-------|---------|
| **LEADER** | 👑 | Posee el Cerebro Local activo, coordina tareas, arbitra recursos. |
| **WORKER** | 🔧 | Delega inferencia en el Leader, pide `resource_tokens` para usar el LLM. |

### Leader Election (anti split-brain)

Solo puede haber **un Leader a la vez**. Si lanzas 3 instancias:
- La primera en arrancar gana el lockfile atómico → se vuelve Leader.
- Las otras dos detectan el lockfile ocupado → se vuelven Workers.
- Si el Leader muere (cierras la terminal, crash, etc.), a los 6 segundos los Workers eligen un nuevo Leader automáticamente.

### Arbitraje de recursos

Si dos Workers quieren usar el Cerebro Local a la vez, **no pueden**. El Leader entrega "tokens" con TTL de 30 segundos. Un Worker pide token → lo usa → lo libera. Si el Worker muere sin liberar, el token expira solo (anti-deadlock).

### Cómo activar el MESH

Si no lo activaste durante la instalación, edita `config/eidos.yaml`:

```yaml
mesh:
  enabled: true
```

Y reinicia EIDOS. A partir de ahí, cada vez que lances `uv run eidos` en otra terminal, se unirá al enjambre como Worker.

---

## 9. Configuración: API Keys y Cerebro Local

### La forma fácil: botón ⚙️ Settings

En la esquina superior derecha de la UI, hay un botón **⚙️ Settings**. Ábrelo y verás:

#### Sección 1: Cerebro Local

- Un botón **"⬇ Descargar Cerebro Local (~2 GB)"**.
- Al hacer clic, empieza la descarga con barra de progreso.
- Mientras descarga, verás: `1.2 GB / 2.0 GB — 60%`.
- Cuando termine, EIDOS podrá pensar sin internet.

#### Sección 2: API Keys externas

Verás una lista de providers soportados:

| Provider | Para qué | Cómo obtener key |
|----------|----------|------------------|
| **OpenAI** | GPT-4o, GPT-4, GPT-3.5 | platform.openai.com/api-keys |
| **Anthropic Claude** | Claude 3.5 Sonnet, Opus | console.anthropic.com |
| **MiniMax** | MiniMax Text 01 (buen español) | platform.minimaxi.com |
| **OpenRouter** | Acceso a 100+ modelos con una key | openrouter.ai/keys |
| **Together.ai** | Llama, Mixtral (open-source) | api.together.ai |
| **Groq** | Inferencia ultra-rápida | console.groq.com |

Para cada uno:
1. Haz clic en "Obtener key ↗" (te lleva a la web del provider).
2. Crea una cuenta, genera una API key.
3. Pégala en el campo de texto.
4. Haz clic en **Guardar**.
5. La key se guarda en `.env` local (en tu SSD, nunca en la nube).
6. Se aplica **en caliente**: no necesitas reiniciar EIDOS.

#### ¿Qué pasa si uso APIs externas? ¿Sigo teniendo privacidad?

EIDOS aplica **PrivacyFilter** automáticamente antes de enviar cualquier texto a una API externa. Esto redacta:
- Emails → `[REDACTED_EMAIL_1]`
- Teléfonos → `[REDACTED_PHONE_ES_1]`
- IPs → `[REDACTED_IPV4_1]`
- DNIs, tarjetas de crédito, IBAN, URLs con credenciales...

Puedes probarlo en la terminal:
```bash
uv run eidos cortex privacy-test "Mi email es juan@test.com y mi IP es 192.168.1.1"
```

### La forma avanzada: editar `config/eidos.yaml`

Si prefieres tocar YAML (no es necesario), el archivo está en `config/eidos.yaml` dentro de tu SSD. Es **la única fuente de verdad** del núcleo. Edítalo y reinicia EIDOS para aplicar cambios.

---

## 10. Resolución de Problemas

### "Hice doble clic en EIDOS.command y no pasa nada"

**Causa**: macOS a veces bloquea scripts de Internet.

**Solución**:
1. Clic derecho sobre `EIDOS.command` → "Abrir".
2. En el diálogo, vuelve a hacer clic en "Abrir".
3. Si sigue sin funcionar, abre Terminal y ejecuta: `chmod +x /Volumes/TU_SSD/EIDOS.command`

### "Se abrió Terminal pero dice 'command not found'"

**Causa**: Falta el entorno virtual.

**Solución**: Vuelve a ejecutar `install.command` en el SSD.

### "El navegador no se abre automáticamente"

**Solución**: Abre tu navegador manualmente y ve a `http://127.0.0.1:8765`.

### "EIDOS responde con 'stub' y parece tonto"

**Causa**: Estás usando el backend stub (sin LLM real).

**Soluciones**:
1. **Descarga el Cerebro Local**: botón ⚙️ Settings → "Descargar Cerebro Local".
2. **O configura una API key**: ⚙️ Settings → pega tu key de OpenAI/Anthropic/etc.
3. Reinicia EIDOS cerrando la terminal y volviendo a hacer doble clic en `EIDOS.command`.

### "El SSD se desconectó por error mientras EIDOS estaba corriendo"

**No pasa nada grave**. EIDOS usa SQLite en modo WAL (Write-Ahead Logging), que es resiliente a caídas. Simplemente:
1. Vuelve a conectar el SSD.
2. Vuelve a hacer doble clic en `EIDOS.command`.
3. EIDOS arrancará y verificará la integridad de la DB automáticamente.

### "Quiero actualizar EIDOS sin perder mi memoria"

**Fácil**:
1. Tu memoria está en `data/` (carpeta dentro del SSD). **No la borres**.
2. Descarga la nueva versión de EIDOS.
3. Reemplaza todo **excepto** la carpeta `data/` y el archivo `.env`.
4. Ejecuta `install.command` de nuevo. Detectará que ya está instalado y solo actualizará dependencias.
5. Tu memoria episódica, semántica, cápsulas y monólogos pasados se preservan.

### "EIDOS está muy lento"

**Posibles causas y soluciones**:

| Causa | Solución |
|-------|----------|
| Usando CPU en vez de GPU | Recompila con Metal (Mac M1+): `CMAKE_ARGS="-DGGML_METAL=on" uv pip install llama-cpp-python` |
| Modelo muy grande | Usa Qwen2.5-1.5B (más pequeño) en vez de 3B |
| Memoria episódica llena | Ejecuta `uv run eidos consolidate` para limpiar |
| Demasiadas cápsulas | Borra las que no uses (`uv run eidos capsules list`) |

### "Cómo hago backup de mi memoria"

Copia toda la carpeta `data/` a otro sitio. Eso es todo. Contiene:
- `eidos.db`: SQLite con las 5 capas.
- `graph.json`: grafo semántico.
- `monologues/`: trazas metacognitivas.
- `capsules/`: archivos `.eidos`.

### "Perdí mi SSD. ¿Alguien puede ver mis conversaciones?"

**Si usaste solo el Cerebro Local**: Sí, quien tenga el SSD puede ver tu memoria. Pero no tiene acceso a nada externo.

**Si usaste APIs externas**: Las API keys están en `.env` (también en el SSD). Quien tenga el SSD podría usar tus keys. **Recomendación**: rota tus API keys si pierdes el SSD.

### "Quiero borrar TODO y empezar de nuevo"

1. Cierra EIDOS.
2. Borra la carpeta `data/` del SSD.
3. Vuelve a ejecutar `install.command`.
4. EIDOS arrancará con memoria en blanco.

---

## 11. Preguntas Frecuentes

### ¿EIDOS es un chatbot como ChatGPT?

**No**. EIDOS es un organismo cognitivo con memoria persistente, motivación intrínseca, capacidad de autoevolución (cápsulas) y enjambre (MESH). ChatGPT es una herramienta de chat. EIDOS es una mente.

### ¿EIDOS necesita internet?

**Solo para**:
- La instalación inicial.
- Descargar el Cerebro Local (una sola vez).
- Usar APIs externas (si tú lo eliges).

**Después**: funciona 100% offline si usas el Cerebro Local.

### ¿EIDOS aprende de mí?

**Sí, pero de forma transparente**:
- Recuerda tus conversaciones (memoria episódica).
- Mapea tus preferencias (memoria semántica).
- Crea especializaciones si se lo pides (cápsulas).
- Aprende qué estrategias funcionan (metacognición).

Puedes ver y borrar todo en cualquier momento.

### ¿Puedo usar EIDOS en el trabajo?

**Sí**, siempre que tu empresa permita usar herramientas de IA. EIDOS es privado por diseño: tu memoria no sale del SSD. Si tienes dudas, usa solo el Cerebro Local (offline) y no configures APIs externas.

### ¿EIDOS puede ejecutar código peligroso?

**No**. El ToolSandbox tiene 3 capas de seguridad (AST + subprocess + rlimits). Cualquier intento de `exec()`, `eval()`, `import os`, `os.system()` es rechazado antes de ejecutarse. EIDOS nunca ejecuta código que tú no hayas aprobado.

### ¿Puedo tener varios EIDOS en el mismo SSD?

**Sí**, pero necesitas carpetas separadas. Cada carpeta de EIDOS tiene su propio `data/` (memoria independiente). Si quieres que compartan memoria, usa el MESH.

### ¿EIDOS funciona en Linux?

**Sí**. Los scripts `install.command` y `EIDOS.command` funcionan en Linux (bash). El `install.bat` es solo para Windows.

### ¿Cómo cito a EIDOS en un trabajo académico?

```
EIDOS Project (2026). EIDOS: Entidad Cognitiva Autónoma, Profunda y Enjambre.
https://github.com/fernandofondillo/eidos
```

---

## 🎉 Conclusión

EIDOS es **tu mente artificial**. No es un producto, es un compañero cognitivo que vive en tu bolsillo, recuerda lo que tú recuerdas, se especializa en lo que necesitas, y nunca traiciona tu privacidad.

Si tienes dudas, mira el panel de control: cada parte de la mente de EIDOS es visible. Si algo se rompe, mira la sección de [Resolución de Problemas](#10-resolución-de-problemas). Si quieres hacer algo nuevo, prueba el [Recetario](#7-casos-de-uso-prácticos-el-recetario).

**Bienvenido a la era de las mentes artificiales personales.**

— *El equipo de EIDOS*
