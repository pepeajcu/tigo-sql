# Guía: journey de renovaciones en Power BI (Power Query + DAX)

Traducción de `3-analisis-reno_dashboard.py` a un modelo de Power BI. Arquitectura elegida:

- **Power Query (M)**: limpieza, ventanas de atribución y el "último toque" (todo lo que en el
  script hacía DuckDB con SQL). Es ETL determinista — no debe recalcularse según los filtros que
  toque el usuario, igual que el CSV que генera el script hoy.
- **DAX**: tabla Calendario, relaciones, medidas y comparativos. Aquí sí vive todo lo que reacciona
  a los slicers.
- **Modelo**: `Envios` y `Renovaciones` son tablas únicas (append de ambos orígenes) con una columna
  `Dataset` = `"Produccion"` / `"Pruebas"`. Comparar en el mismo visual es usar `Dataset` como
  leyenda/eje — nunca duplicar medidas.

Archivos de origen — esta carpeta (`powerbi/`) es la carpeta de trabajo para todo lo de Power BI de
aquí en adelante; las dos subcarpetas son las dos **olas de análisis que se comparan entre sí**:

| | `powerbi/produ/` | `powerbi/pruebas/` |
|---|---|---|
| Envíos | `envios_produ.csv` | `envios_pruebas.csv` |
| Renovaciones | `reno_produ.csv` | `reno_pruebas.csv` |

Encabezados verificados en los 4 CSV (idénticos entre las dos olas):
- Envíos: `msisdn, cuenta_id, fecha_envio, canal, canvas_step_nm, canvas_variation_nm, campaign_id`
  (`campaign_id` no se usa — las funciones de limpieza de la sección 1 seleccionan solo las columnas
  necesarias, así que se descarta solo).
- Renovaciones: `msisdn, fecha_conv, channel, ciudad, departamento, bfr_vc_nm, bfr_dt_nm`

---

## 0. Diagrama del modelo

```
Dim_Dataset ──┬── Envios[Dataset]
              ├── Renovaciones[Dataset]
              └── Atribucion[Dataset]

Calendario[Date] ──┬── Envios[fecha_envio]
                    ├── Renovaciones[fecha_conv]
                    └── Atribucion[fecha_conv]
```

`Envios`, `Renovaciones` y `Atribucion` **no están relacionadas entre sí** — son tres tablas de
hechos a distinto grano (evento de envío, evento de renovación, renovación-ya-atribuida). Cuando
una medida necesita cruzar dos de ellas por un atributo que comparten (canal, paso, departamento…)
se usa `TREATAS` dentro de la medida en vez de crear una relación física para cada atributo. Es un
único patrón, reutilizado — lo explico una vez en la sección 3 y lo repito igual en cada medida.

---

## 1. Power Query — funciones de limpieza

Crea dos **funciones** reutilizables (clic derecho en el panel de consultas → Nueva consulta →
Consulta en blanco → pega el código → Inicio → Crear función, o simplemente crea la consulta y
Power BI la detecta como función porque empieza con parámetros).

### `fx_Msisdn`
Equivalente a la macro `f_msisdn` (línea 136-138): se queda con los últimos 8 dígitos.

```m
(x as any) as text =>
let
    texto        = Text.From(x, "es-ES"),
    soloDigitos  = Text.Select(texto, {"0".."9"}),
    ultimos8     = Text.End(soloDigitos, 8)
in
    ultimos8
```

### `fx_Fecha`
Equivalente a la macro `f_fecha` (línea 127-131): toma los primeros 10 caracteres.

```m
(x as any) as nullable date =>
let
    texto     = Text.From(x, "es-ES"),
    primeros10 = Text.Start(texto, 10),
    fecha     = try Date.FromText(primeros10) otherwise null
in
    fecha
```

### `fx_LimpiarEnvios`
Equivalente al `CREATE TABLE {p}_envios` (líneas 164-175). Recibe la tabla cruda y el nombre del
dataset, y devuelve ya limpio y filtrado.

```m
(tabla as table, datasetNombre as text) as table =>
let
    ConMsisdn   = Table.AddColumn(tabla, "msisdn_limpio", each fx_Msisdn([msisdn]), type text),
    ConFecha    = Table.AddColumn(ConMsisdn, "fecha_envio_limpia", each fx_Fecha([fecha_envio]), type date),
    ConCanal    = Table.AddColumn(ConFecha, "canal_limpio", each Text.Lower(Text.Trim(Text.From([canal]))), type text),
    ConPaso     = Table.AddColumn(ConCanal, "paso_limpio",
                    each let v = Text.Trim(Text.From([canvas_step_nm])) in if v = "" then "(sin paso)" else v, type text),
    ConVariante = Table.AddColumn(ConPaso, "variante_limpia",
                    each let v = Text.Trim(Text.From([canvas_variation_nm])) in if v = "" then "(sin variante)" else v, type text),
    Filtrado    = Table.SelectRows(ConVariante, each Text.Length([msisdn_limpio]) = 8 and [fecha_envio_limpia] <> null),
    ConDataset  = Table.AddColumn(Filtrado, "Dataset", each datasetNombre, type text),
    Final       = Table.SelectColumns(ConDataset,
                    {"Dataset", "msisdn_limpio", "cuenta_id", "fecha_envio_limpia", "canal_limpio", "paso_limpio", "variante_limpia"}),
    Renombrado  = Table.RenameColumns(Final,
                    {{"msisdn_limpio","msisdn"}, {"fecha_envio_limpia","fecha_envio"}, {"canal_limpio","canal"},
                     {"paso_limpio","canvas_step_nm"}, {"variante_limpia","canvas_variation_nm"}})
in
    Renombrado
```

### `fx_LimpiarReno`
Equivalente al `CREATE TABLE {p}_reno` (líneas 177-189).

```m
(tabla as table, datasetNombre as text) as table =>
let
    Mayus       = (col as any) as text => let v = Text.Trim(Text.From(col)) in if v = "" then "SIN DATO" else Text.Upper(v),
    ConMsisdn   = Table.AddColumn(tabla, "msisdn_limpio", each fx_Msisdn([msisdn]), type text),
    ConFecha    = Table.AddColumn(ConMsisdn, "fecha_conv_limpia", each fx_Fecha([fecha_conv]), type date),
    ConVenta    = Table.AddColumn(ConFecha, "canal_venta_", each Mayus([channel]), type text),
    ConCiudad   = Table.AddColumn(ConVenta, "ciudad_", each Mayus([ciudad]), type text),
    ConDepto    = Table.AddColumn(ConCiudad, "departamento_", each Mayus([departamento]), type text),
    ConPlan     = Table.AddColumn(ConDepto, "plan_nm_", each Mayus([bfr_vc_nm]), type text),
    ConDetalle  = Table.AddColumn(ConPlan, "plan_detalle_", each Mayus([bfr_dt_nm]), type text),
    Filtrado    = Table.SelectRows(ConDetalle, each Text.Length([msisdn_limpio]) = 8 and [fecha_conv_limpia] <> null),
    ConDataset  = Table.AddColumn(Filtrado, "Dataset", each datasetNombre, type text),
    Final       = Table.SelectColumns(ConDataset,
                    {"Dataset", "msisdn_limpio", "fecha_conv_limpia", "canal_venta_", "ciudad_", "departamento_", "plan_nm_", "plan_detalle_"}),
    Renombrado  = Table.RenameColumns(Final,
                    {{"msisdn_limpio","msisdn"}, {"fecha_conv_limpia","fecha_conv"}, {"canal_venta_","canal_venta"},
                     {"ciudad_","ciudad"}, {"departamento_","departamento"}, {"plan_nm_","plan_nm"}, {"plan_detalle_","plan_detalle"}}),
    SinDuplicados = Table.Distinct(Renombrado)   -- SELECT DISTINCT del original, linea 179
in
    SinDuplicados
```

---

## 2. Power Query — carga y unificación

Carga cada CSV (Inicio → Obtener datos → Texto/CSV), promueve encabezados, y aplica la función que
corresponda. Cuatro consultas de origen:

```m
// Envios_Produ  →  powerbi/produ/envios_produ.csv
let
    Origen = Csv.Document(File.Contents("...\powerbi\produ\envios_produ.csv"), [Delimiter=",", Encoding=65001]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars=true]),
    Limpio = fx_LimpiarEnvios(Encabezados, "Produccion")
in
    Limpio

// Envios_Pruebas  →  powerbi/pruebas/envios_pruebas.csv  (mismo patron, dataset = "Pruebas")
// Reno_Produ      →  powerbi/produ/reno_produ.csv         (fx_LimpiarReno, dataset = "Produccion")
// Reno_Pruebas    →  powerbi/pruebas/reno_pruebas.csv      (fx_LimpiarReno, dataset = "Pruebas")
```

En Power BI, al usar **Obtener datos → Carpeta** apuntando a `powerbi/`, o simplemente al elegir cada
CSV con el diálogo de archivo, la ruta absoluta queda embebida en `File.Contents(...)` — si mueves la
carpeta `powerbi/` de máquina, solo hay que corregir esas 4 rutas (mismo problema que resuelve
`carpeta()` en el script de Python, líneas 40-43).

Y dos consultas finales que se cargan al modelo:

```m
// Envios
Table.Combine({Envios_Produ, Envios_Pruebas})

// Renovaciones
Table.Combine({Reno_Produ, Reno_Pruebas})
```

Marca `Envios_Produ`, `Envios_Pruebas`, `Reno_Produ`, `Reno_Pruebas` como **"Habilitar carga" = No**
(clic derecho → Habilitar carga) — solo son pasos intermedios, igual que las tablas `_raw` del
script no salen en el dashboard final.

---

## 3. Power Query — Ventanas de atribución

Equivalente a `{p}_ventanas` (líneas 209-216): cada envío vive desde `fecha_envio` hasta el
siguiente envío del mismo msisdn (o +7 días si es el último). Se resuelve con `Table.Group`
(agrupa por persona, ordena, y calcula el "siguiente" con los índices de la lista — no hace falta
un self-join fila a fila, que sería lento en M):

```m
// Ventanas
let
    Origen    = Table.Distinct(Table.SelectColumns(Envios, {"Dataset", "msisdn", "fecha_envio"})),
    Agrupado  = Table.Group(Origen, {"Dataset", "msisdn"},
                  {{"Fechas", each Table.Sort(_, {{"fecha_envio", Order.Ascending}}), type table}}),
    ConVentanas = Table.AddColumn(Agrupado, "Ventanas", each
        let
            fechas = [Fechas][fecha_envio],
            n      = List.Count(fechas),
            filas  = List.Transform({0..n-1}, (i) =>
                [ fecha_envio = fechas{i},
                  fin_ventana = if i < n - 1 then fechas{i+1} else Date.AddDays(fechas{i}, 7) ])
        in
            Table.FromRecords(filas)),
    Expandido = Table.ExpandTableColumn(ConVentanas, "Ventanas", {"fecha_envio", "fin_ventana"}),
    Final     = Table.SelectColumns(Expandido, {"Dataset", "msisdn", "fecha_envio", "fin_ventana"})
in
    Final
```

*(`TOPE_VENTANA_DIAS = 7` está fijo en `Date.AddDays(fechas{i}, 7)`; si algún día lo quieres
parametrizable, crea un parámetro de Power Query `P_VentanaDias` y sustitúyelo ahí.)*

---

## 4. Power Query — la atribución (el corazón del modelo)

Equivalente a `{p}_atribucion` (líneas 218-240). Nota clave que simplifica mucho la traducción: como
las ventanas de un mismo msisdn son contiguas, la renovación siempre cae en la ventana del **envío
más reciente que sea `<= fecha_conv`** — no hace falta reconstruir el join completo con `Ventanas`,
basta con encontrar esa fecha máxima y comprobar que la renovación siga dentro de su ventana
(`< fin_ventana`, para descartar las que caen después de los 7 días del último envío). El desempate
por canal (`PRIORIDAD_CANAL`, línea 56) se aplica solo cuando hay varios envíos el mismo día.

```m
// Atribucion
let
    CanalPrioridad = [whatsapp = 3, sms = 2, push = 1, email = 4, inapp = 5],

    EnviosPorPersona = Table.Group(Envios, {"Dataset", "msisdn"},
                          {{"Eventos", each Table.Sort(_, {{"fecha_envio", Order.Ascending}}), type table}}),

    ConEventos = Table.NestedJoin(Renovaciones, {"Dataset", "msisdn"}, EnviosPorPersona, {"Dataset", "msisdn"}, "EnviosMsisdn", JoinKind.Inner),
    Expandido1 = Table.ExpandTableColumn(ConEventos, "EnviosMsisdn", {"Eventos"}),

    ConCandidato = Table.AddColumn(Expandido1, "Candidato", each
        let
            fc       = [fecha_conv],
            eventos  = [Eventos],
            fechas   = eventos[fecha_envio],
            previas  = List.Select(fechas, each _ <= fc),
            n        = List.Count(previas)
        in
            if n = 0 then null
            else
                let
                    fUlt          = List.Max(previas),
                    filasMismaFecha = Table.SelectRows(eventos, each [fecha_envio] = fUlt),
                    siguientes    = List.Select(fechas, each _ > fUlt),
                    finVentana    = if List.Count(siguientes) = 0 then Date.AddDays(fUlt, 7) else List.Min(siguientes),
                    dentro        = fc < finVentana
                in
                    if not dentro then null
                    else
                        let
                            conPrioridad = Table.AddColumn(filasMismaFecha, "prioridad",
                                             each Record.FieldOrDefault(CanalPrioridad, [canal], 99)),
                            ganador      = Table.First(Table.Sort(conPrioridad, {{"prioridad", Order.Ascending}}))
                        in
                            [ fecha_envio          = ganador[fecha_envio],
                              cuenta_id            = ganador[cuenta_id],
                              canal                = ganador[canal],
                              canvas_step_nm        = ganador[canvas_step_nm],
                              canvas_variation_nm   = ganador[canvas_variation_nm],
                              dias_al_convertir     = Duration.Days(fc - ganador[fecha_envio]),
                              toques_previos        = n ]),

    ConMatch   = Table.SelectRows(ConCandidato, each [Candidato] <> null),
    Expandido2 = Table.ExpandRecordColumn(ConMatch, "Candidato",
                   {"fecha_envio","cuenta_id","canal","canvas_step_nm","canvas_variation_nm","dias_al_convertir","toques_previos"}),
    Final      = Table.RemoveColumns(Expandido2, {"Eventos"})
in
    Final
```

Resultado: una fila por renovación atribuida, con **todas** las columnas de `Renovaciones`
(msisdn, fecha_conv, canal_venta, ciudad, departamento, plan_nm, plan_detalle, Dataset) **más** las
del envío ganador (fecha_envio, canal, canvas_step_nm, dias_al_convertir, toques_previos). Es el
mismo contenido que `detalle_atribucion.csv` (línea 413) — por eso, más abajo, casi ninguna medida
necesita relacionar `Atribucion` con `Envios` o `Renovaciones`: ya trae todo consigo.

⚠️ Si algún dataset es grande (cientos de miles de filas), verifica el tiempo de refresco: el
`Table.Group` por persona es O(n), pero mantén el query en modo *no cargar pasos intermedios* y
Power Query lo optimizará razonablemente. Si se vuelve lento, avísame y lo reescribimos con
`Table.Buffer` selectivo.

---

## 5. Power Query — orden del journey (`paso_idx`, `dia_rel`)

Equivalente a `{p}_orden` (líneas 257-262) + el `dia_cero` de cada dataset (línea 205). Se calcula
una vez y se **fusiona como columnas** directamente en `Envios` y en `Atribucion` (así ninguna de
las dos necesita una tabla `Pasos` relacionada aparte).

```m
// Pasos  (consulta intermedia, no hace falta cargarla al modelo)
let
    DiaCero   = Table.Group(Envios, {"Dataset"}, {{"dia_cero", each List.Min([fecha_envio]), type date}}),
    Agrupado  = Table.Group(Envios, {"Dataset", "canvas_step_nm"}, {{"primera_fecha", each List.Min([fecha_envio]), type date}}),
    ConCero   = Table.NestedJoin(Agrupado, {"Dataset"}, DiaCero, {"Dataset"}, "cero", JoinKind.LeftOuter),
    Expand1   = Table.ExpandTableColumn(ConCero, "cero", {"dia_cero"}),
    ConIdx    = Table.Group(Expand1, {"Dataset"},
                  {{"Filas", each Table.AddIndexColumn(
                       Table.Sort(_, {{"primera_fecha", Order.Ascending}, {"canvas_step_nm", Order.Ascending}}),
                       "paso_idx", 1, 1), type table}}),
    Expand2   = Table.ExpandTableColumn(ConIdx, "Filas", {"canvas_step_nm", "primera_fecha", "dia_cero", "paso_idx"}),
    ConRel    = Table.AddColumn(Expand2, "dia_rel", each Duration.Days([primera_fecha] - [dia_cero]), Int64.Type)
in
    ConRel
```

Luego, en la consulta `Envios` (y en `Atribucion`), añade un paso final `Table.NestedJoin` contra
`Pasos` por `{"Dataset","canvas_step_nm"}`, expandiendo solo `paso_idx` y `dia_rel`. Así ambas
tablas quedan con esas dos columnas listas para usar como eje sin relaciones adicionales.

---

## 6. Power Query — dimensión `Dim_Dataset`

Tabla chica manual (Inicio → Introducir datos), la única relación física del modelo aparte del
calendario — se usa como leyenda/slicer en **todos** los visuales comparativos:

```m
#table(
    {"Dataset", "DatasetLabel", "Color"},
    {
        {"Produccion", "Producción", "#F5B700"},
        {"Pruebas",    "Pruebas",    "#112CB7"}
    }
)
```

Relaciónala 1-a-muchos con `Envios[Dataset]`, `Renovaciones[Dataset]` y `Atribucion[Dataset]`. En
los visuales usa siempre `Dim_Dataset[DatasetLabel]` como leyenda — **no** `Envios[Dataset]`
directamente, porque el filtro solo se propaga correctamente desde el lado "1" de la relación hacia
las tres tablas de hechos a la vez.

---

## 7. DAX — tabla Calendario

```dax
Calendario =
VAR MinFecha =
    MINX ( UNION ( VALUES ( Envios[fecha_envio] ), VALUES ( Renovaciones[fecha_conv] ) ), [Value] )
VAR MaxFecha =
    MAXX ( UNION ( VALUES ( Envios[fecha_envio] ), VALUES ( Renovaciones[fecha_conv] ) ), [Value] )
RETURN
ADDCOLUMNS (
    CALENDAR ( MinFecha, MaxFecha ),
    "Año", YEAR ( [Date] ),
    "MesNum", MONTH ( [Date] ),
    "MesNombre", FORMAT ( [Date], "MMMM" ),
    "DiaSemanaNum", WEEKDAY ( [Date], 2 ),
    "DiaSemanaNombre",
        SWITCH ( WEEKDAY ( [Date], 2 ),
            1, "Lunes", 2, "Martes", 3, "Miércoles", 4, "Jueves",
            5, "Viernes", 6, "Sábado", 7, "Domingo" )
)
```

Márcala como **tabla de fechas** (Herramientas de tabla → Marcar como tabla de fechas → `Date`).
Relaciónala 1-a-muchos con `Envios[fecha_envio]`, `Renovaciones[fecha_conv]` y `Atribucion[fecha_conv]`
— **las tres pueden quedar activas a la vez**, porque son pares de tablas distintos (no hay
ambigüedad; solo haría falta `USERELATIONSHIP` si dos columnas de fecha de la *misma* tabla
apuntaran ambas a `Calendario`, que no es el caso aquí).

Este es el slicer de fechas que pediste: un único control de fecha en el dashboard filtra
simultáneamente envíos, renovaciones y atribución.

---

## 8. DAX — medidas base

```dax
Envios Totales = COUNTROWS ( Envios )

Impactados = DISTINCTCOUNT ( Envios[msisdn] )

Renovaciones Atribuidas = COUNTROWS ( Atribucion )

Convertidos = DISTINCTCOUNT ( Atribucion[msisdn] )

Tasa Conversion = DIVIDE ( [Convertidos], [Impactados] )        -- formato %

Renovaciones del Periodo = COUNTROWS ( Renovaciones )           -- atribuidas o no

Share Atribucion = DIVIDE ( [Renovaciones Atribuidas], [Renovaciones del Periodo] )  -- formato %

Latencia Mediana (dias) = MEDIAN ( Atribucion[dias_al_convertir] )

Pasos del Journey = DISTINCTCOUNT ( Envios[canvas_step_nm] )
```

Estas seis medidas, con `Dim_Dataset[DatasetLabel]` como leyenda, ya te dan la tarjeta comparativa
de la sección "Resumen" del script (líneas 397-409, 832-847) sin nada adicional.

### Brecha entre datasets (opcional, equivalente a `z_dos_proporciones`, línea 425-434)

```dax
Tasa Produccion  = CALCULATE ( [Tasa Conversion], Dim_Dataset[Dataset] = "Produccion" )
Tasa Pruebas     = CALCULATE ( [Tasa Conversion], Dim_Dataset[Dataset] = "Pruebas" )
Brecha pp        = ( [Tasa Produccion] - [Tasa Pruebas] ) * 100
```
La prueba z bilateral del script es más un detalle estadístico de reporte que algo que un usuario
mueva con slicers — si la quieres en DAX igual, es una fórmula larga con `NORM.S.DIST`; dime y te
la armo, pero normalmente `Brecha pp` + los dos volúmenes ya comunican lo mismo en un dashboard.

---

## 9. DAX — el patrón `TREATAS` (léelo antes de la sección 10)

`Envios`, `Renovaciones` y `Atribucion` **no tienen relación física entre sí** (grano distinto: evento
de envío vs. evento de renovación vs. renovación-ya-resuelta). Cuando un visual necesita cruzar dos
de ellas por un atributo que comparten — canal, paso del journey, departamento… — se usa `TREATAS`
para "prestar" el filtro de una tabla a la otra dentro de la medida. Es el mismo patrón repetido en
cada caso de abajo:

```dax
Convertidos (via TREATAS) =
CALCULATE (
    [Convertidos],
    TREATAS ( VALUES ( Envios[canal] ), Atribucion[canal] )
)
```

Esto dice: "toma los valores de `canal` que están activos ahora mismo por el lado de `Envios`
(por ejemplo, porque `Envios[canal]` está en el eje del gráfico) y aplícalos como filtro sobre
`Atribucion[canal]`". Así el numerador (convertidos) queda sincronizado con el denominador
(impactados) aunque vivan en tablas distintas.

---

## 10. DAX — journey: alcance y tasa por paso / por canal

Sustituye a `{p}_paso` (líneas 264-287) y a la gráfica 3.2/3.3 del script.

```dax
Convertidos por Paso =
CALCULATE (
    [Convertidos],
    TREATAS ( VALUES ( Envios[canvas_step_nm] ), Atribucion[canvas_step_nm] ),
    TREATAS ( VALUES ( Envios[Dataset] ), Atribucion[Dataset] )
)

Tasa por Paso = DIVIDE ( [Convertidos por Paso], [Impactados] )

Convertidos por Canal Envio =
CALCULATE (
    [Convertidos],
    TREATAS ( VALUES ( Envios[canal] ), Atribucion[canal] ),
    TREATAS ( VALUES ( Envios[Dataset] ), Atribucion[Dataset] )
)

Tasa por Canal Envio = DIVIDE ( [Convertidos por Canal Envio], [Impactados] )
```

**Visual sugerido — "Tasa de conversión por paso" (línea 510-524):** gráfico de líneas, eje X =
`Envios[paso_idx]`, valor = `[Tasa por Paso]`, leyenda = `Dim_Dataset[DatasetLabel]`.

**Visual sugerido — "Línea de tiempo del journey" (línea 484-508):** gráfico de dispersión, eje X =
`Envios[dia_rel]`, eje Y = `Dim_Dataset[DatasetLabel]`, tamaño de burbuja = `[Convertidos por Paso]`.

---

## 11. DAX — ritmo: latencia, día de semana, toques previos, curva acumulada

Sustituye a las secciones 3.4/3.5/3.6/3.8 del script (líneas 553-619). Todas siguen el mismo patrón
"% del propio dataset" (línea 570, 611, 375-377): el denominador usa `ALLSELECTED` sobre el campo
del eje para no perder el filtro de `Dataset` ni de `Calendario`.

```dax
% del Dataset (Dia Semana) =
DIVIDE ( [Renovaciones Atribuidas], CALCULATE ( [Renovaciones Atribuidas], ALLSELECTED ( Calendario[DiaSemanaNombre] ) ) )

% del Dataset (Latencia) =
DIVIDE ( [Renovaciones Atribuidas], CALCULATE ( [Renovaciones Atribuidas], ALLSELECTED ( Atribucion[dias_al_convertir] ) ) )

% del Dataset (Toques Previos) =
DIVIDE ( [Renovaciones Atribuidas], CALCULATE ( [Renovaciones Atribuidas], ALLSELECTED ( Atribucion[toques_previos] ) ) )
```

- **Día de la semana**: eje X = `Calendario[DiaSemanaNombre]` (ordena esta columna por
  `DiaSemanaNum` en Modelado → Ordenar por columna), valor = `[% del Dataset (Dia Semana)]`.
- **Latencia**: eje X = `Atribucion[dias_al_convertir]`, valor = `[% del Dataset (Latencia)]`.
- **Toques previos**: eje X = `Atribucion[toques_previos]`, valor = `[% del Dataset (Toques Previos)]`.

### Curva acumulada (día relativo a la conversión, línea 380-389)

Necesitas primero un `dia_rel_conv` en `Atribucion`: en la consulta M de `Atribucion` (sección 4),
añade un paso final que haga merge con `Pasos`-`DiaCero` por `Dataset` y calcule
`Duration.Days([fecha_conv] - [dia_cero])`. Con esa columna:

```dax
Atribuidas Acumuladas =
CALCULATE (
    [Renovaciones Atribuidas],
    FILTER ( ALLSELECTED ( Atribucion[dia_rel_conv] ), Atribucion[dia_rel_conv] <= MAX ( Atribucion[dia_rel_conv] ) )
)

% Acumulado =
DIVIDE (
    [Atribuidas Acumuladas],
    CALCULATE ( [Renovaciones Atribuidas], ALLSELECTED ( Atribucion[dia_rel_conv] ) )
)
```

Visual: gráfico de líneas escalonado (Format → Line → Step), eje X = `Atribucion[dia_rel_conv]`,
valor = `[% Acumulado]`, leyenda = `Dim_Dataset[DatasetLabel]`.

---

## 12. DAX — perfil de quién renueva (índice de composición)

Sustituye a `dimension()` (líneas 327-348) y a `grafica_dimension()`. Aplica igual a `departamento`,
`ciudad`, `plan_detalle` y `canal_venta` — todas viven **ya dentro de `Atribucion`** (vinieron
copiadas desde `Renovaciones` en la sección 4), así que el numerador no necesita `TREATAS`; solo el
denominador necesita "tomar prestado" el filtro hacia `Renovaciones`, que sí es una tabla distinta.

```dax
% Atribuido =
DIVIDE ( [Renovaciones Atribuidas], CALCULATE ( [Renovaciones Atribuidas], ALLSELECTED ( Atribucion[departamento] ) ) )

Renovaciones Base (Categoria) =
CALCULATE (
    [Renovaciones del Periodo],
    TREATAS ( VALUES ( Atribucion[departamento] ), Renovaciones[departamento] )
)

% Base Periodo =
DIVIDE ( [Renovaciones Base (Categoria)], [Renovaciones del Periodo] )

Indice Composicion = DIVIDE ( [% Atribuido], [% Base Periodo] ) * 100
```

Para `ciudad`, `plan_detalle` y `canal_venta`, duplica estas cuatro medidas cambiando el nombre de
columna (`Atribucion[ciudad]` / `Renovaciones[ciudad]`, etc.) — no hay forma de parametrizar el
nombre de columna dentro de una medida DAX, así que sí toca una copia por dimensión (4 dimensiones
× 4 medidas = 16 medidas cortas; agrúpalas en una carpeta de medidas "Composición" para no
perderte).

**Visual sugerido:** barras horizontales agrupadas, eje Y = la categoría (top N por
`[Renovaciones Atribuidas]` — usa un *Top N* de filtro visual, línea 623-626 del script usa 8-10),
valor = `[Indice Composicion]`, leyenda = `Dim_Dataset[DatasetLabel]`, línea de referencia en 100.

---

## 13. Filtros / slicers recomendados

Ya tienes el de fecha (`Calendario`). Otros que se desprenden directo de las columnas que ya existen
en el modelo, ordenados por qué tan útiles son:

| Slicer | Campo | Por qué |
|---|---|---|
| **Dataset** | `Dim_Dataset[DatasetLabel]` | El comparativo central — casi siempre como leyenda, pero también sirve como slicer para aislar un solo dataset |
| **Paso del journey** | `Envios[canvas_step_nm]` (ordenado por `paso_idx`) | Ver el detalle de un paso específico en vez de todo el journey |
| **Canal del mensaje** | `Envios[canal]` / `Atribucion[canal]` | whatsapp/sms/push/email/inapp — mismo filtro que la gráfica 3.7 del script |
| **Canal de venta** | `Atribucion[canal_venta]` | Dónde se cierra la renovación (línea 1014-1018) |
| **Departamento / Ciudad** | `Atribucion[departamento]`, `Atribucion[ciudad]` | Geografía |
| **Plan** | `Atribucion[plan_detalle]` | Con qué plan queda la línea |
| **Día de la semana** | `Calendario[DiaSemanaNombre]` | Cruzar "qué día firma" con cualquier otro corte |
| **Rango de toques previos** | `Atribucion[toques_previos]` (agrupado en bins: 1, 2, 3, 4+) | Aísla conversiones "de un solo toque" vs. las que necesitaron insistencia — el script lo grafica pero no lo deja como filtro; en Power BI es fácil agregarlo |
| **Rango de latencia** | `Atribucion[dias_al_convertir]` (bins: 0, 1-2, 3-7) | Conversiones inmediatas vs. tardías |

Nota sobre `canal` y `departamento`/`ciudad`/`plan_detalle` como **slicer** (no solo como eje de un
gráfico): un slicer normal solo filtra la tabla a la que está conectado por relación física. Como
`Envios` y `Atribucion` no están relacionadas, un slicer de `Envios[canal]` no va a filtrar
`Atribucion` automáticamente. Dos salidas:
1. Simple: pon el slicer sobre `Atribucion[canal]` (no `Envios[canal]`) — como casi todo lo que se
   filtra en el dashboard son *resultados* de conversión, esto cubre el 90% de los casos.
2. Si de verdad necesitas que un slicer filtre `Envios` y `Atribucion` a la vez, ahí sí conviene una
   tabla `Dim_Canal` chica relacionada con ambas (mismo patrón que `Dim_Dataset` en la sección 6) en
   vez de TREATAS — dímelo si quieres que te la arme, es un query corto.

---

## 14. Mapa rápido: gráfica del script → visual de Power BI

| Script (función / sección) | Visual Power BI | Medida principal |
|---|---|---|
| 3.1 Timeline (línea 484) | Dispersión (scatter) | `[Convertidos por Paso]`, eje `Envios[dia_rel]` |
| 3.2 Tasa por paso (línea 510) | Líneas | `[Tasa por Paso]` |
| 3.3 Alcance por paso (línea 526) | Barras horizontales | `[Impactados]` vs `[Convertidos por Paso]` |
| 3.4 Día de semana (línea 553) | Barras agrupadas | `[% del Dataset (Dia Semana)]` |
| 3.5 Latencia (línea 566) | Barras agrupadas | `[% del Dataset (Latencia)]` |
| 3.6 Curva acumulada (línea 580) | Líneas escalonadas | `[% Acumulado]` |
| 3.7 Canal (línea 592) | Barras agrupadas | `[Convertidos por Canal Envio]` / `[Impactados]` |
| 3.8 Toques previos (línea 607) | Barras agrupadas | `[% del Dataset (Toques Previos)]` |
| 3.9 Dimensiones (línea 622) | Barras horizontales agrupadas | `[Indice Composicion]` |

---

## Orden sugerido para construirlo

1. Sección 1-2 (funciones + carga) → confirma que `Envios` y `Renovaciones` cargan bien para los
   dos datasets.
2. Sección 3-4 (Ventanas + Atribucion) → valida contra `detalle_atribucion.csv` que ya te generó el
   script: mismo conteo de filas por dataset.
3. Sección 5-7 (Pasos, Dim_Dataset, Calendario) → arma el modelo y las relaciones.
4. Sección 8 → medidas base, primera tarjeta comparativa.
5. Secciones 10-12 → medidas por visual, según vayas armando cada gráfica.
6. Sección 13 → slicers.

Si algún paso de M te tira error al pegarlo (por nombres de columna que no coincidan exactamente
con tus CSV), pásame el mensaje de error y el encabezado real del CSV y lo ajusto.
