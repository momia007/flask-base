## Cálculo del porcentaje de asistencia

El porcentaje de asistencia de cada alumno se calcula día por día, no simplemente
contando registros sueltos. La lógica es la siguiente:

### 1. Días totales considerados (denominador)

Se recorre, día por día, el rango que va desde **`INICIO_CICLO`** del curso
(columna en la hoja `Cursos`) hasta una **fecha tope**, que es la más chica entre:

- la fecha de hoy, o
- el último día en el que se tomó asistencia para ese curso (última fecha con
  algún registro en la hoja `Asistencias` para ese `ID_CURSO`).

Usar esta fecha tope (en vez de "hoy" a secas) es lo que evita que el porcentaje
siga bajando artificialmente después de que el curso terminó y ya no se carga
más asistencia: una vez que el curso finaliza, la fecha tope queda "congelada"
en el último día real de clase.

De ese rango de días solo se cuentan los que:

- Coinciden con un día de la semana en que el curso dicta clase, según las
  columnas `LU`, `MA`, `MI`, `JU`, `VI` de la hoja `Cursos` (cada curso tiene su
  propio patrón semanal).
- **No** son feriado (hoja `Feriados`). Los feriados se descuentan del total:
  ese día no cuenta para nadie, ni a favor ni en contra.

### 2. Días asistidos (numerador)

Un día del rango anterior cuenta como "asistido" para un alumno si se cumple
**alguna** de estas dos condiciones:

- El alumno tiene un registro con estado `P` (presente) o `J` (justificado) ese
  día, en la hoja `Asistencias`.
- Ese día el profesor del curso estuvo ausente (hoja `Ausencias_Profesores`,
  filtrado por `ID_CURSO` y fecha).

**Criterio de las ausencias de profesor:** a diferencia de los feriados, un día
de ausencia del profesor **no se resta del total de días** — sigue contando
como un día de clase programado. En cambio, se le da al alumno el beneficio de
la duda y **se cuenta como si hubiera asistido**, ya que no es su responsabilidad
que el profesor no haya podido dar clase, y no hay forma de saber si el alumno
habría asistido o no ese día.

Cada día se evalúa una sola vez: si por algún motivo coinciden ambas
condiciones el mismo día (por ejemplo, el alumno tiene un `P` cargado y además
ese día el profesor figura ausente), el día suma una sola vez al numerador, no
dos.

### 3. Fórmula final

```
Porcentaje = (días asistidos / días totales considerados) × 100
```

### 4. Casos sin datos suficientes

El cálculo devuelve **"N/D"** (no disponible), en vez de 0%, cuando:

- El curso todavía no tiene `INICIO_CICLO` cargado en la hoja `Cursos`.
- El curso todavía no tiene ningún día de asistencia tomado (recién arrancó).
- El alumno no tiene DNI cargado (se muestra "Sin DNI" en ese caso particular).

Esto evita mostrar un 0% engañoso quen en realidad significa "todavía no hay
información para calcular nada", que es una situación distinta a "el alumno
faltó siempre".
