# Pendientes y mejoras planificadas

Este archivo lista las cosas que están **planificadas** pero todavía no
implementadas. Se van tachando o moviendo a `CHANGELOG.md` a medida que se
completan.

Última actualización: 2026-10-07

---

## 🗂️  Estructura de archivos en Google Drive (referencia)
Mi unidad/
└── sistema_asistencia/
├── base_datos/
│ ├── Asistencia CFL (produccion) ← planilla activa real
│ ├── Asistencia CFL (desarrollo) ← copia para desarrollo
│ ├── backups/ ← backups automáticos aquí
│ └── archivos_historicos/ ← datos viejos movidos aquí
└── ...


**Compartir la carpeta `base_datos/` con la cuenta de servicio (permiso
Editor) para que todos los archivos nuevos hereden el permiso
automáticamente.**

---

## 🔴 Alta prioridad

### Importación de inscripciones desde Google Forms
Contexto: los alumnos se preinscriben a través de un Google Forms. Cada
curso tiene su propio Forms (y su propia planilla de respuestas asociada).
El Forms se cierra cuando el cupo se llena. En el primer día de clases
cada alumno confirma su vacante trayendo la copia de DNI.

- [ ] Módulo `/admin/importar` que lea la planilla de respuestas del Forms.
- [ ] Preview antes de confirmar (mostrar qué alumnos se van a crear).
- [ ] Detección de duplicados:
  - DNI duplicado dentro del propio Forms.
  - DNI ya existente en el mismo curso.
  - DNI existente en otros cursos (permitir, solo avisar).
- [ ] Checkbox por fila para elegir cuáles importar.
- [ ] Alta masiva a hoja `Alumnos` con estado `A` y `ORIGEN = "IMPORT"`.
- [ ] `FECHA_INSCRIPCION` = "Marca temporal" del Forms.
- [ ] Pantalla de resultado ("N importados, M salteados por duplicado").
- [ ] Mensaje recordatorio: "No olvides dar de baja a los que no
      confirmaron su vacante el primer día de clases".

### Backup antes de cada acción crítica
- [ ] Función `hacer_backup()` en `services/backup.py`.
- [ ] La exporta a `sistema_asistencia/base_datos/backups/` en Drive
      con nombre `backup_AAAA-MM-DD_HH-MM-SS.xlsx`.
- [ ] Se ejecuta automáticamente ANTES de importaciones o cambios masivos.
- [ ] Botón manual "Hacer backup ahora" en `/configuracion`.
- [ ] Rotación: mantener últimos 30 backups, borrar los más viejos.
- [ ] (Opcional) Backup diario automático con el Programador de Tareas
      de Windows.

### Ampliar hoja `Alumnos` con datos del Forms
Contexto: hoy `Alumnos` solo tiene DNI, Apellidos, Nombres, Curso, Cuat,
Año y Estado. Los datos completos del alumno están en la planilla del Forms
pero no se guardan.

- [ ] Agregar columnas a `Alumnos`:
      `FECHA_NAC`, `GENERO`, `NACIONALIDAD`, `PROVINCIA_NAC`, `DOMICILIO`,
      `BARRIO`, `TELEFONO`, `EMAIL`, `CUIL`, `ESTUDIOS`, `ESTADO_LABORAL`,
      `DISCAPACIDAD`, `TELEFONO_EMERGENCIA`, `FECHA_INSCRIPCION`, `ORIGEN`,
      `OBSERVACIONES`.
- [ ] Agregar `FECHA_INSCRIPCION` para altas manuales (fecha del sistema).
- [ ] `ORIGEN` = "IMPORT" | "MANUAL" | "ESPERA".

---

## 🔴 Alta prioridad

### Gestión de cursos (ABM completo)
Contexto: hoy los cursos se cargan y editan directamente en Google Sheets.
No hay pantalla en la app para que un operador pueda crear, editar o dar de
baja un curso. Cada cambio requiere abrir Sheets a mano, con riesgo de
romper fórmulas o columnas.

Un curso tiene: ID_CURSO, CURSO (nombre largo), NICK (nombre corto),
TURNO (M/T/V), LU..VI (días de clase), INICIO, FIN, PROFESOR,
INICIO_CICLO, y posiblemente CUPO (si se agrega en el futuro).

- [ ] Módulo `/admin/cursos` con listado filtrable:
      - Filtro por turno (Mañana/Tarde/Vespertino).
      - Filtro por estado activo/inactivo (si se agrega columna).
      - Búsqueda por nombre o nick.
- [ ] Alta de curso nuevo:
      - Formulario con todos los campos.
      - Validaciones: ID único, días de la semana al menos uno,
        INICIO < FIN, INICIO_CICLO con formato de fecha.
      - Al crear, se agrega la fila a la hoja `Cursos` con los mismos
        encabezados.
- [ ] Edición de curso existente:
      - Editar todos los campos menos ID_CURSO (es la clave).
      - Verificar que no rompa las relaciones con `Alumnos` y `Asistencias`
        (el ID_CURSO se mantiene).
- [ ] Baja / reactivación de curso:
      - ¿Qué significa dar de baja un curso?
        - Opción A: nueva columna `ESTADO` en `Cursos` (A/B), igual que
          en `Alumnos`. Los cursos dados de baja no aparecen en las
          pantallas de toma de lista ni en el import.
        - Opción B: borrar la fila (peligroso, rompe referencias).
        - **Recomendado: Opción A** (consistente con `Alumnos`).
- [ ] Duplicar curso (útil para arrancar un cuatrimestre nuevo copiando
      la estructura de un curso viejo, cambiando fechas y cuatrimestre).
- [ ] Validaciones antes de dar de baja un curso:
      - ¿Tiene alumnos activos? Avisar y permitir forzar.
      - ¿Tiene asistencias cargadas? Preservar (no se borran).
- [ ] Documentación en la pantalla: explicar qué significa cada columna
      (para que el operador sepa qué llenar).

Riesgos a manejar:
- Al crear/editar un curso, invalidar el caché de `Cursos` para que la
  app lo vea al instante.
- Al cambiar `PROFESOR` de un curso, verificar que las `Ausencias_Profesores`
  ya cargadas mantengan el profesor viejo (histórico) o se actualicen
  (no hay una respuesta única, evaluar).
- Al cambiar días/horarios, las asistencias viejas no se recalculan
  (el porcentaje se calcula con los días actuales del curso, no con los
  de la fecha de la asistencia).


## 🟡 Media prioridad

### Lista de espera
Contexto: cuando un curso se llena, hay gente que queda afuera y se anota
en una lista de espera en papel. Hoy no hay forma de gestionarla desde la app.

- [ ] Hoja nueva `Lista_Espera` con datos mínimos del alumno.
- [ ] Pantalla `/admin/lista_espera` para ver, agregar y editar.
- [ ] Botón "Pasar a Alumnos" cuando se libera un cupo.
- [ ] Columna `CUPO` en hoja `Cursos` (opcional).
- [ ] Al importar un Forms, si el curso está lleno, ofrecer mandar los
      sobrantes a la lista de espera.

### Archivar ciclo lectivo
Contexto: la planilla activa va a crecer indefinidamente. Con el volumen
actual no hay problema en tamaño, pero sí en tiempo de lectura y cuota de
API a medida que pasen los años.

- [ ] Módulo `/admin/archivar` que mueva filas viejas de `Asistencias`
      a un archivo en `sistema_asistencia/base_datos/archivos_historicos/`.
- [ ] Nomenclatura: `Asistencias AAAA-NC.xlsx` (ej: `Asistencias 2026-1C.xlsx`).
- [ ] Vistas de consulta histórica que lean el archivo.
- [ ] Nota en la planilla activa indicando dónde está el archivo.

### Documentación del proyecto
- [ ] README.md con:
      - Qué es la app y para quién.
      - Cómo se instala (venv, dependencias, credenciales).
      - Cómo se configura (`config.py`, qué cambiar).
      - Cómo se despliega (`update_server.bat`).
      - Estructura de las hojas de Google Sheets (qué es cada columna).
      - Estructura de la carpeta de Drive (`sistema_asistencia/`).
- [ ] Comentario de cabecera en cada archivo de `routes/` y `services/`.
- [ ] Guía rápida para nuevos colaboradores.

### Auditoría y trazabilidad (sin login)
- [ ] Log de cambios importantes en hoja `Auditoria` (o archivo local).
- [ ] Guardar "qué" y "cuándo" + IP. Sin login, no sabemos "quién".
- [ ] Útil para: bajas, reactivaciones, cambios de estado, borrados.

---

## 🔵 Baja prioridad (a futuro)

### Login por usuario y roles
- [ ] Sistema de login con roles (admin, profesor, consulta).
- [ ] Requiere rediseño importante. Reevaluar en 2027.

### Migrar a base de datos real
- [ ] Solo si Google Sheets se vuelve inviable (>500k filas activas o
      tiempos de respuesta > 2 seg con caché activo).
- [ ] Candidato: SQLite.

### Mejoras varias
- [ ] `config.py.example` + `.gitignore` con `config.py`.
- [ ] Caché inteligente: invalidar solo la parte afectada.
- [ ] Endpoint `/health` para monitoreo.

---

## ✅ Completados recientemente

### v1.1.0 (2026-10-01)
- Admin de alumnos (`/admin/alumnos`).
- Filtros por estado (activos / bajas / todos).
- Sistema de baja/reactivación con contraseña.
- Reactivación automática al marcar presente a un alumno dado de baja.
- Caché en disco (`instance/cache_sheets.json`).
- Pantalla `/configuracion`.
- Modo oscuro y barra superior con versión.

### v1.2.0 (en preparación, 2026-10-07)
- Separación dev/prod por variable `ENTORNO`.
- `SPREADSHEET_ID_PRODUCCION` y `SPREADSHEET_ID_DESARROLLO`.
- `SPREADSHEET_NOMBRE_PRODUCCION` y `SPREADSHEET_NOMBRE_DESARROLLO`.
- Pantalla `/configuracion` muestra el entorno activo.
- Mensaje de error mejorado cuando falta permiso en la planilla.
- `update_server.bat` con exclusiones ampliadas.
- `config.py` ya no depende de `python-dotenv`.
- Planillas renombradas sin año (viven para siempre).
- Estructura de carpetas en Drive: `sistema_asistencia/base_datos/`.