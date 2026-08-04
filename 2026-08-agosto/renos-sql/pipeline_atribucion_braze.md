# Atribución de renovaciones a envíos de Braze — Tigo Guatemala

Documento de referencia del pipeline. Cubre objetivo, arquitectura, las cinco
fases con su SQL, el código de cruce, y las trampas encontradas durante la
construcción.

**Periodo:** 1 de junio – 31 de julio de 2026 · **Alcance:** solo Guatemala

---

## 1. Objetivo

Medir qué contacto del journey de retención trae las renovaciones.

El journey son 28 días relativos a cada cliente, con ocho contactos:

| Día | Canal | Etapa | Nota |
|-----|-------|-------|------|
| 1 | Push / SMS | Awareness | |
| 3 | WhatsApp | Awareness | |
| 7 | Push / SMS | Consideración | |
| 10 | WhatsApp | Consideración | A/B test *Smartphone* |
| 12 | Push / SMS | Consideración | |
| 16 | WhatsApp | Consideración | A/B test *GB* |
| 21 | Push / SMS | Decisión | Incentivo final |
| 28 | Push / SMS | Reminders | → cuarentena |

**Salida:** renovaciones atribuidas por día de envío, por canal, y por paso del
journey con su variante de A/B test.

---

## 2. El problema central

Las tres fuentes hablan de "usuario" en idiomas distintos:

- **Envíos (Braze):** identifican por `external_user_id`, un UUID.
- **Renovaciones (Horus):** identifican por número telefónico (`msisdn_dd`).
- **`braze_profile_fct`** es el único puente entre ambos.

Y viven en **dos motores separados**: Braze en Trino, renovaciones en Horus.
No existe una consulta que toque los dos. El cruce ocurre fuera, en Python.

```
TRINO                                    HORUS
braze_chnnl_*_fct                        smy.dm_bi_sls_sttstcs_mnth
      │ external_user_id = external_id          │
braze_profile_fct                              │
      │ msisdn                                  │ msisdn_dd
      ▼                                         ▼
   envios.csv  ───────────►  Python + DuckDB  ◄─── renovaciones.csv
```

---

## 3. Inventario de fuentes

### Trino — `gt_awsmichqice_glue.hq_anl_prd_engmt_link`

| Tabla | Uso |
|-------|-----|
| `braze_chnnl_webhook_fct` | SMS y WhatsApp (los distingue `step_name`) |
| `braze_chnnl_push_fct` | Push |
| `braze_chnnl_email_fct` | Email |
| `braze_chnnl_inapp_fct` | In-app |
| `braze_profile_fct` | Puente `external_id` → `msisdn` |
| `braze_campaign_dim` | Nombres de campaña (no se usa en el pipeline) |

Columnas relevantes de las fct: `instance_tp`, `dt` (partición), `date_send_dt`,
`campaign_id`, `external_user_id`, `canvas_step_nm`, `canvas_variation_nm`,
`step_name` (solo webhook).

Columnas relevantes de perfil: `external_id`, `msisdn`, `phone`, `cntry_cd`,
`fct_dt` (texto, snapshot diario), `bs_un`, `bs_ln`.

### Horus — `smy`

`dm_bi_sls_sttstcs_mnth` — 100% Guatemala, no requiere filtro de país.

Columnas: `fct_dt` (mes, primer día — **es partición mensual**), `evnt_dt`
(fecha real del evento), `evnt_typ`, `msisdn_dd`, `ar_sscrbr_dd`, `sb_bs_un`,
`mv_bs_un`, `bllbl_cd`.

---

## 4. Ventana de atribución

**No se usa ventana fija.** La cadencia del journey tiene huecos de 2 a 7 días,
así que una ventana fija de 7 días haría que casi toda renovación tenga tres o
cuatro envíos compitiendo por el crédito.

**Regla: cada envío vale hasta que llega el siguiente.** Las ventanas quedan de
2, 4, 3, 2, 4, 5 y 7 días — definidas por la cadencia, no elegidas a dedo.
Resultado: cero traslapes y cero huecos. Cada renovación tiene un solo dueño.

Los contactos del día 21 y 28 no tienen siguiente: se les aplica un tope de
7 días (`TOPE_VENTANA_DIAS`).

### Padding asimétrico

Los dos rellenos van a tablas distintas y en direcciones opuestas:

- **−9 días en los envíos** (desde el 22 de mayo): para que una renovación de
  principios de junio encuentre el envío que la causó. Estos envíos **no se
  reportan** — su ventana de conversión está incompleta. Solo participan como
  candidatos de atribución.
- **+7 días en las conversiones** (hasta el 7 de agosto): para que los envíos
  del final de julio alcancen a ver quién renovó.

El −9 en vez de −7 es colchón: el gap máximo del journey es exactamente 7 días
y Braze puede guardar en UTC mientras Horus guarda hora local.

---

## 5. FASE 1 — Unificar los envíos

**Objetivo:** apilar los cuatro canales en una sola estructura, filtrando lo que
no corresponde.

**Cómo se resuelve:** escaneo puro con filtros y `UNION ALL`. Sin joins, sin
agregaciones, sin redistribución de datos entre nodos.

```sql
SELECT lower(step_name) AS canal, external_user_id, date_send_dt AS fecha_envio,
       campaign_id, canvas_step_nm, canvas_variation_nm
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
WHERE dt >= DATE '2026-05-22' AND dt < DATE '2026-08-01'
  AND instance_tp = 'gt'
  AND step_name IN ('SMS', 'WhatsApp')

UNION ALL
SELECT 'push', external_user_id, date_send_dt,
       campaign_id, canvas_step_nm, canvas_variation_nm
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
WHERE dt >= DATE '2026-05-22' AND dt < DATE '2026-08-01' AND instance_tp = 'gt'

UNION ALL
SELECT 'email', external_user_id, date_send_dt,
       campaign_id, canvas_step_nm, canvas_variation_nm
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_email_fct
WHERE dt >= DATE '2026-05-22' AND dt < DATE '2026-08-01' AND instance_tp = 'gt'

UNION ALL
SELECT 'inapp', external_user_id, date_send_dt,
       campaign_id, canvas_step_nm, canvas_variation_nm
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_inapp_fct
WHERE dt >= DATE '2026-05-22' AND dt < DATE '2026-08-01' AND instance_tp = 'gt';
```

**Por qué así:**

- **`UNION ALL`, nunca `UNION`.** `UNION` deduplica sobre el total unificado: un
  shuffle completo de decenas de millones de filas para eliminar cero
  duplicados, porque los canales son mutuamente excluyentes.
- **Filtro por `dt`, no por `date_send_dt`.** `dt` es la partición y poda
  archivos antes de leerlos. La columna lógica filtraría después de escanear.
- **`step_name IN ('SMS','WhatsApp')`** — la tabla webhook también trae `Bridge`,
  `Zendesk` y `Other`, que no son envíos de campaña.
- **Seis columnas y no veintitantas.** En formato columnar lo que no se pide no
  se lee.

**Palanca si el volumen es alto:** resolver los `campaign_id` del journey contra
`braze_campaign_dim` en una consulta aparte y agregarlos como literales
`IN (...)` en cada rama. Reduce antes del join de la fase 2, que es donde
importa.

---

## 6. FASE 2 — Resolver el teléfono

**Objetivo:** traducir `external_user_id` a `msisdn`, que es la única llave que
Horus entiende.

**Cómo se resuelve:** un solo join contra `braze_profile_fct`. Es el único join
del lado de Trino y el paso más caro del pipeline.

En la práctica las fases 1 y 2 son **una sola consulta**, porque no hay permiso
de escritura para materializar tablas intermedias.

```sql
WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-06-01', '2026-07-01', '2026-07-31')
      AND cntry_cd = 'gt'
      AND msisdn IS NOT NULL
    GROUP BY external_id
),
envios AS (
    -- (la consulta completa de la FASE 1)
)
SELECT
    p.msisdn              AS msisdn,
    e.external_user_id    AS cuenta_id,
    e.fecha_envio         AS fecha_envio,
    e.canal               AS canal,
    e.canvas_step_nm      AS canvas_step_nm,
    e.canvas_variation_nm AS canvas_variation_nm,
    e.campaign_id         AS campaign_id
FROM envios e
JOIN perfil p ON p.external_id = e.external_user_id
GROUP BY 1, 2, 3, 4, 5, 6, 7;
```

**Por qué así:**

- **Tres snapshots, no 61.** `fct_dt` es diario y cada foto trae ~37M filas de
  Guatemala. Leer el periodo completo son 2,200 millones de filas para lo que en
  el fondo es un diccionario. Tres fotos cubren tanto a quienes entraron como a
  quienes salieron durante el periodo.
- **`arbitrary(msisdn)` es seguro** porque se verificó que el par
  `external_id` → `msisdn` no cambia entre snapshots (ver píldora #11). Si la
  versión de Trino no la tiene, `min(msisdn)` es equivalente.
- **Sin filtro de `bs_un` / `bs_ln`.** El 62.6% de los perfiles guatemaltecos no
  los tiene poblados; filtrar por ahí borraría siete de cada diez perfiles. El
  lado de Horus ya filtra `MOBILE`, así que el filtro no aporta nada.
- **`JOIN`, no `LEFT JOIN`.** Sin `msisdn` no hay forma de cruzar contra Horus.
- **`GROUP BY` final** colapsa reenvíos del mismo canal el mismo día y achica el
  archivo a descargar.

**Medir antes de exportar** — misma consulta, mismo costo, cuatro números en vez
de millones de filas:

```sql
SELECT count(*)                           AS envios_con_msisdn,
       count(DISTINCT e.external_user_id) AS usuarios,
       count(DISTINCT p.msisdn)           AS telefonos,
       min(e.fecha_envio) AS desde, max(e.fecha_envio) AS hasta
FROM envios e JOIN perfil p ON p.external_id = e.external_user_id;
```

**Salida:** `envios.csv` con columnas `msisdn, cuenta_id, fecha_envio, canal,
canvas_step_nm, canvas_variation_nm`.

---

## 7. FASE 3 — Extraer las renovaciones

**Objetivo:** la lista de líneas que renovaron y cuándo.

```sql
SELECT DISTINCT
    msisdn_dd AS msisdn,
    evnt_dt   AS fecha_conv
FROM smy.dm_bi_sls_sttstcs_mnth
WHERE fct_dt IN (DATE '2026-06-01', DATE '2026-07-01', DATE '2026-08-01')
  AND evnt_dt >= DATE '2026-05-22'
  AND evnt_dt <  DATE '2026-08-08'
  AND evnt_typ = 'RENOVACION'
  AND sb_bs_un = 'MOBILE'
  AND bllbl_cd = 'FACTURABLE';
```

**Por qué así:**

- **Tres particiones mensuales.** `fct_dt` es el mes, no el día. La cola de
  +7 días cae en la partición de agosto: filtrar solo julio deja la última
  semana de envíos con cero conversiones aparentes.
- **`evnt_dt` acota dentro de las particiones**, para no traer meses completos.
- **`DISTINCT`** cubre por adelantado dos riesgos: el traslape si el datamart
  re-expresa meses anteriores, y líneas repetidas el mismo día.
- **Sin `CASE`** en el filtro de unidad de negocio: al filtrar solo
  `RENOVACION`, siempre resuelve a `sb_bs_un`, y una expresión condicional puede
  estorbar el pushdown.

**Salida:** `renovaciones.csv` con columnas `msisdn, fecha_conv`.

---

## 8. FASE 4 — Atribución

**Objetivo:** decidir a qué envío le pertenece cada renovación.

**Cómo se resuelve:** en DuckDB, sobre los dos CSV. Tres pasos:

1. **Normalizar el teléfono** de ambos lados: solo dígitos, últimos 8.
2. **Calcular la ventana** de cada envío con `lead()` sobre las fechas distintas
   por teléfono.
3. **Cruzar y desempatar** con `row_number()`, quedándose con una sola fila por
   renovación (last-touch).

```sql
-- Ventanas
WITH fechas AS (SELECT DISTINCT msisdn, fecha_envio FROM envios)
SELECT msisdn, fecha_envio,
       COALESCE(
           lead(fecha_envio) OVER (PARTITION BY msisdn ORDER BY fecha_envio),
           fecha_envio + INTERVAL 7 DAY
       ) AS fin_ventana
FROM fechas;

-- Atribución
FROM renovaciones r
JOIN ventanas v ON v.msisdn = r.msisdn
               AND r.fecha_conv >= v.fecha_envio
               AND r.fecha_conv <  v.fin_ventana
JOIN envios e   ON e.msisdn = v.msisdn
               AND e.fecha_envio = v.fecha_envio
```

El doble join es necesario: `ventanas` responde *qué fecha de envío se lleva
esta renovación*, y `envios` responde *qué se mandó ese día* (canal, paso,
variante), que `ventanas` no conserva.

---

## 9. FASE 5 — Reporte

**Objetivo:** dos vistas del resultado.

- **Por día y canal** — responde "qué día rindió más".
- **Por paso del journey y variante** — responde "qué contacto rinde más".

La segunda es la que importa. Los días del journey son **relativos a cada
cliente**: el día 7 de uno es el día 21 de otro. Agrupar por fecha calendario
mezcla gente en etapas distintas del funnel. `canvas_step_nm` es el eje que
compara peras con peras; `canvas_variation_nm` separa los dos A/B tests.

Ambos reportes tienen la misma forma: un CTE `alcance` (denominador, desde
`envios`) y un CTE `conv` (numerador, desde `atribucion`), unidos por
`LEFT JOIN` para que los días sin conversión aparezcan en cero en vez de
desaparecer.

---

## 10. Código de cruce

```python
"""
Cruce de envios Braze (Trino) con renovaciones (Horus).

Entrada:
  envios.csv         msisdn, cuenta_id, fecha_envio, canal,
                     canvas_step_nm, canvas_variation_nm
  renovaciones.csv   msisdn, fecha_conv

Uso:  pip install duckdb && python atribucion.py
"""

import duckdb

# ---------------------------------------------------------------- CONFIG
ENVIOS_CSV = "envios.csv"
RENOVACIONES_CSV = "renovaciones.csv"

# Los envios anteriores a esta fecha participan en la atribucion pero NO
# se reportan: su ventana de conversion esta incompleta.
REPORTE_DESDE = "2026-06-01"
REPORTE_HASTA = "2026-08-01"   # exclusivo

TOPE_VENTANA_DIAS = 7          # para los envios sin uno siguiente

# Desempate cuando dos canales caen el mismo dia. Menor = gana.
PRIORIDAD_CANAL = {"whatsapp": 1, "sms": 2, "push": 3, "email": 4, "inapp": 5}

SALIDA_DIA_CANAL = "reporte_dia_canal.csv"
SALIDA_PASO = "reporte_paso_journey.csv"
SALIDA_DETALLE = "detalle_atribucion.csv"
# ------------------------------------------------------------------------

con = duckdb.connect()

_case_prioridad = "CASE canal\n" + "\n".join(
    f"    WHEN '{k}' THEN {v}" for k, v in PRIORIDAD_CANAL.items()
) + "\n    ELSE 99 END"


def norm(col):
    """Deja solo digitos y se queda con los ultimos 8 (formato GT)."""
    return f"right(regexp_replace(CAST({col} AS VARCHAR), '[^0-9]', '', 'g'), 8)"


# 1. Cargar y normalizar --------------------------------------------------
# all_varchar=true evita que el lector convierta los telefonos a numero
# y les coma los ceros o les pegue un .0 al final.
con.execute(f"""
CREATE OR REPLACE TABLE envios AS
SELECT
    {norm('msisdn')}                AS msisdn,
    cuenta_id,
    TRY_CAST(fecha_envio AS DATE)   AS fecha_envio,
    lower(trim(canal))              AS canal,
    COALESCE(canvas_step_nm, '(sin paso)')          AS canvas_step_nm,
    -- Sin este COALESCE los pasos sin variante quedan en NULL y el LEFT
    -- JOIN del reporte por paso no engancha: NULL nunca es igual a NULL.
    COALESCE(canvas_variation_nm, '(sin variante)') AS canvas_variation_nm
FROM read_csv('{ENVIOS_CSV}', all_varchar = true)
WHERE {norm('msisdn')} <> ''
  AND TRY_CAST(fecha_envio AS DATE) IS NOT NULL;
""")

con.execute(f"""
CREATE OR REPLACE TABLE renovaciones AS
SELECT DISTINCT
    {norm('msisdn')}              AS msisdn,
    TRY_CAST(fecha_conv AS DATE)  AS fecha_conv
FROM read_csv('{RENOVACIONES_CSV}', all_varchar = true)
WHERE {norm('msisdn')} <> ''
  AND TRY_CAST(fecha_conv AS DATE) IS NOT NULL;
""")

# 2. Diagnostico: si esto sale mal, nada de lo demas sirve ----------------
diag = con.execute("""
SELECT
    (SELECT count(*) FROM envios)                     AS filas_envios,
    (SELECT count(DISTINCT msisdn) FROM envios)       AS msisdn_envios,
    (SELECT count(*) FROM renovaciones)               AS filas_renov,
    (SELECT count(DISTINCT msisdn) FROM renovaciones) AS msisdn_renov,
    (SELECT count(DISTINCT r.msisdn) FROM renovaciones r
       WHERE EXISTS (SELECT 1 FROM envios e WHERE e.msisdn = r.msisdn))
                                                      AS msisdn_en_ambos
""").fetchone()

print("--- Diagnostico ---")
print(f"Envios:        {diag[0]:>12,} filas   {diag[1]:>10,} msisdn")
print(f"Renovaciones:  {diag[2]:>12,} filas   {diag[3]:>10,} msisdn")
print(f"Msisdn de renovacion que aparecen en envios: {diag[4]:,}"
      f"  ({100 * diag[4] / max(diag[3], 1):.1f}%)\n")

if diag[4] == 0:
    raise SystemExit(
        "Cero coincidencias de msisdn. Revisa el formato en ambos CSV "
        "antes de seguir: imprime unos valores crudos de cada lado."
    )

# 3. Ventana: cada envio vale hasta que llega el siguiente ----------------
con.execute(f"""
CREATE OR REPLACE TABLE ventanas AS
WITH fechas AS (
    SELECT DISTINCT msisdn, fecha_envio FROM envios
)
SELECT
    msisdn,
    fecha_envio,
    COALESCE(
        lead(fecha_envio) OVER (PARTITION BY msisdn ORDER BY fecha_envio),
        fecha_envio + INTERVAL {TOPE_VENTANA_DIAS} DAY
    ) AS fin_ventana
FROM fechas;
""")

# 4. Atribucion last-touch ------------------------------------------------
con.execute(f"""
CREATE OR REPLACE TABLE atribucion AS
WITH candidatos AS (
    SELECT
        r.msisdn, r.fecha_conv, e.cuenta_id, e.fecha_envio, e.canal,
        e.canvas_step_nm, e.canvas_variation_nm,
        date_diff('day', e.fecha_envio, r.fecha_conv) AS dias_al_convertir,
        -- Cuantos canales compitieron ese mismo dia. Si es > 1, el
        -- ganador lo decidio PRIORIDAD_CANAL, no la data.
        count(*) OVER (
            PARTITION BY r.msisdn, r.fecha_conv, e.fecha_envio
        ) AS canales_mismo_dia,
        row_number() OVER (
            PARTITION BY r.msisdn, r.fecha_conv
            ORDER BY e.fecha_envio DESC, {_case_prioridad}
        ) AS rn
    FROM renovaciones r
    JOIN ventanas v
      ON v.msisdn = r.msisdn
     AND r.fecha_conv >= v.fecha_envio
     AND r.fecha_conv <  v.fin_ventana
    JOIN envios e
      ON e.msisdn = v.msisdn
     AND e.fecha_envio = v.fecha_envio
)
SELECT * EXCLUDE (rn) FROM candidatos WHERE rn = 1;
""")

# 5. Reportes -------------------------------------------------------------
con.execute(f"""
CREATE OR REPLACE TABLE reporte_dia_canal AS
WITH alcance AS (
    SELECT fecha_envio, canal,
           count(DISTINCT msisdn)    AS msisdn_impactados,
           count(DISTINCT cuenta_id) AS cuentas_impactadas
    FROM envios
    WHERE fecha_envio >= DATE '{REPORTE_DESDE}'
      AND fecha_envio <  DATE '{REPORTE_HASTA}'
    GROUP BY 1, 2
),
conv AS (
    SELECT fecha_envio, canal,
           count(DISTINCT msisdn) AS msisdn_convertidos,
           count(*)               AS renovaciones,
           round(avg(dias_al_convertir), 2) AS dias_prom
    FROM atribucion
    WHERE fecha_envio >= DATE '{REPORTE_DESDE}'
      AND fecha_envio <  DATE '{REPORTE_HASTA}'
    GROUP BY 1, 2
)
SELECT
    a.fecha_envio,
    dayname(a.fecha_envio) AS dia_semana,
    a.canal,
    a.msisdn_impactados,
    a.cuentas_impactadas,
    COALESCE(c.msisdn_convertidos, 0) AS msisdn_convertidos,
    COALESCE(c.renovaciones, 0)       AS renovaciones,
    round(100.0 * COALESCE(c.msisdn_convertidos, 0)
          / nullif(a.msisdn_impactados, 0), 2) AS tasa_pct,
    c.dias_prom
FROM alcance a
LEFT JOIN conv c USING (fecha_envio, canal)
ORDER BY a.fecha_envio, a.canal;
""")

con.execute(f"""
CREATE OR REPLACE TABLE reporte_paso AS
WITH alcance AS (
    SELECT canvas_step_nm, canvas_variation_nm, canal,
           count(DISTINCT msisdn) AS msisdn_impactados
    FROM envios
    WHERE fecha_envio >= DATE '{REPORTE_DESDE}'
      AND fecha_envio <  DATE '{REPORTE_HASTA}'
    GROUP BY 1, 2, 3
),
conv AS (
    SELECT canvas_step_nm, canvas_variation_nm, canal,
           count(DISTINCT msisdn) AS msisdn_convertidos
    FROM atribucion
    WHERE fecha_envio >= DATE '{REPORTE_DESDE}'
      AND fecha_envio <  DATE '{REPORTE_HASTA}'
    GROUP BY 1, 2, 3
)
SELECT
    a.canvas_step_nm, a.canvas_variation_nm, a.canal,
    a.msisdn_impactados,
    COALESCE(c.msisdn_convertidos, 0) AS msisdn_convertidos,
    round(100.0 * COALESCE(c.msisdn_convertidos, 0)
          / nullif(a.msisdn_impactados, 0), 2) AS tasa_pct
FROM alcance a
LEFT JOIN conv c USING (canvas_step_nm, canvas_variation_nm, canal)
ORDER BY tasa_pct DESC;
""")

for tabla, archivo in [("reporte_dia_canal", SALIDA_DIA_CANAL),
                       ("reporte_paso", SALIDA_PASO),
                       ("atribucion", SALIDA_DETALLE)]:
    con.execute(f"COPY {tabla} TO '{archivo}' (HEADER, DELIMITER ',')")

print("--- Reporte por dia y canal ---")
print(con.execute("SELECT * FROM reporte_dia_canal").df().to_string(index=False))
print("\n--- Reporte por paso del journey ---")
print(con.execute("SELECT * FROM reporte_paso").df().to_string(index=False), "\n")

empates = con.execute("""
SELECT count(*) FILTER (WHERE canales_mismo_dia > 1), count(*) FROM atribucion
""").fetchone()
if empates[0]:
    print(f"ATENCION: {empates[0]:,} de {empates[1]:,} atribuciones "
          f"({100 * empates[0] / empates[1]:.1f}%) tuvieron mas de un canal "
          f"el mismo dia.")
    print("El ganador lo decidio PRIORIDAD_CANAL, no la data. Si push y SMS "
          "salen juntos,\nel que quede segundo va a mostrar cero siempre.\n")

sin_atribuir = con.execute("""
SELECT count(*) FROM renovaciones r
WHERE NOT EXISTS (SELECT 1 FROM atribucion a
                  WHERE a.msisdn = r.msisdn AND a.fecha_conv = r.fecha_conv)
""").fetchone()[0]
print(f"Renovaciones sin envio previo en ventana: {sin_atribuir:,}")
print("(son tu linea base: gente que renovo sin haber sido tocada)")
```

---

## 11. Píldoras de conocimiento

Hallazgos de la exploración. Varios contradicen lo que la documentación o los
nombres de columna sugieren.

### Sobre las tablas de Braze

**1. `conversion_f` y `date_conversion_dt` son inservibles.** `conversion_f`
siempre vale 1 y `date_conversion_dt` coincide siempre con `date_send_dt`. Es
relleno del ETL, no atribución real de Braze. Una columna llamada `conversion_f`
que siempre vale 1 es una trampa para quien arme un dashboard encima sin
revisarla — vale la pena avisarle al equipo que mantiene el ETL.

**2. `event_tp` es el canal, no el tipo de evento.** En `webhook_fct` siempre
dice `webhook`. No sirve para filtrar envíos contra aperturas.

**3. `send_nbr` siempre vale 1.** Las tablas no vienen pre-agregadas: es una fila
por envío. Contar filas y sumar `send_nbr` son equivalentes.

**4. `braze_chnnl_webhook_fct` mezcla tráfico que no es de campaña.**
`step_name` toma los valores `SMS`, `WhatsApp`, `Other`, `Bridge` y `Zendesk`.
Sin filtrar, el denominador se contamina con tickets de soporte.

**5. `braze_profile_fct` acumula histórico, no parque activo.** Colombia aparece
con 76M perfiles postpago móvil sobre una población de ~52M. Sirve como universo
de referencia, pero usarlo de denominador diluye cualquier tasa con líneas que
ya no existen.

**6. El 62.6% de los perfiles guatemaltecos no tiene `bs_un` ni `bs_ln`.**
23.1M filas en blanco contra 3.1M marcadas como postpago móvil. Filtrar por esas
columnas borra siete de cada diez perfiles.

**7. `bs_un` a veces guarda un arreglo**, no un escalar — valores tipo
`["mobile","postpaid"]`. En Guatemala son 25 filas, en Colombia casi un millón.
Un `=` nunca va a ser confiable sobre esa columna.

**8. `fct_dt` en perfil es texto y snapshot diario.** Se filtra con comillas, no
con `DATE '...'`. Cada foto trae ~37M filas de Guatemala.

**9. `phone` y `msisdn` son el mismo dato** en dos presentaciones: los conteos
distintos dan idénticos.

**10. Una sola fila por `external_id` dentro de cada snapshot** — no hay fan-out
cuenta → teléfono. Esto sugiere que `external_user_id` identifica una línea, no
una cuenta.

**11. El par `external_id` → `msisdn` es estable.** Cero cambios entre los
snapshots del 1 de junio y el 31 de julio. Por eso se pueden apilar varios
snapshots con `arbitrary()` sin riesgo de ambigüedad.

**12. Match de identificadores: 92.39%** midiendo contra el snapshot del 1 de
junio. Lo que no empata no sesga la tasa —sin perfil no hay teléfono, así que
esas filas quedan fuera del numerador *y* del denominador—, solo reduce
cobertura. Con tres snapshots debería subir.

### Sobre Horus

**13. `fct_dt` en `dm_bi_sls_sttstcs_mnth` es el mes, no el día.** La cola de
+7 días cae en la partición del mes siguiente. Filtrar un solo mes deja la última
semana de envíos con cero conversiones aparentes, y nada avisa.

**14. Es una tabla de ventas, no de web analytics.** Captura la renovación se
haya hecho en app, web, agencia o call center.

### Sobre Trino

**15. `count(DISTINCT ...)` dentro de un `GROUP BY` revienta el cluster.** El
`MarkDistinctOperator` no puede pre-agregar por nodo y arrastra el conjunto
completo de valores únicos en memoria. Para explorar volumen usar
`approx_distinct()` (HyperLogLog, ~2% de error, memoria constante) y dejar
`count(DISTINCT)` para los números finales sobre conjuntos ya filtrados.

**16. Filtrar por la columna de partición, no por la lógica.** `dt` poda
archivos antes de leerlos; `date_send_dt` filtra después de escanear todo.

**17. `UNION ALL` y no `UNION`** cuando las ramas son mutuamente excluyentes.

**18. Sin filtro de país, cualquier consulta a las tablas globales trae toda la
región.** Guatemala es apenas el 13.3% de `braze_profile_fct`. En las fct de
canal el filtro es `instance_tp = 'gt'`; en perfil es `cntry_cd = 'gt'`.

### Sobre el cruce en Python

**19. CSV más números de teléfono es corrupción garantizada.** El lector infiere
que son números: `50212345678` se vuelve `5.0212345678e10`, los ceros a la
izquierda desaparecen, y una fila vacía convierte la columna entera a decimal
con `.0` pegado. Leer siempre como texto (`all_varchar=true` en DuckDB,
`dtype=str` en pandas).

**20. `NULL` nunca engancha en un JOIN.** `canvas_variation_nm` es `NULL` en los
pasos sin A/B test, y sin `COALESCE` esos pasos mostraban cero conversiones — con
números perfectamente plausibles. Es el tipo de bug que no se detecta mirando el
resultado.

**21. El desempate de canal decide el resultado.** Cuando push y SMS salen el
mismo día, el que pierda la prioridad muestra cero siempre. En pruebas, el 71%
de las atribuciones tuvo empate. Si esos canales disparan juntos, no se pueden
reportar por separado: o se unifican en una etiqueta `push+sms`, o se acepta que
uno se lleva todo el crédito por convención.

---

## 12. Pendientes y limitaciones

### Por confirmar

- **`SELECT DISTINCT fct_dt`** en `braze_profile_fct` — verificar que existan las
  tres fechas usadas y que la retención cubra junio.
- **Formato de `phone` / `msisdn` vs `msisdn_dd`** — comparar diez filas de cada
  lado para confirmar que los últimos 8 dígitos son el mismo plan de numeración.
- **Traslape de particiones en Horus** — si la de agosto trae eventos de junio,
  el datamart re-expresa y vale entender por qué (el `DISTINCT` lo cubre, pero
  es señal de algo).
- **Push y SMS: ¿cascada o simultáneos?** Es una pregunta de negocio y define si
  los canales se pueden reportar por separado.
- **Zona horaria** de cada fuente. Braze probablemente UTC, Horus hora local; con
  −6 de diferencia los envíos de la noche se corren de día.

### Limitaciones conocidas

- **Sin grupo de control**, el reporte mide correlación, no efecto. Las
  renovaciones ocurren por ciclo de facturación aunque no se mande nada: el día
  con más conversiones puede ser simplemente el día de corte. El número de
  "renovaciones sin envío previo" que imprime el script es el punto de partida
  para construirlo.
- **No existe una tabla de parque activo** identificada. Sin ella, el universo
  elegible sale de `braze_profile_fct` filtrado a `bs_un='mobile'` y
  `bs_ln='postpaid'`, que es un techo histórico y no clientes vigentes.
- **El mapeo teléfono-perfil se toma de tres fotos**, no punto en el tiempo. El
  riesgo es bajo porque el par resultó estable, pero no es cero.
- **`external_user_id` parece identificar línea y no cuenta**, contrario al
  supuesto inicial. Conviene confirmarlo con negocio antes de comunicar
  resultados en términos de "clientes".
