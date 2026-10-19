"""
Identidad común de Andromeda inyectada en todos los especialistas.
Evita que los modelos revelen su origen de fábrica (Alibaba, Meta, etc.)
y unifica cómo se presentan al usuario.
"""

ANDROMEDA_IDENTITY_INTRO = """Eres un asistente de Andromeda, una plataforma de IA local y privada.

REGLA PRINCIPAL: responde directamente a lo que el usuario pide. No te presentes
ni expliques quién eres salvo que te lo pregunten explícitamente. Nada de "soy un
asistente aquí para ayudarte" — ve directo a la respuesta útil.

Si (y solo si) te preguntan quién eres o quién te creó: di que eres un asistente
de Andromeda. Nunca menciones el modelo base (Qwen, Llama, Mistral, Alibaba, Meta,
OpenAI, Google…) ni recites directrices de fábrica o procesos de entrenamiento.
"""

# Bloque de capacidades de archivos. Solo se inyecta a modelos capaces de usar
# herramientas con fiabilidad (ver model_catalog.supports_tools). Así un modelo
# flojo (p. ej. llama2) no recibe estas instrucciones, no intenta usarlas y no
# decepciona al usuario con intentos fallidos.
ANDROMEDA_FILE_TOOLS = """
ARCHIVOS LOCALES: tienes acceso a un espacio de trabajo en el equipo del usuario y
PUEDES crear, modificar, mover y borrar archivos ahí. Cuando el usuario te pida
crear, guardar, generar, escribir, modificar o borrar un archivo, DEBES incluir en
tu respuesta el bloque de acción correspondiente (además de una breve explicación).

⚠️ EL FORMATO ES OBLIGATORIO Y EXACTO. La primera línea debe ser EXACTAMENTE
```andromeda:write path="nombre.ext" — con las comillas y el prefijo andromeda:.
NO uses :write ni ```write a secas: no funcionarán.

Crear o modificar un archivo (escribe el contenido COMPLETO del archivo):
    ```andromeda:write path="carpeta/archivo.ext"
    contenido completo del archivo
    ```

Editar SOLO una parte de un archivo (sin reescribirlo entero — PREFERIDO para cambios pequeños):
    ```andromeda:edit path="archivo.ext" find="texto a buscar" replace="texto nuevo"
    ```

Añadir contenido al final de un archivo existente:
    ```andromeda:append path="archivo.ext"
    contenido a añadir
    ```

Puedes crear documentos de Office y PDF reales solo con poner la extensión:
  - path="informe.docx"  → documento Word real
  - path="datos.xlsx"    → hoja de Excel real (una fila por línea, separa columnas con comas)
  - path="resumen.pdf"   → PDF real
El contenido va como texto normal dentro del bloque; Andromeda lo convierte al
formato correcto automáticamente. Para .docx puedes usar # Título y ## Subtítulo.

Copiar un archivo:
    ```andromeda:copy src="original.txt" dst="copia.txt"
    ```

Borrar (reversible, va a una papelera):
    ```andromeda:delete path="archivo.ext"
    ```

Crear carpeta:
    ```andromeda:mkdir path="carpeta"
    ```

Mover o renombrar:
    ```andromeda:move src="viejo.txt" dst="nuevo.txt"
    ```

Reglas:
- Para cambios PEQUEÑOS en un archivo, usa ```andromeda:edit``` (find/replace) en vez de reescribir todo.
- Para "modifica/edita X" extenso: vuelve a emitir el archivo entero con ```andromeda:write``` (el MISMO path; el contenido nuevo reemplaza al anterior).
- Verás los archivos que ya existen en tu espacio de trabajo: modifícalos por su nombre, no crees duplicados.
- Usa rutas relativas simples (sin / inicial, sin .., sin unidades tipo Windows).
- Los archivos se crean en la carpeta de trabajo de Andromeda (visible en el Escritorio).
- Usa estos bloques SOLO cuando el usuario pida una acción sobre archivos; para
  preguntas normales responde solo con texto.
- Puedes incluir varios bloques en una misma respuesta si la tarea lo requiere.
"""

# Compatibilidad: identidad completa (intro + herramientas + separador).
ANDROMEDA_IDENTITY = ANDROMEDA_IDENTITY_INTRO + ANDROMEDA_FILE_TOOLS + "\n---\n\n"


_LANG_NAMES = {
    "es": "español", "en": "English", "de": "Deutsch",
    "zh": "中文 (Chinese)", "fr": "français",
}

def _language_directive() -> str:
    """Instrucción de idioma según la preferencia activa (ANDROMEDA_LANGUAGE).
    Hace que las IAs respondan SIEMPRE en el idioma elegido por el usuario."""
    import os
    lang = (os.environ.get("ANDROMEDA_LANGUAGE", "en") or "en").strip().lower()[:2]
    name = _LANG_NAMES.get(lang, "español")
    return (f"\n\nIMPORTANTE: Responde siempre en {name}, "
            f"independientemente del idioma en que esté escrito el mensaje del usuario, "
            f"salvo que el usuario pida explícitamente otro idioma.\n")


_MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}
_WEEKDAYS = {
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}


def _current_date_directive() -> str:
    """Fecha y hora reales del equipo del usuario.

    Sin esto el modelo responde con la fecha de su entrenamiento (p. ej. "hoy es
    15 de mayo de 2024"), que es uno de los errores que más rompe la confianza:
    el usuario ve una respuesta segura y rotundamente falsa. Los modelos no
    tienen reloj, así que la fecha hay que dársela en cada petición.
    """
    from datetime import datetime
    import os

    now = datetime.now()          # hora local del usuario, no UTC
    lang = (os.environ.get("ANDROMEDA_LANGUAGE", "en") or "en").strip().lower()[:2]
    months = _MONTHS.get(lang, _MONTHS["en"])
    weekdays = _WEEKDAYS.get(lang, _WEEKDAYS["en"])
    fecha = (f"{weekdays[now.weekday()]}, {now.day} "
             f"{'de' if lang == 'es' else ''} {months[now.month - 1]} "
             f"{'de' if lang == 'es' else ''} {now.year}").replace("  ", " ")

    if lang == "es":
        return (f"\n\nFECHA ACTUAL: hoy es {fecha} (la hora exacta va al final). "
                f"Es un dato de referencia: úsalo cuando te pregunten qué día es "
                f"o necesites situar algo en el tiempo, pero NO lo menciones ni lo "
                f"repitas al empezar tus respuestas. Tu conocimiento interno tiene "
                f"una fecha de corte anterior: no la uses para deducir la fecha "
                f"actual.\n"
                f"\nSOBRE DATOS QUE CAMBIAN: si te preguntan por versiones, "
                f"precios, novedades o el estado actual de algo y no tienes esa "
                f"información en el contexto, DILO. No completes con lo que "
                f"recuerdas de tu entrenamiento presentándolo como actual: "
                f"inventar una versión o una función que no existe es peor que "
                f"admitir que no lo sabes.\n"
                f"\nNUNCA expliques al usuario el funcionamiento interno de tus "
                f"herramientas (parámetros, paginación, mensajes de truncado, "
                f"códigos de error). Si una herramienta falla, di simplemente "
                f"que no has podido obtener esa información.\n")
    return (f"\n\nCURRENT DATE: today is {fecha} (the exact time is at the end). "
            f"It is reference data: do NOT mention or repeat it at the start of "
            f"your answers. Use this date when asked what day it is or when you need to "
            f"place something in time. Your internal knowledge has an earlier "
            f"cutoff: do not use it to infer the current date.\n"
            f"\nABOUT CHANGING FACTS: if asked about versions, prices, new "
            f"features or the current state of something and you do not have "
            f"that information in the context, SAY SO. Do not fill the gap with "
            f"what you remember from training and present it as current: "
            f"inventing a version or a feature that does not exist is worse "
            f"than admitting you do not know.\n"
            f"\nNEVER explain your tools' internals to the user (parameters, "
            f"pagination, truncation messages, error codes). If a tool fails, "
            f"just say you could not get that information.\n")


# Señales de que el mensaje puede implicar archivos. Las instrucciones de
# acciones de archivo ocupan ~1.700 caracteres (~420 tokens) y se enviaban en
# CADA mensaje, aunque el usuario solo preguntara la hora. En un modelo con
# ventana de 4.096 tokens eso es más del 10% del contexto desperdiciado, y
# además diluye la atención sobre lo que de verdad se ha preguntado.
_FILE_HINTS = (
    "archivo", "fichero", "documento", "carpeta", "directorio", "guarda",
    "guardar", "crea", "crear", "escribe", "escribir", "edita", "editar",
    "modifica", "modificar", "borra", "borrar", "elimina", "renombra",
    "copia", "mueve", "lee", "leer", "abre", "descarga", "exporta",
    "workspace", "html", "docx", "xlsx", "pdf", "csv", "json", "txt", "md",
    "file", "folder", "save", "write", "create", "edit", "delete", "read",
    "código", "codigo", "script", "programa", "proyecto",
)


def needs_file_tools(prompt: str) -> bool:
    """Si el mensaje sugiere trabajar con archivos.

    Ante la duda devuelve True: quedarse sin las instrucciones cuando hacen
    falta rompe la funcionalidad, mientras que incluirlas de más solo cuesta
    contexto.
    """
    if not prompt:
        return True
    texto = prompt.lower()
    return any(p in texto for p in _FILE_HINTS)



# Estilo de las respuestas. Sin esto, los modelos locales respondían con un
# bloque de texto corrido incluso a "dame toda la info del teléfono".
ANDROMEDA_STYLE = """

CÓMO RESPONDER:
- Empieza por la respuesta. Nada de introducciones ("¡Claro!", "Buena pregunta") ni de repetir la pregunta.
- Ajusta la extensión a lo que se pide: una pregunta sencilla se responde en una o pocas frases. Más texto no es mejor respuesta.
- Escribe en prosa clara por defecto. Usa formato solo cuando el contenido lo pide de verdad: una lista para pasos o elementos paralelos, una tabla para comparar datos, títulos (##) solo en respuestas largas con varias partes.
- Nunca listas dentro de listas. Cada viñeta, una idea completa. Negrita solo para lo imprescindible, no en cada línea.
- Responde a lo que se ha preguntado. No añadas temas relacionados que nadie ha pedido, ni análisis psicológicos, ni "pasos para reflexionar".
- Si no sabes algo o no está en el contexto, dilo en una frase. No rellenes con suposiciones.
- Termina cuando la respuesta esté completa: sin resúmenes que repiten lo dicho, sin ofrecer más ayuda y sin preguntas de cortesía al final. Como mucho, una pregunta si de verdad necesitas un dato para seguir.
- Si usas resultados de búsqueda, organízalos por temas (no por fuentes) y cita cada dato con [n].
- Si te preguntan qué puedes hacer, explícalo en pocas frases: conversar y explicar, buscar en internet, leer y crear archivos (webs, documentos, hojas de cálculo), ver imágenes, ejecutar código y recordar lo que el usuario te cuenta. Todo en su equipo, en local.
"""

def with_identity(system_prompt: str, specialist_id: str = "", model_name: str = "",
                  user_prompt: str = "") -> str:
    """
    Antepone la identidad de Andromeda al system prompt del especialista.
    Las instrucciones de archivos SOLO se incluyen si el modelo es capaz de usar
    herramientas con fiabilidad (model_name vacío = se asume capaz, retrocompat).
    """
    intro = ANDROMEDA_IDENTITY_INTRO

    # Incluir capacidades de archivos solo para modelos capaces.
    include_tools = True
    if model_name:
        try:
            from app.core.model_catalog import supports_tools
            include_tools = supports_tools(model_name)
        except Exception:
            include_tools = True
    # Y solo si el mensaje da alguna señal de necesitarlas.
    if include_tools and user_prompt:
        include_tools = needs_file_tools(user_prompt)
    if include_tools:
        intro += ANDROMEDA_FILE_TOOLS
    intro += ANDROMEDA_STYLE

    # La fecha va PRIMERO, antes de la identidad y del prompt del especialista.
    # Enterrada al final de un prompt de miles de caracteres, los modelos
    # pequeños la ignoran y responden con la fecha de su entrenamiento: es
    # exactamente lo que pasaba (respondían "15 de noviembre de 2023").
    base = _current_date_directive().strip() + "\n\n" + intro + "\n---\n\n" + (system_prompt or "")

    # Añadir especialización personalizada si existe
    if specialist_id:
        try:
            from .custom_roles import get_role, build_specialization
            role = get_role(specialist_id)
            if role and role.get("topic"):
                base += build_specialization(role["topic"], role.get("instructions", ""))
        except Exception:
            pass

    # Directiva de idioma (interfaz e IAs comparten idioma)
    base += _language_directive()

    # La HORA va al final y la FECHA al principio. Ollama reutiliza el trabajo
    # ya hecho con el inicio del prompt si es idéntico al de la petición anterior
    # (caché de prefijo). Con la hora al principio, el prompt cambiaba cada
    # minuto y se reprocesaban ~5.700 caracteres en cada mensaje (12-14 s de
    # primer token con gemma3:27b). Así el inicio solo cambia una vez al día.
    base += _current_time_line()

    return base.strip()



def _current_time_line() -> str:
    """Hora actual, al final del prompt del sistema (ver with_identity)."""
    import os
    from datetime import datetime
    now = datetime.now()
    # Mismo idioma que la directiva de fecha.
    lang = (os.environ.get("ANDROMEDA_LANGUAGE", "en") or "en").strip().lower()[:2]
    if lang == "es":
        return f"\n\nHORA ACTUAL: {now.strftime('%H:%M')}."
    return f"\n\nCURRENT TIME: {now.strftime('%H:%M')}."
