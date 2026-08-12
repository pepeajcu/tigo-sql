"""
Cruce de envios Braze (Trino) con renovaciones (Horus).

Entrada:
  envios.csv         msisdn, cuenta_id, fecha_envio, canal,
                     canvas_step_nm, canvas_variation_nm
  renovaciones.csv   msisdn, fecha_conv

Uso:  pip install duckdb  && python atribucion.py
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