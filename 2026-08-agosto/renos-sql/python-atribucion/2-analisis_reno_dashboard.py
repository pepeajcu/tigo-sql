"""
Journey de renovaciones postpago | Tigo Guatemala
Atribucion last-touch sobre envios de Braze vs renovaciones de Horus.

Salida: un dashboard .HTML autocontenido + los CSV intermedios.
No dibuja nada dentro del notebook.

Requisitos:  pip install duckdb plotly pandas
"""

import os
import re
import json
import datetime as dt

import duckdb
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

# =============================================================================
# 1. CONFIGURACION
# =============================================================================

BASE = os.environ.get("RENO_BASE", "C:/Users/datatigo/Desktop/tigo-sql/tigo-sql/2026-08-agosto/renos-sql/dataset/produ")

ENVIOS_CSV = os.environ.get("ENVIOS_CSV", f"{BASE}/envios_produ.csv")
RENOVACIONES_CSV = os.environ.get("RENOVACIONES_CSV", f"{BASE}/reno_produ.csv")
OUT_DIR = os.environ.get("OUT_DIR", f"{BASE}/output")

# AUTO_RANGO=True toma el periodo del propio archivo y evita el error mas comun:
# correr data de un mes nuevo con las fechas del mes anterior todavia clavadas,
# lo que deja la tabla de atribucion vacia sin decir por que.
AUTO_RANGO = True

REPORTE_DESDE = "2026-06-01"          # se ignoran si AUTO_RANGO = True
REPORTE_HASTA = "2026-07-10"          # exclusivo

TOPE_VENTANA_DIAS = 7                 # vigencia del ultimo envio del journey
MIN_N_DIMENSION = 3                   # piso para mostrar un corte por dimension

PRIORIDAD_CANAL = {"whatsapp": 3, "sms": 2, "push": 1, "email": 4, "inapp": 5}

os.makedirs(OUT_DIR, exist_ok=True)

SALIDA_DIA_CANAL = f"{OUT_DIR}/reporte_dia_canal.csv"
SALIDA_PASO      = f"{OUT_DIR}/reporte_paso_journey.csv"
SALIDA_RUTA      = f"{OUT_DIR}/reporte_ruta_ab.csv"
SALIDA_GEO       = f"{OUT_DIR}/reporte_geografia.csv"
SALIDA_PLAN      = f"{OUT_DIR}/reporte_plan.csv"
SALIDA_VENTA     = f"{OUT_DIR}/reporte_canal_venta.csv"
SALIDA_DETALLE   = f"{OUT_DIR}/detalle_atribucion.csv"
SALIDA_HTML      = f"{OUT_DIR}/reporte_renovaciones.html"

LOGO_URL = ("https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/"
            "Logo_Tigo.svg/1280px-Logo_Tigo.svg.png")

# =============================================================================
# 2. INGESTA Y NORMALIZACION
# =============================================================================

con = duckdb.connect()

# fecha_envio viene como '2026-06-07 16:00:00.000 -0600'. Un TRY_CAST directo a
# DATE devuelve NULL por el offset y vacia la tabla completa; nos quedamos con
# los primeros 10 caracteres, que ya son la fecha local de Guatemala.
con.execute("""
CREATE OR REPLACE MACRO f_fecha(x) AS COALESCE(
    TRY_CAST(substr(CAST(x AS VARCHAR), 1, 10) AS DATE),
    CAST(TRY_CAST(substr(CAST(x AS VARCHAR), 1, 19) AS TIMESTAMP) AS DATE)
);
""")

# Los envios traen el numero con codigo de pais (502xxxxxxxx) y las
# renovaciones sin el. Los ultimos 8 digitos son el terreno comun.
con.execute("""
CREATE OR REPLACE MACRO f_msisdn(x) AS
    right(regexp_replace(CAST(x AS VARCHAR), '[^0-9]', '', 'g'), 8);
""")

_case_prioridad = ("CASE canal\n" + "\n".join(
    f"    WHEN '{k}' THEN {v}" for k, v in PRIORIDAD_CANAL.items()) + "\n    ELSE 99 END")

con.execute(f"""
CREATE OR REPLACE TABLE envios_raw AS
SELECT * FROM read_csv('{ENVIOS_CSV}', all_varchar = true);
""")

con.execute(f"""
CREATE OR REPLACE TABLE reno_raw AS
SELECT * FROM read_csv('{RENOVACIONES_CSV}', all_varchar = true);
""")

con.execute("""
CREATE OR REPLACE TABLE envios AS
SELECT
    f_msisdn(msisdn)                                AS msisdn,
    cuenta_id,
    f_fecha(fecha_envio)                            AS fecha_envio,
    lower(trim(canal))                              AS canal,
    COALESCE(NULLIF(trim(canvas_step_nm), ''), '(sin paso)')          AS canvas_step_nm,
    COALESCE(NULLIF(trim(canvas_variation_nm), ''), '(sin variante)') AS canvas_variation_nm,
    campaign_id
FROM envios_raw
WHERE length(f_msisdn(msisdn)) = 8
  AND f_fecha(fecha_envio) IS NOT NULL;
""")

# upper() en las dimensiones de texto para que 'Guatemala' y 'GUATEMALA' no
# abran dos filas distintas.
con.execute("""
CREATE OR REPLACE TABLE renovaciones AS
SELECT DISTINCT
    f_msisdn(msisdn)            AS msisdn,
    f_fecha(fecha_conv)         AS fecha_conv,
    COALESCE(NULLIF(upper(trim(channel)), ''), 'SIN DATO')       AS canal_venta,
    COALESCE(NULLIF(upper(trim(ciudad)), ''), 'SIN DATO')        AS ciudad,
    COALESCE(NULLIF(upper(trim(departamento)), ''), 'SIN DATO')  AS departamento,
    COALESCE(NULLIF(upper(trim(bfr_vc_nm)), ''), 'SIN DATO')     AS plan_nm,
    COALESCE(NULLIF(upper(trim(bfr_dt_nm)), ''), 'SIN DATO')     AS plan_detalle
FROM reno_raw
WHERE length(f_msisdn(msisdn)) = 8
  AND f_fecha(fecha_conv) IS NOT NULL;
""")

_re = con.execute("SELECT min(fecha_envio), max(fecha_envio), count(*) FROM envios").fetchone()
_rr = con.execute("SELECT min(fecha_conv), max(fecha_conv), count(*) FROM renovaciones").fetchone()

if _re[2] == 0:
    raise SystemExit(f"No quedo ni un envio valido despues de limpiar.\n"
                     f"Revisa {ENVIOS_CSV}: msisdn de 8 digitos y fecha_envio legible.")
if _rr[2] == 0:
    raise SystemExit(f"No quedo ni una renovacion valida despues de limpiar.\n"
                     f"Revisa {RENOVACIONES_CSV}: msisdn de 8 digitos y fecha_conv legible.")

if AUTO_RANGO:
    REPORTE_DESDE = str(min(_re[0], _rr[0]))
    REPORTE_HASTA = str(max(_re[1], _rr[1]) + dt.timedelta(days=1))

print(f"Envios       {_re[2]:>8,}  de {_re[0]} a {_re[1]}")
print(f"Renovaciones {_rr[2]:>8,}  de {_rr[0]} a {_rr[1]}")
print(f"Periodo      {REPORTE_DESDE} a {REPORTE_HASTA}"
      f"{'  (automatico)' if AUTO_RANGO else '  (fijo en la config)'}\n")

# Base de comparacion: todas las renovaciones del periodo, tocadas o no. Sirve
# de denominador para saber si el journey sobre o sub-representa un segmento.
con.execute(f"""
CREATE OR REPLACE TABLE base_reno AS
SELECT * FROM renovaciones
WHERE fecha_conv >= DATE '{REPORTE_DESDE}' AND fecha_conv < DATE '{REPORTE_HASTA}';
""")

# =============================================================================
# 3. VENTANAS Y ATRIBUCION LAST-TOUCH
# =============================================================================

# Cada envio queda vigente hasta el siguiente envio del mismo msisdn; el ultimo
# vive TOPE_VENTANA_DIAS. Asi ninguna renovacion se cuenta dos veces.
con.execute(f"""
CREATE OR REPLACE TABLE ventanas AS
WITH fechas AS (SELECT DISTINCT msisdn, fecha_envio FROM envios)
SELECT
    msisdn,
    fecha_envio,
    COALESCE(
        lead(fecha_envio) OVER (PARTITION BY msisdn ORDER BY fecha_envio),
        fecha_envio + INTERVAL {TOPE_VENTANA_DIAS} DAY
    ) AS fin_ventana
FROM fechas;
""")

con.execute(f"""
CREATE OR REPLACE TABLE atribucion AS
WITH candidatos AS (
    SELECT
        r.msisdn, r.fecha_conv,
        r.canal_venta, r.ciudad, r.departamento, r.plan_nm, r.plan_detalle,
        e.cuenta_id, e.fecha_envio, e.canal,
        e.canvas_step_nm, e.canvas_variation_nm,
        date_diff('day', e.fecha_envio, r.fecha_conv) AS dias_al_convertir,
        count(*) OVER (PARTITION BY r.msisdn, r.fecha_conv, e.fecha_envio) AS canales_mismo_dia,
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
SELECT c.* EXCLUDE (rn),
       (SELECT count(*) FROM envios e2
         WHERE e2.msisdn = c.msisdn AND e2.fecha_envio <= c.fecha_conv) AS toques_previos
FROM candidatos c
WHERE rn = 1;
""")

con.execute(f"""
CREATE OR REPLACE VIEW atr AS
SELECT * FROM atribucion
WHERE fecha_envio >= DATE '{REPORTE_DESDE}' AND fecha_envio < DATE '{REPORTE_HASTA}';
""")

con.execute(f"""
CREATE OR REPLACE VIEW env AS
SELECT * FROM envios
WHERE fecha_envio >= DATE '{REPORTE_DESDE}' AND fecha_envio < DATE '{REPORTE_HASTA}';
""")

_d = con.execute("""
SELECT (SELECT count(*) FROM atribucion) AS total,
       (SELECT count(*) FROM atr)        AS en_periodo,
       (SELECT count(DISTINCT msisdn) FROM envios
         WHERE msisdn IN (SELECT msisdn FROM renovaciones)) AS msisdn_cruzados,
       (SELECT count(DISTINCT msisdn) FROM envios)          AS msisdn_envio
""").fetchone()

if _d[1] == 0:
    _ej_e = con.execute("SELECT msisdn FROM envios LIMIT 3").df().msisdn.tolist()
    _ej_r = con.execute("SELECT msisdn FROM renovaciones LIMIT 3").df().msisdn.tolist()
    raise SystemExit(
        "\nCERO renovaciones atribuidas. El reporte no se puede armar. Revisa en este orden:\n\n"
        f"  1. Cruce de numeros: solo {_d[2]:,} de {_d[3]:,} msisdn impactados aparecen\n"
        f"     en la tabla de renovaciones. Si es 0, el formato no coincide.\n"
        f"     Ejemplo envios     -> {_ej_e}\n"
        f"     Ejemplo renovacion -> {_ej_r}\n\n"
        f"  2. Periodo: se atribuyeron {_d[0]:,} renovaciones en total, pero 0 caen dentro\n"
        f"     de {REPORTE_DESDE} a {REPORTE_HASTA}. Pon AUTO_RANGO = True o ajusta las fechas.\n\n"
        f"  3. Ventana: TOPE_VENTANA_DIAS = {TOPE_VENTANA_DIAS}. Si las renovaciones ocurren\n"
        f"     mucho despues del ultimo envio, ninguna cae dentro.\n")

print(f"Atribuidas   {_d[1]:>8,}  ({_d[2]:,} de {_d[3]:,} msisdn cruzan con renovaciones)\n")

# =============================================================================
# 4. REPORTES BASE: DIA / CANAL / PASO
# =============================================================================

con.execute("""
CREATE OR REPLACE TABLE reporte_dia_canal AS
WITH alcance AS (
    SELECT fecha_envio, canal,
           count(DISTINCT msisdn)    AS msisdn_impactados,
           count(DISTINCT cuenta_id) AS cuentas_impactadas
    FROM env GROUP BY 1, 2
),
conv AS (
    SELECT fecha_envio, canal,
           count(DISTINCT msisdn) AS msisdn_convertidos,
           count(*)               AS renovaciones,
           round(avg(dias_al_convertir), 2) AS dias_prom
    FROM atr GROUP BY 1, 2
)
SELECT a.fecha_envio,
       dayname(a.fecha_envio) AS dia_semana,
       a.canal,
       a.msisdn_impactados,
       a.cuentas_impactadas,
       COALESCE(c.msisdn_convertidos, 0) AS msisdn_convertidos,
       COALESCE(c.renovaciones, 0)       AS renovaciones,
       round(100.0 * COALESCE(c.msisdn_convertidos, 0)
             / nullif(a.msisdn_impactados, 0), 2) AS tasa_pct,
       c.dias_prom
FROM alcance a LEFT JOIN conv c USING (fecha_envio, canal)
ORDER BY a.fecha_envio, a.canal;
""")

# "Dia 12" no va despues de "Dia 3" alfabeticamente: el orden real del journey
# es la fecha en que salio cada paso.
con.execute("""
CREATE OR REPLACE TABLE orden_pasos AS
SELECT canvas_step_nm,
       min(fecha_envio) AS primera_fecha,
       dense_rank() OVER (ORDER BY min(fecha_envio), canvas_step_nm) AS paso_idx
FROM envios GROUP BY 1;
""")

con.execute("""
CREATE OR REPLACE TABLE reporte_paso AS
WITH alcance AS (
    SELECT canvas_step_nm, canvas_variation_nm, canal,
           count(DISTINCT msisdn) AS msisdn_impactados
    FROM env GROUP BY 1, 2, 3
),
conv AS (
    SELECT canvas_step_nm, canvas_variation_nm, canal,
           count(DISTINCT msisdn) AS msisdn_convertidos,
           round(avg(dias_al_convertir), 2) AS dias_prom
    FROM atr GROUP BY 1, 2, 3
)
SELECT a.canvas_step_nm, a.canvas_variation_nm, a.canal,
       o.paso_idx, o.primera_fecha,
       a.msisdn_impactados,
       COALESCE(c.msisdn_convertidos, 0) AS msisdn_convertidos,
       round(100.0 * COALESCE(c.msisdn_convertidos, 0)
             / nullif(a.msisdn_impactados, 0), 2) AS tasa_pct,
       c.dias_prom
FROM alcance a
LEFT JOIN conv c USING (canvas_step_nm, canvas_variation_nm, canal)
JOIN orden_pasos o USING (canvas_step_nm)
ORDER BY o.paso_idx, a.canal;
""")

# =============================================================================
# 5. RUTAS DEL JOURNEY (el A/B que ya viene armado en la data)
# =============================================================================

# La secuencia de pasos que recibio cada msisdn identifica su rama. Se etiquetan
# por tamano (A la mas grande) para no amarrar el codigo a nombres de paso.
con.execute("""
CREATE OR REPLACE TABLE ruta_msisdn AS
SELECT msisdn,
       string_agg(canvas_step_nm, ' > ' ORDER BY fecha_envio, canvas_step_nm) AS ruta_key,
       count(*) AS pasos_recibidos
FROM envios GROUP BY 1;
""")

con.execute("""
CREATE OR REPLACE TABLE rutas AS
SELECT ruta_key,
       'Ruta ' || chr(64 + CAST(row_number() OVER (ORDER BY count(*) DESC, ruta_key) AS INT)) AS ruta,
       count(*) AS msisdn_en_ruta
FROM ruta_msisdn GROUP BY 1;
""")

con.execute("""
CREATE OR REPLACE TABLE reporte_ruta AS
WITH alc AS (
    SELECT ru.ruta, ru.ruta_key, count(DISTINCT rm.msisdn) AS msisdn_impactados
    FROM ruta_msisdn rm JOIN rutas ru USING (ruta_key) GROUP BY 1, 2
),
cv AS (
    SELECT ru.ruta,
           count(DISTINCT a.msisdn) AS msisdn_convertidos,
           round(avg(a.dias_al_convertir), 2) AS dias_prom,
           round(avg(a.toques_previos), 2)    AS toques_prom
    FROM atr a JOIN ruta_msisdn rm USING (msisdn) JOIN rutas ru USING (ruta_key)
    GROUP BY 1
)
SELECT alc.ruta, alc.ruta_key, alc.msisdn_impactados,
       COALESCE(cv.msisdn_convertidos, 0) AS msisdn_convertidos,
       round(100.0 * COALESCE(cv.msisdn_convertidos, 0)
             / nullif(alc.msisdn_impactados, 0), 2) AS tasa_pct,
       cv.dias_prom, cv.toques_prom
FROM alc LEFT JOIN cv USING (ruta) ORDER BY alc.ruta;
""")

# =============================================================================
# 6. DIMENSIONES DEL LADO DE LA RENOVACION
# =============================================================================
# ciudad, departamento, plan y canal de venta solo existen en el registro de la
# renovacion: no hay forma de conocerlos para quien fue impactado y no renovo.
# Por eso aqui no hay "tasa de conversion por departamento". Lo que si se puede
# medir es composicion + indice contra la base de renovaciones del periodo:
#   indice = (% del segmento en lo atribuido / % del segmento en la base) * 100
# 100 = el journey convierte ese segmento en la misma proporcion que el mercado.


def tabla_dimension(col, salida):
    con.execute(f"""
    CREATE OR REPLACE TABLE tmp_dim AS
    WITH a AS (
        SELECT {col} AS valor, count(*) AS conv_atribuidas
        FROM atr GROUP BY 1
    ),
    b AS (
        SELECT {col} AS valor, count(*) AS reno_base
        FROM base_reno GROUP BY 1
    ),
    tot AS (SELECT (SELECT count(*) FROM atr) ta, (SELECT count(*) FROM base_reno) tb)
    SELECT COALESCE(a.valor, b.valor) AS valor,
           COALESCE(a.conv_atribuidas, 0) AS conv_atribuidas,
           COALESCE(b.reno_base, 0)       AS reno_base,
           round(100.0 * COALESCE(a.conv_atribuidas, 0) / nullif(tot.ta, 0), 2) AS pct_atribuido,
           round(100.0 * COALESCE(b.reno_base, 0)       / nullif(tot.tb, 0), 2) AS pct_base,
           round(100.0 * (COALESCE(a.conv_atribuidas, 0) / nullif(tot.ta, 0))
                       / nullif(COALESCE(b.reno_base, 0) / nullif(tot.tb, 0), 0), 0) AS indice
    FROM a FULL OUTER JOIN b USING (valor) CROSS JOIN tot
    ORDER BY conv_atribuidas DESC, reno_base DESC;
    """)
    df = con.execute("SELECT * FROM tmp_dim").df()
    df.to_csv(salida, index=False)
    return df


df_geo   = tabla_dimension("departamento", SALIDA_GEO)
df_ciu   = tabla_dimension("ciudad", f"{OUT_DIR}/reporte_ciudad.csv")
df_plan  = tabla_dimension("plan_nm", SALIDA_PLAN)
df_det   = tabla_dimension("plan_detalle", f"{OUT_DIR}/reporte_plan_detalle.csv")
df_venta = tabla_dimension("canal_venta", SALIDA_VENTA)

# Cruce canal de marketing (lo que mandamos) x canal de venta (donde renovo).
df_cruce = con.execute("""
SELECT canal, canal_venta, count(*) AS conv
FROM atr GROUP BY 1, 2 ORDER BY 1, 3 DESC
""").df()

df_latencia = con.execute("""
SELECT dias_al_convertir, count(*) AS conv
FROM atr GROUP BY 1 ORDER BY 1
""").df()

df_toques = con.execute("""
SELECT toques_previos, count(*) AS conv
FROM atr GROUP BY 1 ORDER BY 1
""").df()

df_dia   = con.execute("SELECT * FROM reporte_dia_canal ORDER BY fecha_envio, canal").df()
df_paso  = con.execute("SELECT * FROM reporte_paso").df()
df_ruta  = con.execute("SELECT * FROM reporte_ruta").df()
df_pasos_orden = con.execute("SELECT * FROM orden_pasos ORDER BY paso_idx").df()

DIAS_ES = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
           "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado", "Sunday": "Domingo"}

# Cada paso del journey salio en una sola fecha, asi que fecha y paso son la
# misma fila: una tabla en lugar de dos.
df_tabla = con.execute("""
SELECT paso_idx, canvas_step_nm, canal, primera_fecha,
       dayname(primera_fecha) AS dia_semana,
       msisdn_impactados, msisdn_convertidos, tasa_pct, dias_prom
FROM reporte_paso ORDER BY paso_idx
""").df()
df_tabla["dia_semana"] = df_tabla["dia_semana"].map(DIAS_ES).fillna(df_tabla["dia_semana"])
df_tabla.to_csv(f"{OUT_DIR}/reporte_paso_fecha.csv", index=False)

df_acum = con.execute("""
SELECT fecha_conv,
       sum(conv) OVER (ORDER BY fecha_conv) AS acumulado
FROM (SELECT fecha_conv, count(*) AS conv FROM atr GROUP BY 1)
ORDER BY fecha_conv
""").df()

# =============================================================================
# 7. KPIs Y CONTROL DE CALIDAD
# =============================================================================

kpi = con.execute("""
SELECT
    (SELECT count(DISTINCT msisdn) FROM env)                  AS impactados,
    (SELECT count(*) FROM env)                                AS envios_totales,
    (SELECT count(*) FROM atr)                                AS conversiones,
    (SELECT count(DISTINCT msisdn) FROM atr)                  AS msisdn_convertidos,
    (SELECT count(*) FROM base_reno)                          AS reno_periodo,
    (SELECT round(avg(dias_al_convertir), 1) FROM atr)        AS dias_prom,
    (SELECT round(avg(toques_previos), 1) FROM atr)           AS toques_prom
""").df().iloc[0].to_dict()

kpi["tasa_global"] = round(100 * kpi["msisdn_convertidos"] / kpi["impactados"], 2) if kpi["impactados"] else 0
kpi["share_mercado"] = round(100 * kpi["conversiones"] / kpi["reno_periodo"], 2) if kpi["reno_periodo"] else 0

qc = con.execute(f"""
SELECT
    (SELECT count(*) FROM envios_raw)  AS envios_leidos,
    (SELECT count(*) FROM envios)      AS envios_validos,
    (SELECT count(*) FROM reno_raw)    AS reno_leidas,
    (SELECT count(*) FROM renovaciones) AS reno_validas,
    (SELECT count(DISTINCT msisdn) FROM envios) AS msisdn_envio,
    (SELECT count(DISTINCT msisdn) FROM envios
      WHERE msisdn IN (SELECT msisdn FROM renovaciones)) AS msisdn_con_reno,
    (SELECT count(*) FROM atr WHERE canales_mismo_dia > 1) AS empates,
    (SELECT count(*) FROM renovaciones r
      WHERE r.msisdn IN (SELECT msisdn FROM envios)
        AND NOT EXISTS (SELECT 1 FROM atribucion a
                        WHERE a.msisdn = r.msisdn AND a.fecha_conv = r.fecha_conv)) AS reno_fuera_ventana
""").df().iloc[0].to_dict()

for tabla, archivo in [("reporte_dia_canal", SALIDA_DIA_CANAL),
                       ("reporte_paso", SALIDA_PASO),
                       ("reporte_ruta", SALIDA_RUTA),
                       ("atribucion", SALIDA_DETALLE)]:
    con.execute(f"COPY {tabla} TO '{archivo}' (HEADER, DELIMITER ',')")

# =============================================================================
# 8. ESTILO DE GRAFICAS
# =============================================================================

AZUL   = "#112CB7"
AZUL_2 = "#7C8AD9"
AZUL_3 = "#C7CEEF"
AZUL_4 = "#EDF0FB"
TINTA  = "#0A0A0A"
GRIS   = "#767680"
REGLA  = "#E7E7E9"

SANS = "Geist, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
MONO = "'Geist Mono', 'SF Mono', ui-monospace, 'JetBrains Mono', monospace"

COLOR_CANAL = {"sms": AZUL, "whatsapp": AZUL_2, "push": AZUL_3, "email": "#9AA3B2", "inapp": "#B9BFCC"}

pio.templates["tigo"] = go.layout.Template(layout=dict(
    font=dict(family=SANS, size=13, color=TINTA),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=38, b=10),
    colorway=[AZUL, AZUL_2, AZUL_3, GRIS],
    hoverlabel=dict(bgcolor=TINTA, bordercolor=TINTA,
                    font=dict(color="#FFFFFF", family=SANS, size=12)),
    xaxis=dict(showgrid=False, zeroline=False, linecolor=REGLA, linewidth=1,
               ticks="outside", tickcolor=REGLA, ticklen=4,
               tickfont=dict(family=MONO, size=11, color=GRIS)),
    yaxis=dict(showgrid=True, gridcolor="#F2F2F4", zeroline=False,
               linecolor="rgba(0,0,0,0)",
               tickfont=dict(family=MONO, size=11, color=GRIS)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                bgcolor="rgba(0,0,0,0)",
                font=dict(family=MONO, size=11, color=GRIS)),
    showlegend=False,
))
pio.templates.default = "tigo"

FIGS = {}


def guardar(nombre, fig, alto=380):
    fig.update_layout(height=alto, template="tigo")
    FIGS[nombre] = fig


# --- 8.1 Signature: la regla del journey, cada envio ubicado en su fecha real
pasos = df_pasos_orden.merge(
    df_paso.groupby("canvas_step_nm", as_index=False).agg(
        impactados=("msisdn_impactados", "sum"),
        convertidos=("msisdn_convertidos", "sum"),
        canal=("canal", "first")),
    on="canvas_step_nm", how="left")
pasos["y"] = pasos["canal"].map({"sms": 1, "whatsapp": 0}).fillna(0.5)

fig = go.Figure()
fig.add_shape(type="line", x0=pasos.primera_fecha.min(), x1=pasos.primera_fecha.max(),
              y0=1, y1=1, line=dict(color=REGLA, width=1))
fig.add_shape(type="line", x0=pasos.primera_fecha.min(), x1=pasos.primera_fecha.max(),
              y0=0, y1=0, line=dict(color=REGLA, width=1))
for canal, sub in pasos.groupby("canal"):
    fig.add_trace(go.Scatter(
        x=sub.primera_fecha, y=sub.y, mode="markers+text",
        marker=dict(size=sub.convertidos.fillna(0) * 2.6 + 12, color=COLOR_CANAL.get(canal, GRIS),
                    line=dict(color="#FFFFFF", width=2)),
        text=sub.convertidos.fillna(0).astype(int).astype(str),
        textposition="middle center",
        textfont=dict(family=MONO, size=10, color="#FFFFFF"),
        customdata=sub[["canvas_step_nm", "impactados", "convertidos"]],
        hovertemplate="<b>%{customdata[0]}</b><br>Impactados %{customdata[1]:,}"
                      "<br>Convertidos %{customdata[2]:,}<extra></extra>"))
for _, r in pasos.iterrows():
    fig.add_annotation(x=r.primera_fecha, y=r.y, text=r.canvas_step_nm,
                       yshift=30 if r.y == 1 else -30, showarrow=False,
                       font=dict(family=MONO, size=10, color=GRIS))
fig.update_yaxes(showgrid=False, showticklabels=True, range=[-0.7, 1.7],
                 tickmode="array", tickvals=[0, 1], ticktext=["WHATSAPP", "SMS"],
                 tickfont=dict(family=MONO, size=11, color=TINTA))
fig.update_xaxes(showgrid=False, tickformat="%d %b", dtick=86400000 * 5)
guardar("ruler", fig, 320)

# --- 8.2 Renovaciones atribuidas por canal
d = con.execute("SELECT canal, count(*) c FROM atr GROUP BY 1 ORDER BY c").df()
fig = go.Figure(go.Bar(x=d.c, y=d.canal.str.upper(), orientation="h",
                       marker_color=[COLOR_CANAL.get(c, GRIS) for c in d.canal],
                       text=d.c, textposition="outside",
                       textfont=dict(family=MONO, size=13, color=TINTA),
                       hovertemplate="%{y}: %{x} renovaciones<extra></extra>"))
fig.update_xaxes(showgrid=False, showticklabels=False,
                 range=[0, d.c.max() * 1.22], linecolor="rgba(0,0,0,0)", ticks="")
fig.update_yaxes(showgrid=False, tickfont=dict(family=MONO, size=12, color=TINTA))
guardar("canal", fig, 220)

# --- 8.3 Impactados vs convertidos por paso (horizontal: las etiquetas de
#         paso son largas y en vertical se encimaban)
p = pasos.sort_values("paso_idx", ascending=False)
etiqueta = p.paso_idx.astype(int).astype(str) + ".  " + p.canvas_step_nm
fig = go.Figure()
fig.add_trace(go.Bar(y=etiqueta, x=p.impactados, orientation="h", name="Impactados",
                     marker_color=AZUL_4, text=p.impactados, textposition="outside",
                     textfont=dict(family=MONO, size=11, color=GRIS),
                     hovertemplate="Impactados %{x:,}<extra></extra>"))
fig.add_trace(go.Bar(y=etiqueta, x=p.convertidos, orientation="h", name="Convertidos",
                     marker_color=AZUL, text=p.convertidos, textposition="outside",
                     textfont=dict(family=MONO, size=12, color=AZUL),
                     hovertemplate="Convertidos %{x:,}<extra></extra>"))
fig.update_layout(barmode="overlay", showlegend=True, bargap=0.42)
fig.update_xaxes(showgrid=False, showticklabels=False, ticks="",
                 linecolor="rgba(0,0,0,0)", range=[0, p.impactados.max() * 1.18])
fig.update_yaxes(showgrid=False, tickfont=dict(family=MONO, size=11, color=TINTA))
guardar("paso", fig, 460)

# --- 8.4 Tasa de conversion por paso
tasa = (100 * p.convertidos / p.impactados).round(2)
fig = go.Figure(go.Bar(
    y=etiqueta, x=tasa, orientation="h",
    marker_color=[COLOR_CANAL.get(c, GRIS) for c in p.canal],
    text=tasa.round(2).astype(str) + "%", textposition="outside",
    textfont=dict(family=MONO, size=12, color=TINTA),
    customdata=p[["impactados", "convertidos"]],
    hovertemplate="%{y}<br>%{customdata[1]} de %{customdata[0]} msisdn<extra></extra>"))
fig.update_xaxes(ticksuffix="%", showgrid=False, showticklabels=False, ticks="",
                 linecolor="rgba(0,0,0,0)", range=[0, tasa.max() * 1.3])
fig.update_yaxes(showgrid=False, tickfont=dict(family=MONO, size=11, color=TINTA))
guardar("tasa_paso", fig, 460)

# --- 8.5 Rutas A/B
r = df_ruta.copy()
fig = go.Figure(go.Bar(
    x=r.ruta, y=r.tasa_pct, marker_color=[AZUL, AZUL_2, AZUL_3][:len(r)],
    text=r.tasa_pct.astype(str) + "%", textposition="outside",
    textfont=dict(family=MONO, size=14, color=TINTA),
    customdata=r[["msisdn_impactados", "msisdn_convertidos"]],
    hovertemplate="%{x}<br>%{customdata[1]} de %{customdata[0]} msisdn<extra></extra>"))
fig.update_yaxes(ticksuffix="%", range=[0, max(r.tasa_pct.max() * 1.35, 1)])
fig.update_xaxes(tickfont=dict(family=MONO, size=12, color=TINTA))
guardar("ruta", fig, 300)

# --- 8.6 Latencia
fig = go.Figure(go.Bar(x=df_latencia.dias_al_convertir, y=df_latencia.conv,
                       marker_color=AZUL, text=df_latencia.conv, textposition="outside",
                       textfont=dict(family=MONO, size=11, color=TINTA),
                       hovertemplate="Dia %{x}: %{y} renovaciones<extra></extra>"))
fig.update_xaxes(dtick=1, title=dict(text="dias entre el envio y la renovacion",
                                     font=dict(family=MONO, size=11, color=GRIS)))
fig.update_yaxes(range=[0, df_latencia.conv.max() * 1.22])
guardar("latencia", fig, 300)

# --- 8.7 Toques previos
fig = go.Figure(go.Bar(x=df_toques.toques_previos, y=df_toques.conv,
                       marker_color=AZUL_2, text=df_toques.conv, textposition="outside",
                       textfont=dict(family=MONO, size=11, color=TINTA),
                       hovertemplate="%{x} impactos: %{y} renovaciones<extra></extra>"))
fig.update_xaxes(dtick=1, title=dict(text="impactos recibidos antes de renovar",
                                     font=dict(family=MONO, size=11, color=GRIS)))
fig.update_yaxes(range=[0, df_toques.conv.max() * 1.22])
guardar("toques", fig, 300)

# --- 8.8 Acumulado
fig = go.Figure(go.Scatter(x=df_acum.fecha_conv, y=df_acum.acumulado, mode="lines",
                           line=dict(color=AZUL, width=2.5, shape="hv"),
                           fill="tozeroy", fillcolor="rgba(17,44,183,0.06)",
                           hovertemplate="%{x|%d %b}: %{y} acumuladas<extra></extra>"))
fig.update_xaxes(tickformat="%d %b")
guardar("acum", fig, 300)

# --- 8.9 Departamento: indice contra la base
g = df_geo[df_geo.conv_atribuidas >= MIN_N_DIMENSION].sort_values("indice")
if g.empty:   # con pocas conversiones ningun departamento alcanza el piso
    g = df_geo[df_geo.conv_atribuidas > 0].nlargest(10, "conv_atribuidas").sort_values("indice")
fig = go.Figure(go.Bar(
    x=g.indice - 100, y=g.valor.str.title(), orientation="h", base=100,
    marker_color=[AZUL if v >= 100 else AZUL_3 for v in g.indice],
    text=g.indice.astype(int).astype(str), textposition="outside",
    textfont=dict(family=MONO, size=11, color=TINTA),
    customdata=g[["conv_atribuidas", "pct_atribuido", "pct_base"]],
    hovertemplate="%{y}<br>%{customdata[0]} renovaciones atribuidas"
                  "<br>%{customdata[1]}% del journey vs %{customdata[2]}% de la base<extra></extra>"))
fig.add_vline(x=100, line=dict(color=TINTA, width=1, dash="dot"))
fig.update_xaxes(showgrid=False, range=[0, (g.indice.max() if len(g) else 200) * 1.15],
                 title=dict(text="indice vs base de renovaciones (100 = igual)",
                            font=dict(family=MONO, size=11, color=GRIS)))
fig.update_yaxes(showgrid=False, tickfont=dict(family=SANS, size=12, color=TINTA))
guardar("geo", fig, 300)

# --- 8.10 Ciudades
c = df_ciu[df_ciu.conv_atribuidas > 0].nlargest(10, "conv_atribuidas").sort_values("conv_atribuidas")
fig = go.Figure(go.Bar(x=c.conv_atribuidas, y=c.valor.str.title(), orientation="h",
                       marker_color=AZUL, text=c.conv_atribuidas, textposition="outside",
                       textfont=dict(family=MONO, size=11, color=TINTA),
                       hovertemplate="%{y}: %{x} renovaciones<extra></extra>"))
fig.update_xaxes(showgrid=False, showticklabels=False, ticks="",
                 linecolor="rgba(0,0,0,0)", range=[0, c.conv_atribuidas.max() * 1.2])
fig.update_yaxes(showgrid=False, tickfont=dict(family=SANS, size=12, color=TINTA))
guardar("ciudad", fig, 360)

# --- 8.11 Plan contratado (detalle) top 8
pl = df_det[df_det.conv_atribuidas > 0].nlargest(8, "conv_atribuidas").sort_values("pct_atribuido")
fig = go.Figure()
for _, r in pl.iterrows():
    fig.add_shape(type="line", x0=r.pct_base, x1=r.pct_atribuido, y0=r.valor, y1=r.valor,
                  line=dict(color=AZUL_3, width=2))
fig.add_trace(go.Scatter(x=pl.pct_base, y=pl.valor, mode="markers", name="Base de renovaciones (11 761)",
                         marker=dict(size=11, color="#FFFFFF", line=dict(color=GRIS, width=1.5)),
                         hovertemplate="Base: %{x}%<extra></extra>"))
fig.add_trace(go.Scatter(x=pl.pct_atribuido, y=pl.valor, mode="markers+text", name="Journey (55)",
                         marker=dict(size=13, color=AZUL),
                         text=pl.pct_atribuido.round(1).astype(str) + "%", textposition="middle right",
                         textfont=dict(family=MONO, size=11, color=TINTA),
                         hovertemplate="Journey: %{x}%<extra></extra>"))
fig.update_layout(showlegend=True)
fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#F2F2F4",
                 range=[0, max(pl.pct_atribuido.max(), pl.pct_base.max()) * 1.35])
fig.update_yaxes(showgrid=False, tickfont=dict(family=MONO, size=11, color=TINTA))
guardar("plan", fig, 400)

# --- 8.12 Canal de venta: journey vs base
v = df_venta.sort_values("pct_base", ascending=True)
v = v.assign(lab=v.valor.str.title())
fig = go.Figure()
for _, r in v.iterrows():
    fig.add_shape(type="line", x0=r.pct_base, x1=r.pct_atribuido, y0=r.lab, y1=r.lab,
                  line=dict(color=AZUL_3, width=2))
fig.add_trace(go.Scatter(x=v.pct_base, y=v.lab, mode="markers", name="Base de renovaciones (11 761)",
                         marker=dict(size=11, color="#FFFFFF", line=dict(color=GRIS, width=1.5)),
                         hovertemplate="Base: %{x}%<extra></extra>"))
fig.add_trace(go.Scatter(x=v.pct_atribuido, y=v.lab, mode="markers+text", name="Journey (55)",
                         marker=dict(size=13, color=AZUL),
                         text=v.pct_atribuido.round(1).astype(str) + "%", textposition="middle right",
                         textfont=dict(family=MONO, size=11, color=TINTA),
                         hovertemplate="Journey: %{x}%<extra></extra>"))
fig.update_layout(showlegend=True)
fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="#F2F2F4", range=[-4, 118])
fig.update_yaxes(showgrid=False, tickfont=dict(family=SANS, size=12, color=TINTA))
guardar("venta", fig, 320)

# --- 8.13 Canal de marketing x canal de venta
cr = df_cruce.copy()
fig = go.Figure()
for canal, sub in cr.groupby("canal"):
    fig.add_trace(go.Bar(x=sub.canal_venta.str.title(), y=sub.conv, name=canal.upper(),
                         marker_color=COLOR_CANAL.get(canal, GRIS),
                         text=sub.conv, textposition="inside",
                         textfont=dict(family=MONO, size=11, color="#FFFFFF"),
                         hovertemplate=canal.upper() + " en %{x}: %{y}<extra></extra>"))
fig.update_layout(barmode="stack", showlegend=True, bargap=0.55)
fig.update_xaxes(tickfont=dict(family=SANS, size=12, color=TINTA))
guardar("cruce", fig, 300)


# =============================================================================
# 9. DASHBOARD HTML
# =============================================================================

def fig_html(nombre):
    return pio.to_html(FIGS[nombre], include_plotlyjs=False, full_html=False,
                       div_id=f"fig-{nombre}",
                       config={
                           "displayModeBar": True,
                           "displaylogo": False,
                           "responsive": True,
                           "scrollZoom": True,
                           "modeBarButtonsToRemove": ["lasso2d", "select2d", "toggleSpikelines",
                                                      "hoverClosestCartesian", "hoverCompareCartesian"],
                           "toImageButtonOptions": {"format": "png", "scale": 3,
                                                    "filename": f"tigo_reno_{nombre}"},
                       })


def num(x, dec=0):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "&mdash;"
    return f"{x:,.{dec}f}".replace(",", " ")


def tabla(df, cols, alias, fmt=None):
    fmt = fmt or {}
    th = "".join(f"<th>{a}</th>" for a in alias)
    filas = []
    for _, r in df.iterrows():
        tds = []
        for c in cols:
            v = r[c]
            f = fmt.get(c)
            tds.append(f"<td>{f(v) if f else ('&mdash;' if pd.isna(v) else v)}</td>")
        filas.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table class='tbl'><thead><tr>{th}</tr></thead><tbody>{''.join(filas)}</tbody></table>"


ruta_desc = []
for _, r in df_ruta.iterrows():
    otros = set()
    for _, o in df_ruta.iterrows():
        if o.ruta != r.ruta:
            otros |= set(o.ruta_key.split(" > "))
    propios = [s for s in r.ruta_key.split(" > ") if s not in otros]
    ruta_desc.append((r.ruta, int(r.msisdn_impactados), " y ".join(propios) or "sin pasos exclusivos",
                      int(r.msisdn_convertidos), r.tasa_pct))

_ord = sorted(ruta_desc, key=lambda x: -x[4])
mejor, peor = _ord[0], _ord[-1]


def z_dos_proporciones(x1, n1, x2, n2):
    """Prueba de dos proporciones. Sin scipy: p bilateral via erfc."""
    import math
    if min(n1, n2) == 0:
        return None, None
    p1, p2 = x1 / n1, x2 / n2
    pp = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


z_ab = p_ab = None
if len(ruta_desc) > 1:
    z_ab, p_ab = z_dos_proporciones(mejor[3], mejor[1], peor[3], peor[1])

if len(ruta_desc) < 2:
    sig_txt = "Solo hay una ruta en la data, no hay comparacion posible."
elif z_ab is None:
    sig_txt = ("No hay renovaciones suficientes en las rutas para contrastarlas: "
               "con conteos en cero la prueba no se puede calcular.")
else:
    sig_txt = (f"z = {z_ab:.2f} &middot; p = {p_ab:.3f}: si las dos rutas fueran igual de buenas, "
               f"habria {p_ab*100:.1f}% de probabilidad de ver una brecha de este tamano solo por azar. "
               + ("Por debajo del 5%, asi que la diferencia se sostiene al 95% de confianza."
                  if p_ab < 0.05 else
                  "Arriba del 5%, asi que todavia puede ser ruido."))

paso_top = p.assign(tasa=100 * p.convertidos / p.impactados).nlargest(1, "convertidos").iloc[0]
lat_med = con.execute("SELECT median(dias_al_convertir) FROM atr").fetchone()[0]
lat_3d = con.execute("SELECT 100.0*count(*) FILTER (WHERE dias_al_convertir<=3)/count(*) FROM atr").fetchone()[0]

fecha_gen = dt.datetime.now().strftime("%d/%m/%Y %H:%M")

CSS = """
:root{
  --azul:#112CB7; --azul-2:#7C8AD9; --azul-4:#EDF0FB;
  --tinta:#0A0A0A; --gris:#767680; --regla:#E7E7E9;
  --papel:#FFFFFF; --hueso:#FAFAFA;
  --sans:Geist,'SF Pro Display',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif;
  --serif:'Instrument Serif','Newsreader',Georgia,'Times New Roman',serif;
  --mono:'Geist Mono','SF Mono',ui-monospace,'JetBrains Mono',monospace;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--hueso);color:var(--tinta);font-family:var(--sans);
     font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 32px}

header.top{background:var(--papel);border-bottom:1px solid var(--regla)}
header.top .wrap{display:flex;align-items:center;justify-content:space-between;
                 gap:24px;padding-top:18px;padding-bottom:18px}
.brand{display:flex;align-items:center;gap:16px}
.brand img{height:26px;display:block}
.brand .fallback{font-family:var(--sans);font-weight:700;font-size:22px;
                 letter-spacing:-.03em;color:var(--azul)}
.brand .sep{width:1px;height:24px;background:var(--regla)}
.brand .kicker{font-family:var(--mono);font-size:11px;letter-spacing:.12em;
               text-transform:uppercase;color:var(--gris)}
.meta{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--gris);text-align:right}

nav.anchors{background:var(--papel);border-bottom:1px solid var(--regla);
            position:sticky;top:0;z-index:19;overflow-x:auto}
nav.anchors .wrap{display:flex;gap:26px;padding-top:12px;padding-bottom:12px}
nav.anchors a{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
              color:var(--gris);text-decoration:none;white-space:nowrap;padding-bottom:2px;
              border-bottom:1px solid transparent;transition:color .2s,border-color .2s}
nav.anchors a:hover,nav.anchors a:focus-visible{color:var(--azul);border-color:var(--azul)}

.hero{background:var(--papel);border-bottom:1px solid var(--regla);padding:72px 0 0}
.hero h1{font-family:var(--serif);font-weight:400;font-size:clamp(34px,5vw,58px);
         line-height:1.06;letter-spacing:-.025em;margin:0 0 18px;max-width:20ch}
.hero h1 em{font-style:normal;color:var(--azul)}
.hero p.lede{max-width:64ch;color:#3A3A40;margin:0 0 44px;font-size:17px}

.kpis{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--regla)}
.kpi{padding:34px 28px 40px;border-right:1px solid var(--regla)}
.kpi:last-child{border-right:0}
.kpi .lab{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
          color:var(--gris);display:block;margin-bottom:14px}
.kpi .val{font-family:var(--sans);font-weight:600;font-size:clamp(46px,6vw,78px);
          line-height:.94;letter-spacing:-.045em;font-variant-numeric:tabular-nums;display:block}
.kpi .val.azul{color:var(--azul)}
.kpi .sub{font-family:var(--mono);font-size:11px;color:var(--gris);margin-top:14px;display:block}

section{padding:76px 0;border-bottom:1px solid var(--regla)}
section:nth-of-type(even){background:var(--papel)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
         color:var(--azul);display:block;margin-bottom:16px}
h2{font-family:var(--serif);font-weight:400;font-size:clamp(26px,3.4vw,38px);line-height:1.12;
   letter-spacing:-.02em;margin:0 0 14px;max-width:26ch}
.dek{max-width:70ch;color:#3A3A40;margin:0 0 36px}

.card{background:var(--papel);border:1px solid var(--regla);border-radius:12px;padding:28px 24px}
section:nth-of-type(even) .card{background:var(--hueso)}
.card + .card{margin-top:20px}
.card h3{font-family:var(--sans);font-weight:600;font-size:15px;letter-spacing:-.01em;margin:0 0 4px}
.card .note{font-family:var(--mono);font-size:11px;color:var(--gris);margin:0 0 20px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.grid2 .card + .card{margin-top:0}

.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:32px}
.stat{background:var(--papel);border:1px solid var(--regla);border-radius:12px;padding:26px 24px}
section:nth-of-type(even) .stat{background:var(--hueso)}
.stat .lab{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
           color:var(--gris);display:block;margin-bottom:12px}
.stat .val{font-weight:600;font-size:clamp(38px,4.4vw,52px);line-height:1;letter-spacing:-.04em;
           font-variant-numeric:tabular-nums;display:block}
.stat .sub{font-family:var(--mono);font-size:11px;color:var(--gris);margin-top:10px;display:block}

.leyenda{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin:0 0 36px;
         border-top:1px solid var(--regla);border-bottom:1px solid var(--regla)}
.leyenda>div{padding:22px 24px 24px;border-right:1px solid var(--regla)}
.leyenda>div:last-child{border-right:0}
.leyenda b{display:block;font-size:14px;margin:0 0 6px}
.leyenda span:not(.pt){display:block;font-size:13px;color:#3A3A40;line-height:1.55}
.leyenda .pt{display:inline-block;width:11px;height:11px;border-radius:999px;margin-bottom:10px}
.leyenda .pt.base{background:#FFFFFF;border:1.5px solid var(--gris)}
.leyenda .pt.journey{background:var(--azul)}
.leyenda .pt.idx{background:var(--azul-2)}
code{font-family:var(--mono);font-size:11px;background:var(--azul-4);color:var(--azul);
     padding:2px 6px;border-radius:4px}
.tag{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:.08em;
     text-transform:uppercase;padding:4px 10px;border-radius:999px;
     background:var(--azul-4);color:var(--azul)}
.tag.aviso{background:#FBF3DB;color:#8A5B00}

.tbl{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.tbl th{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
        color:var(--gris);text-align:right;padding:10px 12px;border-bottom:1px solid var(--regla);
        font-weight:400}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl td{padding:11px 12px;border-bottom:1px solid #F2F2F4;text-align:right}
.tbl tbody tr:hover{background:var(--azul-4)}
.scroll{overflow-x:auto}

ul.notas{list-style:none;padding:0;margin:0}
ul.notas li{border-top:1px solid var(--regla);padding:20px 0;display:grid;
            grid-template-columns:150px 1fr;gap:24px}
ul.notas li:last-child{border-bottom:1px solid var(--regla)}
ul.notas .k{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
            color:var(--gris)}
ul.notas .v{color:#3A3A40}

footer{padding:56px 0 80px;background:var(--papel)}
footer .wrap{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap}
footer p{font-family:var(--mono);font-size:11px;color:var(--gris);margin:0}

.modebar{padding-top:2px!important}
.modebar-container .modebar{background:transparent!important}
.modebar-group{background:transparent!important;padding-left:4px!important}
.modebar-btn svg path{fill:#B4B4BC!important;transition:fill .15s}
.modebar-btn:hover svg path,.modebar-btn.active svg path{fill:var(--azul)!important}
.js-plotly-plot .modebar-btn{opacity:1!important}

.reveal{opacity:0;transform:translateY(12px)}
.reveal.on{opacity:1;transform:none;transition:opacity .6s cubic-bezier(.16,1,.3,1),
            transform .6s cubic-bezier(.16,1,.3,1)}

@media (max-width:900px){
  .wrap{padding:0 20px}
  .kpis{grid-template-columns:1fr 1fr}
  .kpi{border-bottom:1px solid var(--regla)}
  .kpi:nth-child(2n){border-right:0}
  .grid2,.stat-row,.leyenda{grid-template-columns:1fr}
  .leyenda>div{border-right:0;border-bottom:1px solid var(--regla)}
  .leyenda>div:last-child{border-bottom:0}
  ul.notas li{grid-template-columns:1fr;gap:6px}
}
@media (prefers-reduced-motion:reduce){
  .reveal,.reveal.on{opacity:1;transform:none;transition:none}
  html{scroll-behavior:auto}
}
"""

JS = """
const io=new IntersectionObserver((es)=>{es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('on');io.unobserve(e.target)}})},{threshold:.08});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
window.addEventListener('resize',()=>{document.querySelectorAll('.js-plotly-plot').forEach(p=>Plotly.Plots.resize(p))});
"""

HTML = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Journey de renovaciones | {REPORTE_DESDE} a {REPORTE_HASTA}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>{CSS}</style>
<script>{get_plotlyjs()}</script>
</head>
<body>

<header class="top">
  <div class="wrap">
    <div class="brand">
      <img src="{LOGO_URL}" alt="Tigo" class="logo"
           onerror="this.style.display='none';document.getElementById('logo-txt').style.display='inline'">
      <span class="fallback" id="logo-txt" style="display:none">Tigo</span>
      <span class="sep"></span>
      <span class="kicker">Renovaciones postpago &middot; Journey Braze</span>
    </div>
    <div class="meta">{REPORTE_DESDE} &rarr; {REPORTE_HASTA}<br>Generado {fecha_gen}</div>
  </div>
</header>

<nav class="anchors">
  <div class="wrap">
    <a href="#journey">El journey</a>
    <a href="#canal">Canal y paso</a>
    <a href="#ab">Rutas A/B</a>
    <a href="#tiempo">Tiempo de respuesta</a>
    <a href="#quien">Quien renueva</a>
    <a href="#detalle">Detalle diario</a>
  </div>
</nav>

<div class="hero">
  <div class="wrap">
    <h1>De {num(kpi['impactados'])} personas contactadas, <em>{num(kpi['msisdn_convertidos'])} renovaron</em> dentro de la ventana del journey.</h1>
    <p class="lede">Atribucion last-touch entre los envios de SMS y WhatsApp del journey de renovacion
    y las renovaciones facturables registradas del {REPORTE_DESDE} al {REPORTE_HASTA}.
    Cada renovacion se le acredita al ultimo envio vigente de ese numero, sin doble conteo.</p>
  </div>
  <div class="wrap">
    <div class="kpis">
      <div class="kpi">
        <span class="lab">Msisdn impactados</span>
        <span class="val">{num(kpi['impactados'])}</span>
        <span class="sub">numeros unicos &middot; {num(kpi['envios_totales'])} envios en total, 7 por numero</span>
      </div>
      <div class="kpi">
        <span class="lab">Renovaciones atribuidas</span>
        <span class="val azul">{num(kpi['conversiones'])}</span>
        <span class="sub">{num(kpi['msisdn_convertidos'])} numeros distintos</span>
      </div>
      <div class="kpi">
        <span class="lab">Tasa de conversion</span>
        <span class="val">{kpi['tasa_global']}%</span>
        <span class="sub">sobre la base contactada</span>
      </div>
      <div class="kpi">
        <span class="lab">Peso en el total</span>
        <span class="val">{kpi['share_mercado']}%</span>
        <span class="sub">de {num(kpi['reno_periodo'])} renovaciones del periodo</span>
      </div>
    </div>
  </div>
</div>

<section id="journey">
  <div class="wrap reveal">
    <span class="eyebrow">01 &middot; Estructura</span>
    <h2>Nueve envios, dos rutas, treinta dias</h2>
    <p class="dek">Cada burbuja es un paso del journey ubicado en la fecha real en que salio.
    El tamano y el numero dentro son las renovaciones que se le atribuyen. La fila de arriba es SMS,
    la de abajo WhatsApp.</p>
    <div class="card">
      <h3>Linea de tiempo del journey</h3>
      <p class="note">Posicion = fecha de envio &middot; tamano = renovaciones atribuidas</p>
      {fig_html('ruler')}
    </div>
  </div>
</section>

<section id="canal">
  <div class="wrap reveal">
    <span class="eyebrow">02 &middot; De donde vienen</span>
    <h2>El paso que mas produce es {paso_top.canvas_step_nm}</h2>
    <p class="dek">El volumen absoluto responde de donde salen las renovaciones; la tasa responde
    que tan eficiente es cada paso sobre la gente que si lo recibio. Los pasos de rama solo llegan
    a una parte de la base, asi que conviene leer las dos graficas juntas.</p>
    <div class="card">
      <h3>Renovaciones atribuidas por canal</h3>
      <p class="note">Volumen absoluto, no tasa</p>
      {fig_html('canal')}
    </div>
    <div class="card">
      <h3>Impactados contra convertidos, en orden cronologico</h3>
      <p class="note">Barra clara = alcance del paso &middot; barra azul = renovaciones atribuidas</p>
      {fig_html('paso')}
    </div>
    <div class="card">
      <h3>Tasa de conversion por paso</h3>
      <p class="note">Renovaciones atribuidas sobre msisdn que recibieron ese paso</p>
      {fig_html('tasa_paso')}
    </div>
  </div>
</section>

<section id="ab">
  <div class="wrap reveal">
    <span class="eyebrow">03 &middot; Prueba A/B</span>
    <h2>La base viene partida en dos rutas con distinto orden de canal</h2>
    <p class="dek">Los siete envios que recibe cada numero no son los mismos para todos:
    hay dos secuencias distintas en la mitad del journey. Esa diferencia es lo unico que
    separa a los dos grupos, asi que la brecha en tasa se puede leer como resultado del orden.</p>
    <div class="stat-row">
      {"".join(f'''<div class="stat">
        <span class="lab">{rr[0]} &middot; {num(rr[1])} msisdn</span>
        <span class="val">{rr[4]}%</span>
        <span class="sub">{rr[3]} renovaciones &middot; pasos propios: {rr[2]}</span>
      </div>''' for rr in ruta_desc)}
      <div class="stat">
        <span class="lab">Brecha</span>
        <span class="val" style="color:var(--azul)">{round(abs(mejor[4] - peor[4]), 2)} pp</span>
        <span class="sub">a favor de {mejor[0]}</span>
      </div>
    </div>
    <div class="card">
      <h3>Tasa de conversion por ruta</h3>
      <p class="note">Renovaciones atribuidas sobre msisdn asignados a cada ruta &middot; {sig_txt}</p>
      {fig_html('ruta')}
    </div>
  </div>
</section>

<section id="tiempo">
  <div class="wrap reveal">
    <span class="eyebrow">04 &middot; Ritmo</span>
    <h2>La renovacion llega en los primeros dias o no llega</h2>
    <p class="dek">La mediana esta en {num(lat_med, 0)} dias despues del envio y
    {num(lat_3d, 0)}% de las renovaciones atribuidas ocurren dentro de los tres primeros dias.
    Eso define hasta donde tiene sentido estirar la ventana de atribucion.</p>
    <div class="grid2">
      <div class="card">
        <h3>Dias entre el envio y la renovacion</h3>
        <p class="note">Distribucion de la latencia</p>
        {fig_html('latencia')}
      </div>
      <div class="card">
        <h3>Impactos acumulados antes de renovar</h3>
        <p class="note">Cuantos mensajes del journey habia recibido esa persona</p>
        {fig_html('toques')}
      </div>
    </div>
    <div class="card">
      <h3>Renovaciones acumuladas del journey</h3>
      <p class="note">Suma corrida por fecha de renovacion</p>
      {fig_html('acum')}
    </div>
  </div>
</section>

<section id="quien">
  <div class="wrap reveal">
    <span class="eyebrow">05 &middot; Perfil</span>
    <h2>Donde renuevan, por que canal y con que plan</h2>
    <p class="dek">Medicion de la composicion del journey contra las {num(kpi['reno_periodo'])}
    renovaciones del periodo. Indice 100 significa que el journey convierte ese segmento en la
    misma proporcion en que aparece en el total.</p>
    <div class="leyenda">
      <div><span class="pt base"></span><b>Base de renovaciones</b>
        <span>Las {num(kpi['reno_periodo'])} renovaciones facturadas del {REPORTE_DESDE} al {REPORTE_HASTA},
        haya recibido esa persona el journey o no. Es el retrato de como renueva Guatemala.</span></div>
      <div><span class="pt journey"></span><b>Journey</b>
        <span>Las {num(kpi['conversiones'])} renovaciones que este reporte le atribuye a un envio de
        SMS o WhatsApp. Es un subconjunto de la base, el {kpi['share_mercado']}% de ella.</span></div>
      <div><span class="pt idx"></span><b>Como se compara</b>
        <span>Se reparte cada grupo en 100% y se enfrentan los dos porcentajes. Si un plan es 33%
        de las renovaciones del journey y 27% de la base, el journey lo trae de mas.</span></div>
    </div>
    <div class="card">
      <h3>Departamento, indice contra la base de renovaciones</h3>
      <p class="note">Solo departamentos con {MIN_N_DIMENSION} o mas renovaciones atribuidas</p>
      {fig_html('geo')}
    </div>
    <div class="grid2">
      <div class="card">
        <h3>Ciudades con mas renovaciones atribuidas</h3>
        <p class="note">Conteo absoluto, top 10</p>
        {fig_html('ciudad')}
      </div>
      <div class="card">
        <h3>Donde termina cerrandose la renovacion</h3>
        <p class="note">Columna <code>channel</code> del registro de renovacion: el punto de venta
        que factura la transaccion. Cada grupo suma 100%.</p>
        {fig_html('venta')}
      </div>
    </div>
    <div class="grid2">
      <div class="card">
        <h3>Plan que queda contratado al renovar</h3>
        <p class="note">Columna <code>bfr_dt_nm</code>: el detalle de plan con el que quedo la linea.
        Top 8 por volumen atribuido. Cada grupo suma 100%.</p>
        {fig_html('plan')}
      </div>
      <div class="card">
        <h3>Canal del mensaje contra canal de venta</h3>
        <p class="note">Que canal empuja a que punto de cierre</p>
        {fig_html('cruce')}
      </div>
    </div>
  </div>
</section>

<section id="detalle">
  <div class="wrap reveal">
    <span class="eyebrow">06 &middot; Detalle</span>
    <h2>Cada paso del journey con su fecha, su alcance y su resultado</h2>
    <p class="dek">Cada paso salio en una sola fecha, asi que paso y fecha de envio son la misma
    fila. El 16 de junio salieron dos pasos distintos, uno por rama, y por eso aparecen dos
    renglones ese dia. Esta misma tabla se exporta a CSV para cruzarla con costo de envio.</p>
    <div class="card scroll">
      <h3>Journey completo, en orden cronologico</h3>
      <p class="note">Tasa = msisdn convertidos sobre msisdn que recibieron ese paso</p>
      {tabla(df_tabla,
             ["paso_idx", "canvas_step_nm", "canal", "primera_fecha", "dia_semana",
              "msisdn_impactados", "msisdn_convertidos", "tasa_pct", "dias_prom"],
             ["#", "Paso", "Canal", "Fecha de envio", "Dia", "Impactados", "Convertidos", "Tasa", "Dias prom"],
             {"canal": lambda v: str(v).upper(),
              "primera_fecha": lambda v: str(v)[:10],
              "msisdn_impactados": lambda v: num(v),
              "msisdn_convertidos": lambda v: num(v),
              "tasa_pct": lambda v: f"{v}%",
              "dias_prom": lambda v: "&mdash;" if pd.isna(v) else f"{v}"})}
    </div>
  </div>
</section>

<footer>
  <div class="wrap">
    <p>Fuente: envios de Braze &middot; renovaciones facturables mobile<br>
       Ventana de atribucion {TOPE_VENTANA_DIAS} dias &middot; last touch</p>
    <p>{REPORTE_DESDE} &rarr; {REPORTE_HASTA}<br>Generado {fecha_gen}</p>
  </div>
</footer>

<script>{JS}</script>
</body>
</html>
"""

with open(SALIDA_HTML, "w", encoding="utf-8") as fh:
    fh.write(HTML)

print("=" * 68)
print(f"Impactados            {kpi['impactados']:>10,}")
print(f"Renovaciones atrib.   {kpi['conversiones']:>10,}")
print(f"Tasa                  {kpi['tasa_global']:>10}%")
print(f"Peso en el total      {kpi['share_mercado']:>10}%")
print("=" * 68)
print(df_ruta.to_string(index=False))
print("=" * 68)
print(f"Dashboard -> {SALIDA_HTML}")
print(f"CSV       -> {OUT_DIR}")