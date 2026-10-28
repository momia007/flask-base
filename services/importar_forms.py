# services/importar_forms.py
"""
Lógica de lectura y validación de planillas de Google Forms.

El módulo de importación (routes/admin_importar.py) usa estas funciones
para leer las respuestas del Forms, normalizarlas al formato de la hoja
`Alumnos`, y validar cada fila antes de importarla.

Funciones principales:
  - extraer_id_planilla(url_o_id): acepta una URL de Sheets o un ID pelado.
  - leer_respuestas_forms(id_planilla): lee los registros crudos.
  - detectar_tipo_forms(headers): detecta si el Forms tiene columna de
    certificación previa.
  - normalizar_fila_forms(fila_cruda, headers): convierte una fila cruda
    del Forms en un diccionario con las claves de `Alumnos`.
  - analizar_planilla(id_planilla, curso_id, cuatrimestre, anio, alumnos_existentes):
    combina todo y devuelve el preview.
"""

import re
from datetime import datetime

from services.sheets import client
from services.porcentaje_asistencia import normalizar_claves


# -----------------------------------------------------------------------------
#  Helpers de parseo
# -----------------------------------------------------------------------------

def extraer_id_planilla(url_o_id):
    """Acepta una URL de Google Sheets o un ID pelado. Devuelve solo el ID."""
    if not url_o_id:
        return ""
    texto = str(url_o_id).strip()

    # Si es una URL, buscar el patrón /d/XXXXX/
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", texto)
    if match:
        return match.group(1)

    # Si no es URL, asumir que es el ID directo
    return texto


def _limpiar_dni(valor):
    """Deja solo dígitos del DNI. Acepta 41179917.0 (float) o '41.179.917'."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        valor = int(valor) if valor.is_integer() else valor
    return re.sub(r"\D", "", str(valor))


def _limpiar_cuil(valor):
    """Deja solo dígitos del CUIL (11 dígitos esperados)."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        valor = int(valor) if valor.is_integer() else valor
    return re.sub(r"\D", "", str(valor))


def _limpiar_telefono(valor):
    """Deja solo dígitos del teléfono. Acepta floats."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        valor = int(valor) if valor.is_integer() else valor
    return re.sub(r"\D", "", str(valor))


def _parsear_fecha(valor):
    """
    Acepta fechas en varios formatos y devuelve un objeto date.
    Formatos soportados:
      - datetime object (Google Sheets a veces lo devuelve así)
      - 'aaaa-mm-dd HH:MM:SS.microsegundos'
      - 'aaaa-mm-dd HH:MM:SS'
      - 'aaaa-mm-dd'
      - 'dd/mm/aaaa HH:MM:SS'  ← el que devuelve Google Sheets en español
      - 'dd/mm/aaaa HH:MM'
      - 'dd/mm/aaaa'
      - 'd/m/aaaa H:MM:SS'     ← día/mes/hora sin cero adelante
      - 'd/m/aaaa'
    Devuelve None si no se puede parsear.
    """
    if valor is None or valor == "":
        return None

    if isinstance(valor, datetime):
        return valor.date()

    # Si es un número (timestamp)
    if isinstance(valor, (int, float)):
        try:
            return datetime.fromtimestamp(valor).date()
        except Exception:
            pass

    s = str(valor).strip()

    formatos = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",   # 21/8/2026 9:01:48
        "%d/%m/%Y %H:%M",      # 21/8/2026 9:01
        "%d/%m/%Y",            # 21/8/2026
        "%d/%m/%y %H:%M:%S",   # 21/8/26 9:01:48
        "%d/%m/%y",            # 21/8/26
    )

    for fmt in formatos:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Último intento: si tiene hora pero no segundos ("21/8/2026 9:01")
    # o si tiene microsegundos raros, cortar y volver a intentar con solo la fecha
    try:
        solo_fecha = s.split(" ")[0]
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(solo_fecha, fmt).date()
            except ValueError:
                continue
    except Exception:
        pass

    return None


def _formatear_fecha(fecha_obj):
    """Devuelve la fecha en formato dd/mm/aaaa."""
    if fecha_obj is None:
        return ""
    return fecha_obj.strftime("%d/%m/%Y")


# -----------------------------------------------------------------------------
#  Lectura de la planilla del Forms
# -----------------------------------------------------------------------------

def leer_respuestas_forms(id_planilla):
    """
    Lee la planilla del Forms y devuelve:
      - headers: lista de encabezados (strings).
      - filas: lista de diccionarios {encabezado: valor}.

    Ojo: usa la PRIMERA pestaña de la planilla (que es donde Google Forms
    escribe por defecto).
    """
    if not id_planilla:
        raise ValueError("Falta el ID de la planilla del Forms.")

    try:
        planilla = client.open_by_key(id_planilla)
    except Exception as e:
        raise RuntimeError(
            f"No se pudo abrir la planilla del Forms (ID: {id_planilla}). "
            f"Verificá que esté compartida con la cuenta de servicio. Error: {e}"
        ) from e

    hoja = planilla.sheet1
    registros = hoja.get_all_records()

    if registros:
        headers = list(registros[0].keys())
    else:
        # Si no hay filas de datos, al menos leer los encabezados
        valores = hoja.get_all_values()
        headers = valores[0] if valores else []

    return headers, registros


# -----------------------------------------------------------------------------
#  Detección de tipo de Forms
# -----------------------------------------------------------------------------

def detectar_columna_certificacion(headers):
    """
    Busca una columna que contenga 'CERTIFICACION' en el encabezado.
    Si la encuentra, devuelve el nombre exacto de la columna.
    Si no, devuelve None.
    """
    for h in headers:
        if "CERTIFICACION" in str(h).upper():
            return h
    return None


# -----------------------------------------------------------------------------
#  Normalización de una fila del Forms al formato de `Alumnos`
# -----------------------------------------------------------------------------

def normalizar_fila_forms(fila_cruda, headers, columna_certificacion=None):
    """
    Convierte una fila cruda del Forms (dict con los encabezados originales)
    en un dict con las claves que espera la hoja `Alumnos`.

    Devuelve un dict con:
      - apellidos, nombres, dni, cuil, fecha_nac, genero, nacionalidad,
        provincia_nac, domicilio, barrio, telefono, email, estudios,
        estado_laboral, discapacidad, telefono_emergencia,
        fecha_inscripcion (todas como string, ya normalizadas).
      - certificacion_valor: el valor de la columna de certificación (si existe).
    """
    # Normalizamos los encabezados para hacer el match más fácil
    fila_norm = normalizar_claves(fila_cruda)

    def buscar(*palabras_clave):
        """Busca la primera columna cuyo encabezado contenga alguna de las
        palabras clave (case-insensitive). Devuelve el valor o ''."""
        for h_norm, valor in fila_norm.items():
            for pc in palabras_clave:
                if pc in h_norm:
                    return valor
        return ""

    # --- Campos base ---
    apellidos = str(buscar("APELLIDO")).strip()
    nombres = str(buscar("NOMBRE") if "NOMBRE" in str(buscar("NOMBRE")) else buscar("NOMBRES")).strip()

    # OJO: "NOMBRE" matchea con "NOMBRES" y con "APELLIDO/S", así que vamos
    # más despacio. Usamos un approach más cuidadoso:
    apellidos = ""
    nombres = ""
    for h_norm, valor in fila_norm.items():
        if "APELLIDO" in h_norm and not apellidos:
            apellidos = str(valor).strip()
        elif ("NOMBRE" in h_norm or "NOMBRES" in h_norm) and "APELLIDO" not in h_norm and not nombres:
            nombres = str(valor).strip()

    dni = _limpiar_dni(buscar("DNI"))
    cuil = _limpiar_cuil(buscar("CUIL"))
    fecha_nac_obj = _parsear_fecha(buscar("FECHA DE NAC", "NACIMIENTO"))
    fecha_nac = _formatear_fecha(fecha_nac_obj)
    genero = str(buscar("GENERO", "GÉNERO")).strip()
    nacionalidad = str(buscar("NACIONALIDAD")).strip().upper()
    provincia_nac = str(buscar("PROVINCIA")).strip().upper()
    domicilio = str(buscar("DOMICILIO")).strip().upper()
    barrio = str(buscar("BARRIO")).strip().upper()
    telefono = _limpiar_telefono(buscar("TELEFONO PERSONAL", "TELÉFONO PERSONAL", "TELEFONO"))
    email = str(buscar("CORREO", "EMAIL")).strip().lower()
    estudios = str(buscar("ESTUDIOS")).strip()
    estado_laboral = str(buscar("ESTADO LABORAL")).strip()
    discapacidad = str(buscar("DISCAPACIDAD")).strip()
    telefono_emergencia = _limpiar_telefono(buscar("EMERGENCIA"))
    fecha_inscripcion_obj = _parsear_fecha(buscar("MARCA TEMPORAL", "MARCA"))
    fecha_inscripcion = _formatear_fecha(fecha_inscripcion_obj)

    # Certificación (solo si hay columna)
    certificacion_valor = ""
    if columna_certificacion:
        certificacion_valor = str(fila_cruda.get(columna_certificacion, "")).strip().upper()

    return {
        "apellidos": apellidos.upper(),
        "nombres": nombres.upper(),
        "dni": dni,
        "cuil": cuil,
        "fecha_nac": fecha_nac,
        "genero": genero,
        "nacionalidad": nacionalidad,
        "provincia_nac": provincia_nac,
        "domicilio": domicilio,
        "barrio": barrio,
        "telefono": telefono,
        "email": email,
        "estudios": estudios,
        "estado_laboral": estado_laboral,
        "discapacidad": discapacidad,
        "telefono_emergencia": telefono_emergencia,
        "fecha_inscripcion": fecha_inscripcion,
        "certificacion_valor": certificacion_valor,
    }


# -----------------------------------------------------------------------------
#  Validación de una fila normalizada
# -----------------------------------------------------------------------------

def _validar_edad_minima(fecha_nac_str, cuatrimestre, anio):
    """
    Valida que el alumno tenga 18 años al cierre del cuatrimestre.
    Mismo criterio que en admin_alumnos.py.
    Devuelve (True, "") o (False, mensaje).
    """
    if not fecha_nac_str or not cuatrimestre or not anio:
        return (False, "Falta fecha de nacimiento, cuatrimestre o año.")

    try:
        fecha_nac = datetime.strptime(fecha_nac_str, "%d/%m/%Y").date()
    except Exception:
        return (False, "Fecha de nacimiento inválida.")

    anio_actual = datetime.now().year
    if fecha_nac.year < 1900 or fecha_nac.year > anio_actual:
        return (False, "Año de nacimiento fuera de rango.")

    try:
        anio_int = int(anio)
    except Exception:
        return (False, "Año inválido.")

    if str(cuatrimestre) == "1":
        fecha_cierre = datetime(anio_int, 6, 30).date()
    elif str(cuatrimestre) == "2":
        fecha_cierre = datetime(anio_int, 11, 30).date()
    else:
        return (False, "Cuatrimestre inválido.")

    edad_al_cierre = (
        fecha_cierre.year - fecha_nac.year
        - ((fecha_cierre.month, fecha_cierre.day) < (fecha_nac.month, fecha_nac.day))
    )
    if edad_al_cierre >= 18:
        return (True, "")
    return (False, f"No cumple la edad mínima (tendría {edad_al_cierre} años al cierre).")


def validar_fila(normalizada, cuatrimestre, anio, alumnos_existentes, dnies_en_forms):
    """
    Valida una fila normalizada.

    Parámetros:
      - normalizada: dict devuelto por normalizar_fila_forms.
      - cuatrimestre, anio: strings con el cuatrimestre y año destino.
      - alumnos_existentes: set de DNIs que YA existen en el curso destino.
      - dnies_en_forms: dict {dni: cantidad_de_apariciones} para detectar
        duplicados dentro del propio Forms.

    Devuelve un dict:
      - errores: lista de strings (si hay, la fila no se puede importar).
      - advertencias: lista de strings (si hay, la fila se puede importar
        pero conviene revisarla).
    """
    errores = []
    advertencias = []

    # --- DNI ---
    if not normalizada["dni"]:
        errores.append("Falta el DNI.")
    elif len(normalizada["dni"]) != 8:
        errores.append(f"El DNI '{normalizada['dni']}' no tiene 8 dígitos.")

    # --- Apellidos y nombres ---
    if not normalizada["apellidos"]:
        errores.append("Falta el apellido.")
    if not normalizada["nombres"]:
        errores.append("Falta el nombre.")

    # --- CUIL ---
    if normalizada["cuil"] and len(normalizada["cuil"]) != 11:
        advertencias.append(f"El CUIL '{normalizada['cuil']}' no tiene 11 dígitos.")

    # --- Fecha de nacimiento y edad ---
    cumple, msg = _validar_edad_minima(normalizada["fecha_nac"], cuatrimestre, anio)
    if not cumple:
        errores.append(msg)

    # --- Certificación ---
    if normalizada.get("certificacion_valor"):
        if normalizada["certificacion_valor"] not in ("SI", "SÍ"):
            errores.append(
                f"El alumno no tiene certificación previa (valor: '{normalizada['certificacion_valor']}')."
            )

    # --- Duplicado dentro del propio Forms ---
    dni = normalizada["dni"]
    if dni and dnies_en_forms.get(dni, 0) > 1:
        advertencias.append(
            f"El DNI {dni} aparece {dnies_en_forms[dni]} veces en la planilla del Forms."
        )

    # --- Duplicado en el curso destino ---
    if dni and dni in alumnos_existentes:
        advertencias.append("Este DNI ya existe en el curso destino.")

    return {
        "errores": errores,
        "advertencias": advertencias,
    }


# -----------------------------------------------------------------------------
#  Función principal: analizar la planilla y devolver el preview
# -----------------------------------------------------------------------------

def analizar_planilla(id_planilla, curso_id, cuatrimestre, anio, alumnos_existentes):
    """
    Lee la planilla del Forms, normaliza y valida cada fila.

    Devuelve un dict con:
      - headers: lista de encabezados del Forms.
      - filas: lista de dicts, uno por cada alumno del Forms. Cada uno tiene:
          - datos: el dict normalizado (con las claves de Alumnos).
          - errores: lista de strings.
          - advertencias: lista de strings.
          - valido: True si se puede importar (sin errores).
          - importar: True por defecto si es válido, False si no.
      - total: cantidad total de filas.
      - validos: cantidad de filas válidas.
      - invalidos: cantidad de filas inválidas.
    """
    headers, registros = leer_respuestas_forms(id_planilla)

    columna_certificacion = detectar_columna_certificacion(headers)

    # Contar cuántas veces aparece cada DNI (para detectar duplicados dentro del Forms)
    dnies_en_forms = {}
    for reg in registros:
        norm = normalizar_fila_forms(reg, headers, columna_certificacion)
        dni = norm["dni"]
        if dni:
            dnies_en_forms[dni] = dnies_en_forms.get(dni, 0) + 1

    # Procesar cada fila
    filas = []
    for i, reg in enumerate(registros, start=2):  # start=2 porque la fila 1 son los headers
        norm = normalizar_fila_forms(reg, headers, columna_certificacion)
        validacion = validar_fila(
            norm, cuatrimestre, anio, alumnos_existentes, dnies_en_forms
        )

        valido = len(validacion["errores"]) == 0

        filas.append({
            "nro_fila": i,
            "datos": norm,
            "errores": validacion["errores"],
            "advertencias": validacion["advertencias"],
            "valido": valido,
            "importar": valido,  # por defecto: importar si es válido
        })

    validos = sum(1 for f in filas if f["valido"])

    return {
        "headers": headers,
        "columna_certificacion": columna_certificacion,
        "filas": filas,
        "total": len(filas),
        "validos": validos,
        "invalidos": len(filas) - validos,
    }

# -----------------------------------------------------------------------------
#  Guardado y lectura del log de importaciones
# -----------------------------------------------------------------------------

def guardar_log_importacion(id_import, id_planilla, curso_id, curso_nombre,
                             cuatrimestre, anio, total_form, importados,
                             pendientes, nombre_backup):
    """Guarda la cabecera de la importación en la hoja 'Importaciones'."""
    from services.sheets import abrir_hoja
    hoja = abrir_hoja("Importaciones")

    fecha_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    estado = "COMPLETADO" if pendientes == 0 else "CON PENDIENTES"

    hoja.append_row([
        id_import, fecha_hora, id_planilla, curso_id, curso_nombre,
        cuatrimestre, anio, total_form, importados, pendientes,
        nombre_backup, estado
    ])


def guardar_log_pendientes(id_import, filas_pendientes):
    """Guarda las filas pendientes en la hoja 'Importaciones_Pendientes'."""
    from services.sheets import abrir_hoja
    if not filas_pendientes:
        return

    hoja = abrir_hoja("Importaciones_Pendientes")

    for fila in filas_pendientes:
        d = fila["datos"]
        hoja.append_row([
            id_import,
            fila["nro_fila"],
            d["dni"],
            d["apellidos"],
            d["nombres"],
            d["fecha_nac"],
            d["genero"],
            d["nacionalidad"],
            d["provincia_nac"],
            d["domicilio"],
            d["barrio"],
            d["telefono"],
            d["email"],
            d["cuil"],
            d["estudios"],
            d["estado_laboral"],
            d["discapacidad"],
            d["telefono_emergencia"],
            d["fecha_inscripcion"],
            " | ".join(fila["errores"]),
            " | ".join(fila["advertencias"])
        ])