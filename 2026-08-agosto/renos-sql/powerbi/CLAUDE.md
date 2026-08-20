# powerbi/

Carpeta de trabajo para todo lo relacionado con el dashboard de Power BI del journey de
renovaciones (traducción de `python-atribucion/3-analisis-reno_dashboard.py` a Power Query + DAX).
Cualquier cosa nueva sobre este tema — guías, medidas, notas de modelo, exports — va aquí.

## Contenido

- `guia-dax-powerbi.md` — guía completa: funciones de limpieza en Power Query (M), ventanas de
  atribución, lógica de último toque (last-touch), tabla Calendario, medidas DAX y el mapeo de cada
  gráfica del script de Python a su visual equivalente en Power BI.
- `produ/` — CSV de la ola de **Producción**: `envios_produ.csv`, `reno_produ.csv`.
- `pruebas/` — CSV de la ola de **Pruebas**: `envios_pruebas.csv`, `reno_pruebas.csv`.

## Contexto

`produ/` y `pruebas/` son **dos olas de análisis que se comparan entre sí**, no dos proyectos
separados. Mismos encabezados en ambas:

- Envíos: `msisdn, cuenta_id, fecha_envio, canal, canvas_step_nm, canvas_variation_nm, campaign_id`
  (`campaign_id` no se usa en el análisis).
- Renovaciones: `msisdn, fecha_conv, channel, ciudad, departamento, bfr_vc_nm, bfr_dt_nm`.

El modelo de Power BI (ver `guia-dax-powerbi.md`) las carga como **tablas únicas** `Envios` y
`Renovaciones` (append de ambas olas) con una columna `Dataset = "Produccion" / "Pruebas"`, para que
comparar las dos olas en un mismo visual sea solo usar `Dataset` como leyenda — no se duplican
medidas por ola.

## Convención

- Los CSV de cada ola nueva van dentro de `produ/` o `pruebas/` según corresponda, con esos mismos
  nombres de archivo (o corrige las rutas en la sección 2 de la guía si cambian).
- La guía documenta rutas, funciones M y medidas DAX con referencias a líneas del script de Python
  original — si el script cambia, revisar si la guía sigue vigente.
