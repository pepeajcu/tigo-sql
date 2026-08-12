"""
Journey de renovaciones | comparativo Pruebas vs Produccion
Atribucion last-touch de envios contra renovaciones, para dos datasets.

Cada dataset se procesa por separado, con su propio rango de fechas y su propia
estructura de pasos. La comparacion se hace sobre ejes relativos (dia 0 = primer
envio de ese dataset, paso 1..N del journey), asi que dos periodos distintos
pueden convivir en la misma grafica.

Salida: un solo dashboard .HTML autocontenido + los CSV de cada dataset.

Requisitos:  pip install duckdb plotly pandas
"""

import os
import math
import datetime as dt

import duckdb
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

# =============================================================================
# 1. CONFIGURACION
# =============================================================================

# --- RUTAS ------------------------------------------------------------------
# Editar solo estas tres lineas si las carpetas cambian de lugar.
DIR_PRUEBA = r"C:\Users\datatigo\Desktop\tigo-sql\tigo-sql\2026-08-agosto\renos-sql\dataset"
DIR_PRODU  = r"C:\Users\datatigo\Desktop\tigo-sql\tigo-sql\2026-08-agosto\renos-sql\dataset\produ"
DIR_OUT    = r"C:\Users\datatigo\Desktop\tigo-sql\tigo-sql\2026-08-agosto\renos-sql\dataset\produ\output"

# Si esas carpetas no existen (Colab, Mac, o el script movido de maquina), se
# usa la carpeta donde vive este .py para no tener que editar nada.
AQUI = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()


def carpeta(preferida, alterna=None):
    if os.path.isdir(preferida):
        return preferida
    return alterna if alterna and os.path.isdir(alterna) else AQUI


DIR_PRUEBA = os.environ.get("DIR_PRUEBA") or carpeta(DIR_PRUEBA)
DIR_PRODU  = os.environ.get("DIR_PRODU")  or carpeta(DIR_PRODU, os.path.join(DIR_PRUEBA, "produ"))
OUT_DIR    = os.environ.get("OUT_DIR")    or (DIR_OUT if os.path.isdir(os.path.dirname(DIR_OUT))
                                              else os.path.join(DIR_PRODU, "output"))
os.makedirs(OUT_DIR, exist_ok=True)

TOPE_VENTANA_DIAS = 7                 # vigencia del ultimo envio del journey
MIN_N_DIMENSION = 3                   # piso para mostrar un corte por dimension
TOP_N = 8                             # cuantas categorias se grafican por dimension

PRIORIDAD_CANAL = {"whatsapp": 3, "sms": 2, "push": 1, "email": 4, "inapp": 5}

AZUL     = "#112CB7"     # dataset de pruebas
AMARILLO = "#F5B700"     # dataset de produccion
AMBAR    = "#8A6200"     # texto sobre blanco cuando el dato es de produccion

# Cada dataset: etiqueta, color, carpeta propia y nombres de archivo aceptados.
DATASETS = [
    dict(id="prueba",
         nombre="Pruebas",
         color=AZUL,
         color_texto=AZUL,
         dir=DIR_PRUEBA,
         envios=["envios.csv", "envios_prueba.csv", "envios_msisdn.csv"],
         reno=["renovaciones.csv", "reno_msisdn.csv", "reno.csv", "renos.csv"]),
    dict(id="produ",
         nombre="Produccion",
         color=AMARILLO,
         color_texto=AMBAR,
         dir=DIR_PRODU,
         envios=["envios_produ.csv", "envios_produccion.csv", "envios_prod.csv"],
         reno=["reno_produ.csv", "renovaciones_produ.csv", "reno_prod.csv"]),
]

LOGO_URL = ("https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/"
            "Logo_Tigo.svg/1280px-Logo_Tigo.svg.png")


def resolver(base, candidatos, etiqueta, var_entorno=None):
    """Encuentra el archivo aunque cambie de nombre entre una corrida y otra."""
    if var_entorno and os.environ.get(var_entorno):
        return os.environ[var_entorno]
    for nombre in candidatos:
        ruta = os.path.join(base, nombre)
        if os.path.isfile(ruta):
            return ruta
    hay = sorted(f for f in os.listdir(base) if f.lower().endswith(".csv")) \
        if os.path.isdir(base) else []
    raise SystemExit(
        f"\nNo encontre el CSV de {etiqueta}.\n\n"
        f"  Busque en: {base}\n"
        f"  Con estos nombres: {', '.join(candidatos)}\n"
        f"  CSV que si hay ahi: {', '.join(hay) if hay else '(ninguno)'}\n\n"
        f"  Renombra tu archivo, o corrige la ruta arriba en el bloque RUTAS.\n")


def sql_ruta(ruta):
    """DuckDB traga mejor las diagonales normales; en Windows funcionan igual."""
    return str(ruta).replace("\\", "/").replace("'", "''")


for ds in DATASETS:
    ds["envios_csv"] = resolver(ds["dir"], ds["envios"], f"envios de {ds['nombre']}",
                                f"ENVIOS_{ds['id'].upper()}")
    ds["reno_csv"] = resolver(ds["dir"], ds["reno"], f"renovaciones de {ds['nombre']}",
                              f"RENO_{ds['id'].upper()}")
    print(f"{ds['nombre']:<12} {ds['dir']}")
    print(f"{'':<12} {os.path.basename(ds['envios_csv'])} + "
          f"{os.path.basename(ds['reno_csv'])}")
print(f"{'Salida':<12} {OUT_DIR}\n")

# =============================================================================
# 2. MOTOR: UN DATASET A LA VEZ
# =============================================================================

con = duckdb.connect()

# fecha_envio suele venir como '2026-06-07 16:00:00.000 -0600'. Un TRY_CAST
# directo a DATE devuelve NULL por el offset y vacia la tabla completa sin
# avisar; nos quedamos con los primeros 10 caracteres, que ya son la fecha local.
con.execute("""
CREATE OR REPLACE MACRO f_fecha(x) AS COALESCE(
    TRY_CAST(substr(CAST(x AS VARCHAR), 1, 10) AS DATE),
    CAST(TRY_CAST(substr(CAST(x AS VARCHAR), 1, 19) AS TIMESTAMP) AS DATE)
);
""")

# Los envios traen el numero con codigo de pais y las renovaciones sin el.
# Los ultimos 8 digitos son el terreno comun.
con.execute("""
CREATE OR REPLACE MACRO f_msisdn(x) AS
    right(regexp_replace(CAST(x AS VARCHAR), '[^0-9]', '', 'g'), 8);
""")

_case_prioridad = ("CASE canal\n" + "\n".join(
    f"    WHEN '{k}' THEN {v}" for k, v in PRIORIDAD_CANAL.items()) + "\n    ELSE 99 END")

DIAS_ES = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miercoles",
           "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sabado",
           "Sunday": "Domingo"}
ORDEN_DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]


def procesar(ds):
    """Corre el pipeline completo para un dataset y devuelve sus resultados."""
    p = ds["id"]
    salida = os.path.join(OUT_DIR, p)
    os.makedirs(salida, exist_ok=True)

    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_envios_raw AS
    SELECT * FROM read_csv('{sql_ruta(ds["envios_csv"])}', all_varchar = true);
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_reno_raw AS
    SELECT * FROM read_csv('{sql_ruta(ds["reno_csv"])}', all_varchar = true);
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_envios AS
    SELECT
        f_msisdn(msisdn)                                AS msisdn,
        cuenta_id,
        f_fecha(fecha_envio)                            AS fecha_envio,
        lower(trim(canal))                              AS canal,
        COALESCE(NULLIF(trim(canvas_step_nm), ''), '(sin paso)')          AS canvas_step_nm,
        COALESCE(NULLIF(trim(canvas_variation_nm), ''), '(sin variante)') AS canvas_variation_nm
    FROM {p}_envios_raw
    WHERE length(f_msisdn(msisdn)) = 8 AND f_fecha(fecha_envio) IS NOT NULL;
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_reno AS
    SELECT DISTINCT
        f_msisdn(msisdn)            AS msisdn,
        f_fecha(fecha_conv)         AS fecha_conv,
        COALESCE(NULLIF(upper(trim(channel)), ''), 'SIN DATO')       AS canal_venta,
        COALESCE(NULLIF(upper(trim(ciudad)), ''), 'SIN DATO')        AS ciudad,
        COALESCE(NULLIF(upper(trim(departamento)), ''), 'SIN DATO')  AS departamento,
        COALESCE(NULLIF(upper(trim(bfr_vc_nm)), ''), 'SIN DATO')     AS plan_nm,
        COALESCE(NULLIF(upper(trim(bfr_dt_nm)), ''), 'SIN DATO')     AS plan_detalle
    FROM {p}_reno_raw
    WHERE length(f_msisdn(msisdn)) = 8 AND f_fecha(fecha_conv) IS NOT NULL;
    """)

    rango_e = con.execute(f"SELECT min(fecha_envio), max(fecha_envio), count(*) "
                          f"FROM {p}_envios").fetchone()
    rango_r = con.execute(f"SELECT min(fecha_conv), max(fecha_conv), count(*) "
                          f"FROM {p}_reno").fetchone()
    if not rango_e[2]:
        raise SystemExit(f"[{ds['nombre']}] No quedo ni un envio valido tras limpiar "
                         f"{ds['envios_csv']}.")
    if not rango_r[2]:
        raise SystemExit(f"[{ds['nombre']}] No quedo ni una renovacion valida tras limpiar "
                         f"{ds['reno_csv']}.")

    # Cada dataset define su propio periodo a partir de su propia data.
    desde = min(rango_e[0], rango_r[0])
    hasta = max(rango_e[1], rango_r[1]) + dt.timedelta(days=1)
    dia_cero = rango_e[0]        # ancla para el eje relativo

    # Cada envio queda vigente hasta el siguiente envio del mismo msisdn; el
    # ultimo vive TOPE_VENTANA_DIAS. Asi ninguna renovacion se cuenta dos veces.
    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_ventanas AS
    WITH fechas AS (SELECT DISTINCT msisdn, fecha_envio FROM {p}_envios)
    SELECT msisdn, fecha_envio,
           COALESCE(lead(fecha_envio) OVER (PARTITION BY msisdn ORDER BY fecha_envio),
                    fecha_envio + INTERVAL {TOPE_VENTANA_DIAS} DAY) AS fin_ventana
    FROM fechas;
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_atribucion AS
    WITH candidatos AS (
        SELECT
            r.msisdn, r.fecha_conv,
            r.canal_venta, r.ciudad, r.departamento, r.plan_nm, r.plan_detalle,
            e.cuenta_id, e.fecha_envio, e.canal,
            e.canvas_step_nm, e.canvas_variation_nm,
            date_diff('day', e.fecha_envio, r.fecha_conv) AS dias_al_convertir,
            count(*) OVER (PARTITION BY r.msisdn, r.fecha_conv, e.fecha_envio) AS canales_mismo_dia,
            row_number() OVER (PARTITION BY r.msisdn, r.fecha_conv
                               ORDER BY e.fecha_envio DESC, {_case_prioridad}) AS rn
        FROM {p}_reno r
        JOIN {p}_ventanas v ON v.msisdn = r.msisdn
                           AND r.fecha_conv >= v.fecha_envio
                           AND r.fecha_conv <  v.fin_ventana
        JOIN {p}_envios e   ON e.msisdn = v.msisdn AND e.fecha_envio = v.fecha_envio
    )
    SELECT c.* EXCLUDE (rn),
           (SELECT count(*) FROM {p}_envios e2
             WHERE e2.msisdn = c.msisdn AND e2.fecha_envio <= c.fecha_conv) AS toques_previos
    FROM candidatos c WHERE rn = 1;
    """)

    n_atr = con.execute(f"SELECT count(*) FROM {p}_atribucion").fetchone()[0]
    cruce = con.execute(f"""
    SELECT (SELECT count(DISTINCT msisdn) FROM {p}_envios
             WHERE msisdn IN (SELECT msisdn FROM {p}_reno)),
           (SELECT count(DISTINCT msisdn) FROM {p}_envios)
    """).fetchone()
    if n_atr == 0:
        raise SystemExit(
            f"\n[{ds['nombre']}] CERO renovaciones atribuidas.\n"
            f"  Cruce de numeros: {cruce[0]:,} de {cruce[1]:,} msisdn impactados aparecen\n"
            f"  en la tabla de renovaciones. Si es 0, el formato de msisdn no coincide.\n"
            f"  Ventana actual: {TOPE_VENTANA_DIAS} dias.\n")

    # El orden real del journey es la fecha en que salio cada paso, no el
    # nombre ("Dia 12" no va antes que "Dia 3" alfabeticamente).
    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_orden AS
    SELECT canvas_step_nm, min(fecha_envio) AS primera_fecha,
           dense_rank() OVER (ORDER BY min(fecha_envio), canvas_step_nm) AS paso_idx
    FROM {p}_envios GROUP BY 1;
    """)

    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_paso AS
    WITH alcance AS (
        SELECT canvas_step_nm, canal, count(DISTINCT msisdn) AS msisdn_impactados
        FROM {p}_envios GROUP BY 1, 2
    ),
    conv AS (
        SELECT canvas_step_nm, canal,
               count(DISTINCT msisdn) AS msisdn_convertidos,
               round(avg(dias_al_convertir), 2) AS dias_prom
        FROM {p}_atribucion GROUP BY 1, 2
    )
    SELECT o.paso_idx, a.canvas_step_nm, a.canal, o.primera_fecha,
           date_diff('day', DATE '{dia_cero}', o.primera_fecha) AS dia_rel,
           a.msisdn_impactados,
           COALESCE(c.msisdn_convertidos, 0) AS msisdn_convertidos,
           round(100.0 * COALESCE(c.msisdn_convertidos, 0)
                 / nullif(a.msisdn_impactados, 0), 2) AS tasa_pct,
           c.dias_prom
    FROM alcance a
    LEFT JOIN conv c USING (canvas_step_nm, canal)
    JOIN {p}_orden o USING (canvas_step_nm)
    ORDER BY o.paso_idx;
    """)

    # La secuencia de pasos que recibio cada msisdn identifica su rama del
    # journey. Se etiquetan por tamano (A la mas grande).
    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_ruta_msisdn AS
    SELECT msisdn,
           string_agg(canvas_step_nm, ' > ' ORDER BY fecha_envio, canvas_step_nm) AS ruta_key
    FROM {p}_envios GROUP BY 1;
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_rutas AS
    SELECT ruta_key,
           'Ruta ' || chr(64 + CAST(row_number() OVER (ORDER BY count(*) DESC, ruta_key) AS INT)) AS ruta
    FROM {p}_ruta_msisdn GROUP BY 1;
    """)
    con.execute(f"""
    CREATE OR REPLACE TABLE {p}_reporte_ruta AS
    WITH alc AS (
        SELECT ru.ruta, ru.ruta_key, count(DISTINCT rm.msisdn) AS msisdn_impactados
        FROM {p}_ruta_msisdn rm JOIN {p}_rutas ru USING (ruta_key) GROUP BY 1, 2
    ),
    cv AS (
        SELECT ru.ruta, count(DISTINCT a.msisdn) AS msisdn_convertidos,
               round(avg(a.dias_al_convertir), 2) AS dias_prom
        FROM {p}_atribucion a
        JOIN {p}_ruta_msisdn rm USING (msisdn)
        JOIN {p}_rutas ru USING (ruta_key) GROUP BY 1
    )
    SELECT alc.ruta, alc.ruta_key, alc.msisdn_impactados,
           COALESCE(cv.msisdn_convertidos, 0) AS msisdn_convertidos,
           round(100.0 * COALESCE(cv.msisdn_convertidos, 0)
                 / nullif(alc.msisdn_impactados, 0), 2) AS tasa_pct,
           cv.dias_prom
    FROM alc LEFT JOIN cv USING (ruta) ORDER BY alc.ruta;
    """)

    # ciudad, departamento, plan y canal de venta solo existen en el registro de
    # la renovacion. Se mide composicion contra la base del propio periodo:
    # indice = (% en lo atribuido / % en la base) * 100
    def dimension(col):
        con.execute(f"""
        CREATE OR REPLACE TABLE {p}_tmp AS
        WITH a AS (SELECT {col} AS valor, count(*) AS conv FROM {p}_atribucion GROUP BY 1),
             b AS (SELECT {col} AS valor, count(*) AS base FROM {p}_reno
                   WHERE fecha_conv >= DATE '{desde}' AND fecha_conv < DATE '{hasta}' GROUP BY 1),
             t AS (SELECT (SELECT count(*) FROM {p}_atribucion) ta,
                          (SELECT count(*) FROM {p}_reno
                            WHERE fecha_conv >= DATE '{desde}' AND fecha_conv < DATE '{hasta}') tb)
        SELECT COALESCE(a.valor, b.valor) AS valor,
               COALESCE(a.conv, 0) AS conv_atribuidas,
               COALESCE(b.base, 0) AS reno_base,
               round(100.0 * COALESCE(a.conv, 0) / nullif(t.ta, 0), 2) AS pct_atribuido,
               round(100.0 * COALESCE(b.base, 0) / nullif(t.tb, 0), 2) AS pct_base,
               round(100.0 * (COALESCE(a.conv, 0) / nullif(t.ta, 0))
                     / nullif(COALESCE(b.base, 0) / nullif(t.tb, 0), 0), 0) AS indice
        FROM a FULL OUTER JOIN b USING (valor) CROSS JOIN t
        ORDER BY conv_atribuidas DESC;
        """)
        df = con.execute(f"SELECT * FROM {p}_tmp").df()
        df.to_csv(os.path.join(salida, f"dim_{col}.csv"), index=False)
        return df

    res = dict(ds)
    res.update(
        desde=desde, hasta=hasta, dia_cero=dia_cero,
        rango_e=rango_e, rango_r=rango_r,
        paso=con.execute(f"SELECT * FROM {p}_paso").df(),
        ruta=con.execute(f"SELECT * FROM {p}_reporte_ruta").df(),
        geo=dimension("departamento"),
        ciudad=dimension("ciudad"),
        plan=dimension("plan_detalle"),
        venta=dimension("canal_venta"),
    )

    res["latencia"] = con.execute(f"""
        SELECT dias_al_convertir AS dias, count(*) AS conv
        FROM {p}_atribucion GROUP BY 1 ORDER BY 1""").df()

    res["toques"] = con.execute(f"""
        SELECT toques_previos AS toques, count(*) AS conv
        FROM {p}_atribucion GROUP BY 1 ORDER BY 1""").df()

    # Dia de la semana en que se firma la renovacion: no depende del calendario,
    # asi que dos periodos distintos se pueden superponer directo.
    dsem = con.execute(f"""
        SELECT dayname(fecha_conv) AS dia, count(*) AS conv
        FROM {p}_atribucion GROUP BY 1""").df()
    dsem["dia"] = dsem["dia"].map(DIAS_ES).fillna(dsem["dia"])
    dsem = dsem.set_index("dia").reindex(ORDEN_DIAS).fillna(0).reset_index()
    dsem["pct"] = (100 * dsem.conv / dsem.conv.sum()).round(2) if dsem.conv.sum() else 0
    res["dia_semana"] = dsem

    # Curva acumulada sobre dia relativo al primer envio del propio dataset.
    res["acum"] = con.execute(f"""
        SELECT dia_rel,
               sum(conv) OVER (ORDER BY dia_rel) AS acum,
               100.0 * sum(conv) OVER (ORDER BY dia_rel)
                 / (SELECT count(*) FROM {p}_atribucion) AS pct
        FROM (SELECT date_diff('day', DATE '{dia_cero}', fecha_conv) AS dia_rel,
                     count(*) AS conv
              FROM {p}_atribucion GROUP BY 1)
        ORDER BY dia_rel""").df()

    res["canal"] = con.execute(f"""
        SELECT canal,
               count(*) AS conv,
               100.0 * count(*) / (SELECT count(*) FROM {p}_atribucion) AS pct
        FROM {p}_atribucion GROUP BY 1 ORDER BY conv DESC""").df()

    k = con.execute(f"""
    SELECT (SELECT count(DISTINCT msisdn) FROM {p}_envios)   AS impactados,
           (SELECT count(*) FROM {p}_envios)                 AS envios,
           (SELECT count(*) FROM {p}_atribucion)             AS conversiones,
           (SELECT count(DISTINCT msisdn) FROM {p}_atribucion) AS convertidos,
           (SELECT count(*) FROM {p}_reno
             WHERE fecha_conv >= DATE '{desde}' AND fecha_conv < DATE '{hasta}') AS reno_periodo,
           (SELECT median(dias_al_convertir) FROM {p}_atribucion) AS lat_med,
           (SELECT count(DISTINCT canvas_step_nm) FROM {p}_envios) AS pasos
    """).df().iloc[0].to_dict()
    k["tasa"] = round(100 * k["convertidos"] / k["impactados"], 2) if k["impactados"] else 0
    k["share"] = round(100 * k["conversiones"] / k["reno_periodo"], 2) if k["reno_periodo"] else 0
    res["kpi"] = k

    con.execute(f"COPY {p}_paso TO '{sql_ruta(os.path.join(salida, 'paso_journey.csv'))}' (HEADER)")
    con.execute(f"COPY {p}_reporte_ruta TO '{sql_ruta(os.path.join(salida, 'rutas.csv'))}' (HEADER)")
    con.execute(f"COPY {p}_atribucion TO '{sql_ruta(os.path.join(salida, 'detalle_atribucion.csv'))}' (HEADER)")

    print(f"{ds['nombre']:<12} {rango_e[0]} a {rango_r[1]} | "
          f"{int(k['impactados']):,} impactados | {int(k['conversiones']):,} atribuidas | "
          f"{k['tasa']}% | {int(k['pasos'])} pasos")
    return res


DS = [procesar(ds) for ds in DATASETS]
print()


def z_dos_proporciones(x1, n1, x2, n2):
    """Prueba de dos proporciones. Sin scipy: p bilateral via erfc."""
    if min(n1, n2) == 0:
        return None, None
    pp = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (x1 / n1 - x2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


# =============================================================================
# 3. ESTILO
# =============================================================================

AZUL_2, AZUL_3, AZUL_4 = "#7C8AD9", "#C7CEEF", "#EDF0FB"
AMA_3, AMA_4 = "#F7D97A", "#FDF4DA"
TINTA, GRIS, REGLA = "#0A0A0A", "#767680", "#E7E7E9"

SANS = "Geist, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
MONO = "'Geist Mono', 'SF Mono', ui-monospace, 'JetBrains Mono', monospace"

CLARO = {"prueba": AZUL_4, "produ": AMA_4}
MEDIO = {"prueba": AZUL_3, "produ": AMA_3}

pio.templates["tigo"] = go.layout.Template(layout=dict(
    font=dict(family=SANS, size=13, color=TINTA),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=40, b=10),
    colorway=[AZUL, AMARILLO, AZUL_2, GRIS],
    hoverlabel=dict(bgcolor=TINTA, bordercolor=TINTA,
                    font=dict(color="#FFFFFF", family=SANS, size=12)),
    xaxis=dict(showgrid=False, zeroline=False, linecolor=REGLA, linewidth=1,
               ticks="outside", tickcolor=REGLA, ticklen=4, automargin=True,
               tickfont=dict(family=MONO, size=11, color=GRIS)),
    yaxis=dict(showgrid=True, gridcolor="#F2F2F4", zeroline=False,
               linecolor="rgba(0,0,0,0)", automargin=True,
               tickfont=dict(family=MONO, size=11, color=GRIS)),
    legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0,
                bgcolor="rgba(0,0,0,0)",
                font=dict(family=MONO, size=11, color=GRIS)),
    showlegend=True,
))
pio.templates.default = "tigo"

FIGS = {}


def guardar(nombre, fig, alto=380):
    fig.update_layout(height=alto, template="tigo")
    FIGS[nombre] = fig


def barras_h(fig, categorias, alto_base=140, por_fila=34):
    """Alto proporcional al numero de categorias: nunca se encima el texto."""
    return max(alto_base + por_fila * len(categorias), 240)


# --- 3.1 Linea de tiempo del journey, en dia relativo al primer envio
fig = go.Figure()
for i, d in enumerate(DS):
    p = d["paso"].groupby(["paso_idx", "canvas_step_nm", "dia_rel"], as_index=False).agg(
        impactados=("msisdn_impactados", "sum"), convertidos=("msisdn_convertidos", "sum"))
    y = len(DS) - 1 - i
    fig.add_shape(type="line", x0=p.dia_rel.min(), x1=p.dia_rel.max(), y0=y, y1=y,
                  line=dict(color=REGLA, width=1))
    tam = 14 + 26 * (p.convertidos / p.convertidos.max() if p.convertidos.max() else 0)
    fig.add_trace(go.Scatter(
        x=p.dia_rel, y=[y] * len(p), mode="markers", name=d["nombre"],
        marker=dict(size=tam, color=d["color"], line=dict(color="#FFFFFF", width=2)),
        customdata=p[["canvas_step_nm", "impactados", "convertidos", "paso_idx"]],
        hovertemplate=("<b>%{customdata[0]}</b> &middot; paso %{customdata[3]}"
                       "<br>Dia %{x} del journey"
                       "<br>Impactados %{customdata[1]:,}"
                       "<br>Convertidos %{customdata[2]:,}<extra></extra>")))
fig.update_yaxes(showgrid=False, range=[-0.6, len(DS) - 0.4],
                 tickmode="array", tickvals=list(range(len(DS))),
                 ticktext=[d["nombre"].upper() for d in reversed(DS)],
                 tickfont=dict(family=MONO, size=11, color=TINTA))
fig.update_xaxes(showgrid=False, dtick=5,
                 title=dict(text="dias desde el primer envio de cada dataset",
                            font=dict(family=MONO, size=11, color=GRIS)))
guardar("timeline", fig, 300)

# --- 3.2 Tasa de conversion por paso del journey
fig = go.Figure()
for d in DS:
    p = d["paso"].sort_values("paso_idx")
    fig.add_trace(go.Scatter(
        x=p.paso_idx, y=p.tasa_pct, mode="lines+markers", name=d["nombre"],
        line=dict(color=d["color"], width=2.5),
        marker=dict(size=9, color=d["color"], line=dict(color="#FFFFFF", width=1.5)),
        customdata=p[["canvas_step_nm", "msisdn_impactados", "msisdn_convertidos"]],
        hovertemplate=("<b>%{customdata[0]}</b><br>Tasa %{y}%"
                       "<br>%{customdata[2]:,} de %{customdata[1]:,}<extra></extra>")))
fig.update_xaxes(dtick=1, title=dict(text="paso del journey, en orden cronologico",
                                     font=dict(family=MONO, size=11, color=GRIS)))
fig.update_yaxes(ticksuffix="%", rangemode="tozero")
guardar("tasa_paso", fig, 360)

# --- 3.3 Alcance por paso (barras horizontales: los nombres son largos)
filas = []
for d in DS:
    p = d["paso"].groupby(["paso_idx", "canvas_step_nm"], as_index=False).agg(
        impactados=("msisdn_impactados", "sum"), convertidos=("msisdn_convertidos", "sum"))
    p["ds"] = d["nombre"]
    p["etq"] = p.paso_idx.astype(int).astype(str) + ".  " + p.canvas_step_nm + "   " + d["nombre"]
    filas.append(p)
alc = pd.concat(filas).sort_values(["ds", "paso_idx"], ascending=[True, False])
fig = go.Figure()
for d in DS:
    sub = alc[alc.ds == d["nombre"]]
    fig.add_trace(go.Bar(y=sub.etq, x=sub.impactados, orientation="h",
                         name=f"{d['nombre']} &middot; impactados",
                         marker_color=CLARO[d["id"]], showlegend=False,
                         hovertemplate="Impactados %{x:,}<extra></extra>"))
    fig.add_trace(go.Bar(y=sub.etq, x=sub.convertidos, orientation="h",
                         name=d["nombre"], marker_color=d["color"],
                         text=sub.convertidos, textposition="outside",
                         textfont=dict(family=MONO, size=11, color=TINTA),
                         hovertemplate="Convertidos %{x:,}<extra></extra>"))
fig.update_layout(barmode="overlay", bargap=0.35)
fig.update_xaxes(showgrid=False, showticklabels=False, ticks="", linecolor="rgba(0,0,0,0)",
                 range=[0, alc.impactados.max() * 1.18])
fig.update_yaxes(showgrid=False, tickfont=dict(family=MONO, size=10, color=TINTA))
guardar("alcance", fig, barras_h(fig, alc, 150, 26))

# --- 3.4 Dia de la semana en que se firma
fig = go.Figure()
for d in DS:
    s = d["dia_semana"]
    fig.add_trace(go.Bar(x=s.dia, y=s.pct, name=d["nombre"], marker_color=d["color"],
                         customdata=s[["conv"]],
                         hovertemplate="%{x}: %{y}% (%{customdata[0]:,})<extra></extra>"))
fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
fig.update_xaxes(tickfont=dict(family=SANS, size=12, color=TINTA), tickangle=0)
fig.update_yaxes(ticksuffix="%", title=dict(text="% de las renovaciones del dataset",
                                            font=dict(family=MONO, size=11, color=GRIS)))
guardar("dia_semana", fig, 340)

# --- 3.5 Latencia
fig = go.Figure()
for d in DS:
    l = d["latencia"].copy()
    l["pct"] = 100 * l.conv / l.conv.sum()
    fig.add_trace(go.Bar(x=l.dias, y=l.pct.round(2), name=d["nombre"], marker_color=d["color"],
                         customdata=l[["conv"]],
                         hovertemplate="Dia %{x}: %{y}% (%{customdata[0]:,})<extra></extra>"))
fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.06)
fig.update_xaxes(dtick=1, title=dict(text="dias entre el envio y la renovacion",
                                     font=dict(family=MONO, size=11, color=GRIS)))
fig.update_yaxes(ticksuffix="%")
guardar("latencia", fig, 340)

# --- 3.6 Curva acumulada en dia relativo
fig = go.Figure()
for d in DS:
    a = d["acum"]
    fig.add_trace(go.Scatter(x=a.dia_rel, y=a.pct.round(1), mode="lines", name=d["nombre"],
                             line=dict(color=d["color"], width=2.5, shape="hv"),
                             hovertemplate="Dia %{x}: %{y}% acumulado<extra></extra>"))
fig.update_xaxes(dtick=5, title=dict(text="dias desde el primer envio de cada dataset",
                                     font=dict(family=MONO, size=11, color=GRIS)))
fig.update_yaxes(ticksuffix="%", range=[0, 105])
guardar("acum", fig, 340)

# --- 3.7 Canal del mensaje
canales = sorted({c for d in DS for c in d["canal"].canal})
fig = go.Figure()
for d in DS:
    c = d["canal"].set_index("canal").reindex(canales).fillna(0).reset_index()
    fig.add_trace(go.Bar(x=[x.upper() for x in c.canal], y=c.pct.round(1), name=d["nombre"],
                         marker_color=d["color"], customdata=c[["conv"]],
                         text=c.pct.round(1).astype(str) + "%", textposition="outside",
                         textfont=dict(family=MONO, size=11, color=TINTA),
                         hovertemplate="%{x}: %{y}% (%{customdata[0]:,})<extra></extra>"))
fig.update_layout(barmode="group", bargap=0.45, bargroupgap=0.08)
fig.update_xaxes(tickfont=dict(family=MONO, size=12, color=TINTA), tickangle=0)
fig.update_yaxes(ticksuffix="%", range=[0, 115])
guardar("canal", fig, 320)

# --- 3.8 Toques previos
fig = go.Figure()
for d in DS:
    t = d["toques"].copy()
    t["pct"] = 100 * t.conv / t.conv.sum()
    fig.add_trace(go.Bar(x=t.toques, y=t.pct.round(2), name=d["nombre"], marker_color=d["color"],
                         customdata=t[["conv"]],
                         hovertemplate="%{x} impactos: %{y}% (%{customdata[0]:,})<extra></extra>"))
fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.06)
fig.update_xaxes(dtick=1, title=dict(text="impactos recibidos antes de renovar",
                                     font=dict(family=MONO, size=11, color=GRIS)))
fig.update_yaxes(ticksuffix="%")
guardar("toques", fig, 340)


# --- 3.9 Dimensiones de la renovacion, en barras horizontales agrupadas
def grafica_dimension(clave, nombre_fig, top=TOP_N, usar_indice=False):
    top_vals = (pd.concat([d[clave][["valor", "conv_atribuidas"]] for d in DS])
                .groupby("valor", as_index=False).sum()
                .nlargest(top, "conv_atribuidas").valor.tolist())
    top_vals = list(reversed(top_vals))
    fig = go.Figure()
    for d in DS:
        s = d[clave].set_index("valor").reindex(top_vals).reset_index()
        y = [str(v).title() for v in s.valor]
        if usar_indice:
            x = s.indice.fillna(0)
            txt = s.indice.fillna(0).astype(int).astype(str)
            hov = ("%{y} &middot; " + d["nombre"] + "<br>Indice %{x}"
                   "<br>%{customdata[0]:,} atribuidas<extra></extra>")
        else:
            x = s.pct_atribuido.fillna(0)
            txt = s.pct_atribuido.fillna(0).round(1).astype(str) + "%"
            hov = ("%{y} &middot; " + d["nombre"] + "<br>%{x}% del journey"
                   "<br>%{customdata[0]:,} atribuidas &middot; base %{customdata[1]}%<extra></extra>")
        fig.add_trace(go.Bar(
            y=y, x=x, orientation="h", name=d["nombre"], marker_color=d["color"],
            text=txt, textposition="outside",
            textfont=dict(family=MONO, size=10, color=TINTA),
            customdata=s[["conv_atribuidas", "pct_base"]].fillna(0),
            hovertemplate=hov))
    if usar_indice:
        fig.add_vline(x=100, line=dict(color=TINTA, width=1, dash="dot"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.06)
    mx = max(fig.data[i].x.max() for i in range(len(fig.data)))
    fig.update_xaxes(showgrid=False, showticklabels=False, ticks="",
                     linecolor="rgba(0,0,0,0)", range=[0, mx * 1.22])
    fig.update_yaxes(showgrid=False, tickfont=dict(family=SANS, size=11, color=TINTA))
    guardar(nombre_fig, fig, barras_h(fig, top_vals, 150, 24 * len(DS) + 14))


grafica_dimension("geo", "geo", top=10, usar_indice=True)
grafica_dimension("ciudad", "ciudad", top=10)
grafica_dimension("venta", "venta", top=6)
grafica_dimension("plan", "plan", top=TOP_N)

# =============================================================================
# 4. DASHBOARD HTML
# =============================================================================


def fig_html(nombre):
    return pio.to_html(FIGS[nombre], include_plotlyjs=False, full_html=False,
                       div_id=f"fig-{nombre}",
                       config={"displayModeBar": True, "displaylogo": False,
                               "responsive": True, "scrollZoom": True,
                               "modeBarButtonsToRemove": ["lasso2d", "select2d",
                                                          "toggleSpikelines",
                                                          "hoverClosestCartesian",
                                                          "hoverCompareCartesian"],
                               "toImageButtonOptions": {"format": "png", "scale": 3,
                                                        "filename": f"tigo_reno_{nombre}"}})


def num(x, dec=0):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "&mdash;"
    return f"{x:,.{dec}f}".replace(",", " ")


def tabla_paso(d):
    filas = []
    for _, r in d["paso"].sort_values("paso_idx").iterrows():
        filas.append(
            f"<tr><td>{int(r.paso_idx)}</td><td>{r.canvas_step_nm}</td>"
            f"<td>{str(r.canal).upper()}</td><td>{str(r.primera_fecha)[:10]}</td>"
            f"<td>{int(r.dia_rel)}</td><td>{num(r.msisdn_impactados)}</td>"
            f"<td>{num(r.msisdn_convertidos)}</td><td>{r.tasa_pct}%</td></tr>")
    return ("<table class='tbl'><thead><tr><th>#</th><th>Paso</th><th>Canal</th>"
            "<th>Fecha</th><th>Dia rel.</th><th>Impactados</th><th>Convertidos</th>"
            f"<th>Tasa</th></tr></thead><tbody>{''.join(filas)}</tbody></table>")


a, b = DS[0], DS[1]
z_ab, p_ab = z_dos_proporciones(int(a["kpi"]["convertidos"]), int(a["kpi"]["impactados"]),
                                int(b["kpi"]["convertidos"]), int(b["kpi"]["impactados"]))
if z_ab is None:
    sig = "No hay volumen suficiente para contrastar los dos datasets."
else:
    sig = (f"z = {z_ab:.2f} &middot; p = {p_ab:.3f}: si ambos datasets rindieran igual, "
           f"habria {p_ab*100:.1f}% de probabilidad de ver una brecha de este tamano solo "
           "por azar. " + ("Por debajo del 5%, la diferencia se sostiene al 95% de confianza."
                           if p_ab < 0.05 else "Arriba del 5%, todavia puede ser ruido."))

delta = round(a["kpi"]["tasa"] - b["kpi"]["tasa"], 2)
fecha_gen = dt.datetime.now().strftime("%d/%m/%Y %H:%M")

CSS = """
:root{
  --azul:#112CB7; --azul-4:#EDF0FB; --amarillo:#F5B700; --ambar:#8A6200; --ama-4:#FDF4DA;
  --tinta:#0A0A0A; --gris:#767680; --regla:#E7E7E9; --papel:#FFFFFF; --hueso:#FAFAFA;
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
header.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:24px;
                 padding-top:18px;padding-bottom:18px}
.brand{display:flex;align-items:center;gap:16px}
.brand img{height:26px;display:block}
.brand .fallback{font-weight:700;font-size:22px;letter-spacing:-.03em;color:var(--azul)}
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
nav.anchors a:hover{color:var(--azul);border-color:var(--azul)}

.hero{background:var(--papel);border-bottom:1px solid var(--regla);padding:72px 0 0}
.hero h1{font-family:var(--serif);font-weight:400;font-size:clamp(34px,5vw,58px);line-height:1.06;
         letter-spacing:-.025em;margin:0 0 18px;max-width:20ch}
.hero h1 em{font-style:normal;color:var(--azul)}
.hero h1 b{font-weight:400;color:var(--ambar)}
.hero p.lede{max-width:66ch;color:#3A3A40;margin:0 0 44px;font-size:17px}

.par{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--regla)}
.par>div{padding:32px 28px 38px;border-right:1px solid var(--regla)}
.par>div:last-child{border-right:0}
.par .quien{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;
            display:flex;align-items:center;gap:9px;margin-bottom:20px}
.par .quien i{width:11px;height:11px;border-radius:999px;display:inline-block;font-style:normal}
.par .quien .rango{color:var(--gris);letter-spacing:.04em}
.cifras{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}
.cifras .lab{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
             color:var(--gris);display:block;margin-bottom:10px}
.cifras .val{font-weight:600;font-size:clamp(30px,3.6vw,46px);line-height:.95;
             letter-spacing:-.04em;font-variant-numeric:tabular-nums;display:block}
.cifras .sub{font-family:var(--mono);font-size:10.5px;color:var(--gris);margin-top:9px;display:block}

section{padding:76px 0;border-bottom:1px solid var(--regla)}
section:nth-of-type(even){background:var(--papel)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
         color:var(--azul);display:block;margin-bottom:16px}
h2{font-family:var(--serif);font-weight:400;font-size:clamp(26px,3.4vw,38px);line-height:1.12;
   letter-spacing:-.02em;margin:0 0 14px;max-width:28ch}
.dek{max-width:72ch;color:#3A3A40;margin:0 0 36px}

.card{background:var(--papel);border:1px solid var(--regla);border-radius:12px;padding:26px 22px}
section:nth-of-type(even) .card{background:var(--hueso)}
.card + .card{margin-top:20px}
.card h3{font-weight:600;font-size:15px;letter-spacing:-.01em;margin:0 0 4px}
.card .note{font-family:var(--mono);font-size:11px;color:var(--gris);margin:0 0 18px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.grid2 .card + .card{margin-top:0}

.leyenda{display:flex;gap:26px;flex-wrap:wrap;margin:0 0 34px;padding:16px 0;
         border-top:1px solid var(--regla);border-bottom:1px solid var(--regla)}
.leyenda span{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;
              display:flex;align-items:center;gap:9px;color:var(--gris)}
.leyenda i{width:11px;height:11px;border-radius:999px;display:inline-block}

.tbl{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.tbl th{font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
        color:var(--gris);text-align:right;padding:10px 12px;border-bottom:1px solid var(--regla);
        font-weight:400}
.tbl th:first-child,.tbl td:first-child,.tbl th:nth-child(2),.tbl td:nth-child(2){text-align:left}
.tbl td{padding:11px 12px;border-bottom:1px solid #F2F2F4;text-align:right}
.tbl tbody tr:hover{background:var(--azul-4)}
.scroll{overflow-x:auto}

.modebar{padding-top:2px!important}
.modebar-container .modebar{background:transparent!important}
.modebar-group{background:transparent!important;padding-left:4px!important}
.modebar-btn svg path{fill:#B4B4BC!important;transition:fill .15s}
.modebar-btn:hover svg path,.modebar-btn.active svg path{fill:var(--azul)!important}
.js-plotly-plot .modebar-btn{opacity:1!important}

footer{padding:56px 0 80px;background:var(--papel)}
footer .wrap{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap}
footer p{font-family:var(--mono);font-size:11px;color:var(--gris);margin:0}

.reveal{opacity:0;transform:translateY(12px)}
.reveal.on{opacity:1;transform:none;transition:opacity .6s cubic-bezier(.16,1,.3,1),
           transform .6s cubic-bezier(.16,1,.3,1)}

@media (max-width:900px){
  .wrap{padding:0 20px}
  .par,.grid2,.cifras{grid-template-columns:1fr}
  .par>div{border-right:0;border-bottom:1px solid var(--regla)}
  .cifras{gap:26px}
}
@media (prefers-reduced-motion:reduce){
  .reveal,.reveal.on{opacity:1;transform:none;transition:none}
  html{scroll-behavior:auto}
}
"""

JS = """
const io=new IntersectionObserver(e=>e.forEach(x=>{if(x.isIntersecting){x.target.classList.add('on');io.unobserve(x.target)}}),{threshold:.06});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
window.addEventListener('resize',()=>document.querySelectorAll('.js-plotly-plot').forEach(p=>Plotly.Plots.resize(p)));
"""

tarjetas = "".join(f'''
  <div>
    <div class="quien"><i style="background:{d['color']}"></i>{d['nombre']}
      <span class="rango">{d['rango_e'][0]} &rarr; {d['rango_r'][1]}</span></div>
    <div class="cifras">
      <div><span class="lab">Impactados</span>
        <span class="val">{num(d['kpi']['impactados'])}</span>
        <span class="sub">{num(d['kpi']['envios'])} envios &middot; {int(d['kpi']['pasos'])} pasos</span></div>
      <div><span class="lab">Atribuidas</span>
        <span class="val" style="color:{d['color_texto']}">{num(d['kpi']['conversiones'])}</span>
        <span class="sub">{num(d['kpi']['convertidos'])} numeros</span></div>
      <div><span class="lab">Tasa</span>
        <span class="val">{d['kpi']['tasa']}%</span>
        <span class="sub">{d['kpi']['share']}% del total del periodo</span></div>
    </div>
  </div>''' for d in DS)

leyenda = "".join(f'<span><i style="background:{d["color"]}"></i>{d["nombre"]}</span>' for d in DS)

tablas = "".join(f'''
    <div class="card scroll">
      <h3><span style="color:{d['color_texto']}">&#9679;</span> {d['nombre']}</h3>
      <p class="note">Periodo {d['rango_e'][0]} a {d['rango_r'][1]} &middot;
         dia rel. = dias desde el primer envio</p>
      {tabla_paso(d)}
    </div>''' for d in DS)

HTML = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Journey de renovaciones | comparativo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&family=Instrument+Serif&display=swap" rel="stylesheet">
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
      <span class="kicker">Renovaciones &middot; comparativo de journeys</span>
    </div>
    <div class="meta">{len(DS)} datasets<br>Generado {fecha_gen}</div>
  </div>
</header>

<nav class="anchors">
  <div class="wrap">
    <a href="#resumen">Resumen</a>
    <a href="#estructura">Estructura</a>
    <a href="#rendimiento">Rendimiento</a>
    <a href="#ritmo">Ritmo</a>
    <a href="#perfil">Perfil</a>
    <a href="#detalle">Detalle</a>
  </div>
</nav>

<div class="hero">
  <div class="wrap">
    <h1><em>{DS[0]['nombre']}</em> y <b>{DS[1]['nombre']}</b>, medidos con la misma regla.</h1>
    <p class="lede">Cada dataset se procesa por separado, con su propio calendario y su propia
    estructura de pasos. La comparacion corre sobre ejes relativos &mdash; dia 0 es el primer
    envio de cada journey, y los pasos se numeran en orden cronologico &mdash; de modo que dos
    periodos distintos se pueden leer en la misma grafica.</p>
  </div>
  <div class="wrap"><div class="par">{tarjetas}</div></div>
</div>

<section id="resumen">
  <div class="wrap reveal">
    <span class="eyebrow">01</span>
    <h2>La brecha entre los dos</h2>
    <p class="dek">La tasa se calcula sobre la base efectivamente contactada de cada dataset,
    asi que se puede comparar aunque los volumenes sean muy distintos.
    Diferencia: {abs(delta)} puntos porcentuales. {sig}</p>
    <div class="leyenda">{leyenda}</div>
    <div class="card">
      <h3>Renovaciones atribuidas por canal del mensaje</h3>
      <p class="note">Reparto interno de cada dataset, en porcentaje</p>
      {fig_html('canal')}
    </div>
  </div>
</section>

<section id="estructura">
  <div class="wrap reveal">
    <span class="eyebrow">02</span>
    <h2>Estructura de cada journey</h2>
    <p class="dek">Cada burbuja es un paso ubicado en el dia relativo en que salio; el tamano es
    el volumen de renovaciones que se le atribuyen. Sirve para ver si los dos journeys tienen la
    misma cadencia o si uno concentra los envios de otra forma.</p>
    <div class="leyenda">{leyenda}</div>
    <div class="card">
      <h3>Linea de tiempo, en dias desde el primer envio</h3>
      <p class="note">Posicion = dia relativo &middot; tamano = renovaciones atribuidas</p>
      {fig_html('timeline')}
    </div>
    <div class="card">
      <h3>Alcance y conversion de cada paso</h3>
      <p class="note">Barra clara = msisdn impactados &middot; barra llena = renovaciones atribuidas</p>
      {fig_html('alcance')}
    </div>
  </div>
</section>

<section id="rendimiento">
  <div class="wrap reveal">
    <span class="eyebrow">03</span>
    <h2>Rendimiento paso a paso</h2>
    <p class="dek">Los pasos se alinean por su numero de orden, no por su nombre ni por su fecha,
    de modo que el primer envio de un journey se compara contra el primer envio del otro.</p>
    <div class="leyenda">{leyenda}</div>
    <div class="card">
      <h3>Tasa de conversion por paso</h3>
      <p class="note">Renovaciones atribuidas sobre msisdn que recibieron ese paso</p>
      {fig_html('tasa_paso')}
    </div>
  </div>
</section>

<section id="ritmo">
  <div class="wrap reveal">
    <span class="eyebrow">04</span>
    <h2>Cuando renueva la gente</h2>
    <p class="dek">Tres cortes que no dependen del calendario y por eso se pueden superponer:
    cuantos dias pasan entre el envio y la renovacion, en que dia de la semana se firma, y cuantos
    impactos habia recibido esa persona antes de convertir. Todo en porcentaje del propio dataset
    para que la diferencia de tamano no distorsione la forma.</p>
    <div class="leyenda">{leyenda}</div>
    <div class="card">
      <h3>Dia de la semana en que se firma la renovacion</h3>
      <p class="note">% de las renovaciones atribuidas de cada dataset</p>
      {fig_html('dia_semana')}
    </div>
    <div class="grid2">
      <div class="card">
        <h3>Dias entre el envio y la renovacion</h3>
        <p class="note">Distribucion de la latencia</p>
        {fig_html('latencia')}
      </div>
      <div class="card">
        <h3>Impactos acumulados antes de renovar</h3>
        <p class="note">Mensajes del journey recibidos hasta ese momento</p>
        {fig_html('toques')}
      </div>
    </div>
    <div class="card">
      <h3>Ritmo acumulado del journey</h3>
      <p class="note">% de las renovaciones ya logradas a cada dia relativo</p>
      {fig_html('acum')}
    </div>
  </div>
</section>

<section id="perfil">
  <div class="wrap reveal">
    <span class="eyebrow">05</span>
    <h2>Quien renueva y por donde</h2>
    <p class="dek">Medicion de la composicion de cada journey contra la base de renovaciones de su
    propio periodo. Indice 100 significa que ese journey convierte al segmento en la misma
    proporcion en que aparece en el total; arriba de 100 lo trae de mas. Con pocas conversiones
    atribuidas estos cortes se mueven mucho, conviene leerlos junto al conteo absoluto.</p>
    <div class="leyenda">{leyenda}</div>
    <div class="card">
      <h3>Departamento, indice contra la base del periodo</h3>
      <p class="note">Linea punteada = 100 &middot; top 10 por volumen atribuido</p>
      {fig_html('geo')}
    </div>
    <div class="grid2">
      <div class="card">
        <h3>Ciudades</h3>
        <p class="note">% de las renovaciones atribuidas de cada dataset</p>
        {fig_html('ciudad')}
      </div>
      <div class="card">
        <h3>Donde se cierra la renovacion</h3>
        <p class="note">Punto de venta que factura la transaccion</p>
        {fig_html('venta')}
      </div>
    </div>
    <div class="card">
      <h3>Plan con el que queda la linea</h3>
      <p class="note">Top {TOP_N} por volumen atribuido, en % de cada dataset</p>
      {fig_html('plan')}
    </div>
  </div>
</section>

<section id="detalle">
  <div class="wrap reveal">
    <span class="eyebrow">06</span>
    <h2>Detalle por paso</h2>
    <p class="dek">Cada paso con su fecha real, su dia relativo, su alcance y su resultado.
    Las mismas tablas se exportan a CSV en la carpeta de cada dataset.</p>
    {tablas}
  </div>
</section>

<footer>
  <div class="wrap">
    <p>Fuente: envios de Braze &middot; renovaciones facturables mobile<br>
       Ventana de atribucion {TOPE_VENTANA_DIAS} dias &middot; last touch</p>
    <p>Generado {fecha_gen}</p>
  </div>
</footer>

<script>{JS}</script>
</body>
</html>
"""

SALIDA_HTML = os.path.join(OUT_DIR, "reporte_renovaciones_comparativo.html")
with open(SALIDA_HTML, "w", encoding="utf-8") as fh:
    fh.write(HTML)

print("=" * 74)
for d in DS:
    print(f"{d['nombre']:<12} {num(d['kpi']['impactados']):>10} impactados  "
          f"{num(d['kpi']['conversiones']):>8} atribuidas  {d['kpi']['tasa']:>6}%  "
          f"latencia mediana {num(d['kpi']['lat_med'])} d")
print(f"{'Brecha':<12} {abs(delta)} pp"
      + (f"  (z = {z_ab:.2f}, p = {p_ab:.3f})" if z_ab is not None else ""))
print("=" * 74)
print(f"Dashboard -> {SALIDA_HTML}")
print(f"CSV       -> {OUT_DIR}")