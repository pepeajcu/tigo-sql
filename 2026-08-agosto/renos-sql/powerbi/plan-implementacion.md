# Plan de implementación — journey de renovaciones en Power BI

Checklist paso a paso para construir el modelo siguiendo `guia-dax-powerbi.md`. Cada fase es
chica y verificable antes de pasar a la siguiente — si algo no cuadra en una fase, no tiene caso
seguir a la próxima.

Marca cada casilla según avances (`- [ ]` → `- [x]`).

---

## Fase 0 — Preparación

- [ ] Power BI Desktop abierto, archivo nuevo guardado como `.pbix` dentro de `powerbi/` (por
      ejemplo `powerbi/renovaciones.pbix`).
- [ ] Confirmar que los 4 CSV siguen en `powerbi/produ/` y `powerbi/pruebas/` con esos nombres
      exactos (sección "Archivos de origen" de la guía).
- [ ] Tener a mano `detalle_atribucion.csv`, `paso_journey.csv` y `rutas.csv` que ya generó el
      script de Python para cada ola (`dataset/produ/output/produ/...`) — se usan como referencia
      para validar que el modelo de Power BI da los mismos números.

---

## Fase 1 — Funciones de limpieza (guía, sección 1) ✅ 2026-08-18

- [x] Crear consulta en blanco `fx_Msisdn`, pegar el código, verificar que Power BI la reconoce
      como función (ícono de función en el panel de consultas).
- [x] Crear `fx_Fecha` igual.
- [x] Crear `fx_LimpiarEnvios` y `fx_LimpiarReno`.
- [x] Probar `fx_LimpiarEnvios` a mano con una tabla chica de ejemplo (Introducir datos con 2-3
      filas) para confirmar que limpia msisdn a 8 dígitos y fecha a `date` antes de usarla contra
      un CSV real.

**Checkpoint:** las 4 funciones existen y no marcan error al guardar.

---

## Fase 2 — Carga y unificación (guía, sección 2) ✅ 2026-08-18

- [x] Cargar `powerbi/produ/envios_produ.csv` → consulta `Envios_Produ` → aplicar
      `fx_LimpiarEnvios(..., "Produccion")`.
- [x] Cargar `powerbi/pruebas/envios_pruebas.csv` → `Envios_Pruebas` → `fx_LimpiarEnvios(..., "Pruebas")`.
- [x] Cargar `powerbi/produ/reno_produ.csv` → `Reno_Produ` → `fx_LimpiarReno(..., "Produccion")`.
- [x] Cargar `powerbi/pruebas/reno_pruebas.csv` → `Reno_Pruebas` → `fx_LimpiarReno(..., "Pruebas")`.
- [x] Crear consultas finales `Envios` = `Table.Combine({Envios_Produ, Envios_Pruebas})` y
      `Renovaciones` = `Table.Combine({Reno_Produ, Reno_Pruebas})`.
- [x] Deshabilitar carga de las 4 consultas intermedias (`Envios_Produ`, `Envios_Pruebas`,
      `Reno_Produ`, `Reno_Pruebas`) — solo `Envios` y `Renovaciones` se cargan al modelo.

**Checkpoint — validado:** conteo por `Dataset` en Power BI vs. limpieza replicada de forma
independiente en Python contra los mismos 4 CSV — coincide exacto:

| | Power BI | Validación independiente |
|---|---|---|
| Envíos × Producción | 6 567 | 6 567 ✅ |
| Envíos × Pruebas | 3 017 | 3 017 ✅ |
| Renovaciones × Producción | 7 378 | 7 378 ✅ |
| Renovaciones × Pruebas | 11 761 | 11 761 ✅ |

---

## Fase 3 — Ventanas de atribución (guía, sección 3)

- [ ] Crear la consulta `Ventanas` con el código de la sección 3.
- [ ] Deshabilitar su carga al modelo si solo la vas a usar como paso intermedio (no se referencia
      directo en DAX, solo conceptualmente — la lógica real vive dentro de `Atribucion`, sección 4,
      que no depende de esta consulta. Puedes omitir `Ventanas` del todo si vas directo a la Fase 4;
      la dejo en la guía como explicación del concepto, no es un prerrequisito técnico).

**Checkpoint:** ninguno estricto — es opcional/ilustrativa. Sáltala si quieres ir directo a Fase 4.

---

## Fase 4 — Atribución last-touch (guía, sección 4) — la fase crítica ✅ 2026-08-18

- [x] Crear la consulta `Atribucion` con el código completo de la sección 4.
- [x] Cerrar y aplicar. Verificar que no tira error de sintaxis M.
- [x] Contar filas totales de `Atribucion` agrupado por `Dataset`.

**Checkpoint — validado:** algoritmo completo (ventanas + último toque + desempate por canal)
replicado de forma independiente en Python contra los mismos CSV — coincide exacto:

| | Power BI | Validación independiente |
|---|---|---|
| Atribuidas × Producción | 128 | 128 ✅ |
| Atribuidas × Pruebas | 55 | 55 ✅ |

Nota: la tasa de atribución es baja a propósito (128/7 378 ≈ 1.7 %, 55/11 761 ≈ 0.5 %) — la mayoría
de las renovaciones no cayó dentro de los 7 días de vigencia de algún envío de esa persona. No es un
error del modelo, es el comportamiento real de la ventana de atribución sobre esta data.

---

## Fase 5 — Orden del journey: `paso_idx` / `dia_rel` (guía, sección 5) ✅ 2026-08-18

- [x] Crear la consulta `Pasos` (ahora cargada al modelo, con columna `ClavePaso`).
- [x] Relación `Pasos[ClavePaso]` (1) → `Envios[ClavePaso]` (muchos) en el modelo — **no** merge
      directo, por dependencia circular (`Pasos` depende de `Envios`; ver nota en la guía, sección 5).
- [x] Merge `Atribucion` + `Pasos` (sí es válido, sin ciclo) trayendo `dia_cero`, `paso_idx`, `dia_rel`.
- [x] `dia_rel_conv` en `Atribucion` = `Duration.Days([fecha_conv] - [Pasos.dia_cero])`.

**Checkpoint — validado:** máximo `paso_idx` en `Pasos` por `Dataset` vs. cantidad de
`canvas_step_nm` distintos calculada independientemente sobre los CSV — coincide exacto:

| | Power BI | Validación independiente |
|---|---|---|
| Pasos × Producción | 7 | 7 ✅ |
| Pasos × Pruebas | 9 | 9 ✅ |

---

## Fase 6 — `Dim_Dataset` (guía, sección 6) ✅ 2026-08-18

- [x] Crear la tabla manual `Dim_Dataset` con `#table(...)`.
- [x] Relacionarla 1-a-muchos con `Envios[Dataset]`, `Renovaciones[Dataset]`, `Atribucion[Dataset]`.
- [x] Confirmar en la vista de modelo que las 3 flechas de relación apuntan **desde** `Dim_Dataset`
      **hacia** las tres tablas de hechos (dirección de filtro correcta).

**Checkpoint — validado:** `Dim_Dataset[DatasetLabel]` filtrando `Recuento de filas` de `Envios` da
6 567 (Producción) y 3 017 (Pruebas) — coincide con la Fase 2. ✅

**Checkpoint:** arma una tabla visual con `Dim_Dataset[DatasetLabel]` en filas y
`COUNTROWS(Envios)` como valor — deben aparecer dos filas (Producción / Pruebas) con conteos
distintos de cero.

---

## Fase 7 — Tabla `Calendario` (guía, sección 7) ✅ 2026-08-18

- [x] Crear la tabla calculada `Calendario` con el DAX de la sección 7 (corregido: `UNION` de dos
      `SELECTCOLUMNS` en vez de `VALUES(...)[Value]`, que no compilaba).
- [x] Marcarla como tabla de fechas (Herramientas de tabla → Marcar como tabla de fechas → `Date`).
- [x] Relacionarla con `Envios[fecha_envio]`, `Renovaciones[fecha_conv]` y `Atribucion[fecha_conv]`
      — las 3 activas sin pedir `USERELATIONSHIP`.
- [x] Ordenar `DiaSemanaNombre` por `DiaSemanaNum` (columna → Ordenar por columna).

**Checkpoint — validado:** slicer de `Calendario[Date]` acortado cambia el recuento de filas de
`Atribucion` → la relación filtra correctamente. ✅

**Checkpoint:** agrega un slicer de fecha con `Calendario[Date]`, muévelo a un rango chico y
confirma que `COUNTROWS(Atribucion)` cambia — si no reacciona, la relación no quedó activa.

---

## Fase 8 — Medidas base (guía, sección 8) ✅ 2026-08-18

- [x] Crear las 9 medidas: `Envios Totales`, `Impactados`, `Renovaciones Atribuidas`, `Convertidos`,
      `Tasa Conversion`, `Renovaciones del Periodo`, `Share Atribucion`, `Latencia Mediana (dias)`,
      `Pasos del Journey`.
- [x] Formatear `Tasa Conversion` y `Share Atribucion` como porcentaje.

**Checkpoint — validado (Producción):** `Impactados` = 1 346 msisdn distintos (no confundir con
`Envios Totales` = 6 567 filas), `Convertidos` = 128, `Tasa Conversion` = 9.5 % — los 128 atribuidos
son 128 personas distintas (nadie se repite en la ventana de atribución), validado de forma
independiente. ✅

**Checkpoint:** `Tasa Conversion` filtrada a `Dataset = "Produccion"` debe coincidir con
`k['tasa']` que imprime el script para la ola de producción.

---

## Fase 9 — Journey: paso a paso (guía, secciones 9-10)

- [ ] Medidas `Convertidos por Paso`, `Tasa por Paso`, `Convertidos por Canal Envio`,
      `Tasa por Canal Envio` (usan el patrón `TREATAS` explicado en sección 9).
- [ ] Visual "Tasa de conversión por paso": líneas, eje `Envios[paso_idx]`, valor `[Tasa por Paso]`,
      leyenda `Dim_Dataset[DatasetLabel]`.
- [ ] Visual "Línea de tiempo": dispersión, eje X `Envios[dia_rel]`, eje Y `Dim_Dataset[DatasetLabel]`,
      tamaño `[Convertidos por Paso]`.

**Checkpoint:** compara visualmente contra `paso_journey.csv` de cada ola.

---

## Fase 10 — Ritmo (guía, sección 11)

- [ ] Medidas `% del Dataset (Dia Semana)`, `% del Dataset (Latencia)`, `% del Dataset (Toques Previos)`.
- [ ] Medidas `Atribuidas Acumuladas` y `% Acumulado` (requieren `dia_rel_conv` de la Fase 5).
- [ ] 4 visuales: día de semana, latencia, toques previos, curva acumulada (línea escalonada).

---

## Fase 11 — Composición / perfil (guía, sección 12)

- [ ] Duplicar el set de 4 medidas (`% Atribuido`, `Renovaciones Base (Categoria)`,
      `% Base Periodo`, `Indice Composicion`) para cada dimensión: `departamento`, `ciudad`,
      `plan_detalle`, `canal_venta` (16 medidas en total — agrúpalas en una carpeta de medidas
      "Composición").
- [ ] 4 visuales de barras horizontales con línea de referencia en 100, Top N por
      `[Renovaciones Atribuidas]`.

---

## Fase 12 — Slicers (guía, sección 13)

- [ ] Slicer de fecha (`Calendario[Date]`) — ya probado en Fase 7.
- [ ] Slicer de `Dim_Dataset[DatasetLabel]`.
- [ ] Slicer de paso del journey, canal de mensaje, canal de venta, departamento/ciudad, plan.
- [ ] (Opcional) bins de `toques_previos` y `dias_al_convertir` para slicers de rango.

---

## Fase 13 — Verificación final

- [ ] Con el slicer de fecha en el rango completo y ambos datasets seleccionados, compara **todos**
      los KPIs de la Fase 8 contra la salida del script de Python (el bloque final que imprime
      `impactados`, `atribuidas`, `tasa`, `latencia mediana`, líneas 1055-1062).
- [ ] Si algo no cuadra, aísla la fase (usando este checklist) donde se introdujo la diferencia
      antes de seguir ajustando visuales.

---

## Fase 14 — Publicar (si aplica)

- [ ] Guardar el `.pbix` en `powerbi/`.
- [ ] Si se va a publicar a un workspace de Power BI Service, confirmar credenciales/gateway para
      que el refresco programado pueda leer los CSV desde su ubicación real.

---

**Progreso actual:** guía escrita (`guia-dax-powerbi.md`), CSV confirmados en `produ/` y `pruebas/`.
Próximo paso: Fase 0.
