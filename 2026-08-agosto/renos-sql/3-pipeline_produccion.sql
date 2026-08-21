/* PAOS 1 -  */

WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-07-22', '2026-07-31', '2026-08-10')
      AND cntry_cd = 'gt'
      AND msisdn IS NOT NULL
    GROUP BY external_id
),
envios AS (
    SELECT lower(step_name) AS canal, external_user_id, date_send_dt AS fecha_envio,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
    WHERE dt >= DATE '2026-07-17' AND dt < DATE '2026-08-10'
      AND instance_tp = 'gt'
      AND trim(lower(step_name)) IN ('sms', 'whatsapp')
      AND trim(lower(campaign_id)) IN (
    trim(lower('3151c9f0-6602-4798-8d66-8bd251e5b2ad')),
    trim(lower('6cb29791-72dc-4231-afba-96a024002e3e')))

    UNION all
    SELECT 'push', external_user_id, date_send_dt,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-07-17' AND dt < DATE '2026-08-10' AND instance_tp = 'gt'
      AND trim(lower(campaign_id)) IN (
    trim(lower('3151c9f0-6602-4798-8d66-8bd251e5b2ad')),
    trim(lower('6cb29791-72dc-4231-afba-96a024002e3e')))
)
SELECT
    p.msisdn AS msisdn, e.external_user_id AS cuenta_id, e.fecha_envio,
    e.canal, e.canvas_step_nm, e.canvas_variation_nm, e.campaign_id
FROM envios e
JOIN perfil p ON p.external_id = e.external_user_id
GROUP BY 1, 2, 3, 4, 5, 6, 7;


/* PASO 2 */

select 
sls.fct_dt mes, 
sls.evnt_dt fecha, 
sls.evnt_typ, 
sls.msisdn_dd numero, 
sls.ar_sscrbr_dd anexo
from smy.dm_bi_sls_sttstcs_mnth sls
where sls.fct_dt = date '2026-07-01'
and sls.evnt_typ in ('RENOVACION')
and case when sls.evnt_typ = 'RENOVACION' then sls.sb_bs_un else sls.mv_bs_un end = 'MOBILE'
and sls.bllbl_cd = 'FACTURABLE'

select 
sls.fct_dt mes, 
sls.evnt_dt fecha, 
sls.evnt_typ, 
sls.msisdn_dd numero, 
sls.ar_sscrbr_dd anexo
from smy.dm_bi_sls_sttstcs_mnth sls
where sls.fct_dt = date '2026-08-01'
and sls.evnt_typ in ('RENOVACION')
and case when sls.evnt_typ = 'RENOVACION' then sls.sb_bs_un else sls.mv_bs_un end = 'MOBILE'
and sls.bllbl_cd = 'FACTURABLE'




WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-07-22', '2026-07-31', '2026-08-10')
      AND cntry_cd = 'gt'
    GROUP BY external_id
),
ids AS (
    SELECT DISTINCT lower(step_name) AS canal, external_user_id
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
    WHERE dt >= DATE '2026-07-17' AND dt < DATE '2026-08-10'
      AND instance_tp = 'gt'
      AND trim(lower(step_name)) IN ('sms', 'whatsapp')
      AND trim(lower(campaign_id)) IN (
          trim(lower('3151c9f0-6602-4798-8d66-8bd251e5b2ad')),
          trim(lower('6cb29791-72dc-4231-afba-96a024002e3e')))

    UNION ALL
    SELECT DISTINCT 'push' AS canal, external_user_id
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-07-17' AND dt < DATE '2026-08-10'
      AND instance_tp = 'gt'
      AND trim(lower(campaign_id)) IN (
          trim(lower('3151c9f0-6602-4798-8d66-8bd251e5b2ad')),
          trim(lower('6cb29791-72dc-4231-afba-96a024002e3e')))
),
cruce AS (
    SELECT i.canal, i.external_user_id, p.msisdn
    FROM ids i
    LEFT JOIN perfil p ON p.external_id = i.external_user_id
),
enumerado AS (
    SELECT *,
           row_number() OVER (PARTITION BY canal ORDER BY msisdn NULLS LAST) AS rn
    FROM cruce
)
SELECT
    canal,
    array_agg(external_user_id) AS external_user_ids,
    array_agg(msisdn) AS msisdns
FROM enumerado
WHERE rn <= 50
GROUP BY canal;











WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-07-22', '2026-07-31', '2026-08-10')
      AND cntry_cd = 'gt'
    GROUP BY external_id
),
ids AS (
    SELECT DISTINCT lower(step_name) AS canal, external_user_id
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
    WHERE dt >= DATE '2026-07-17' AND dt < DATE '2026-08-10'
      AND instance_tp = 'gt'
      AND trim(lower(step_name)) IN ('sms', 'whatsapp')

    UNION ALL
    SELECT DISTINCT 'push' AS canal, external_user_id
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-07-17' AND dt < DATE '2026-08-10'
      AND instance_tp = 'gt'
),
cruce AS (
    SELECT i.canal, i.external_user_id, p.msisdn
    FROM ids i
    LEFT JOIN perfil p ON p.external_id = i.external_user_id
),
enumerado AS (
    SELECT *,
           row_number() OVER (PARTITION BY canal ORDER BY msisdn NULLS LAST) AS rn
    FROM cruce
)
SELECT
    canal,
    count(*)                                    AS total_ids,
    count(*) FILTER (WHERE msisdn IS NOT NULL)   AS con_msisdn,
    count(*) FILTER (WHERE msisdn IS NULL)       AS sin_msisdn,
    array_agg(external_user_id) FILTER (WHERE rn <= 50) AS ejemplo_external_user_ids,
    array_agg(msisdn) FILTER (WHERE rn <= 50)           AS ejemplo_msisdns
FROM enumerado
GROUP BY canal; 














-- ----------------------------------------------------------------------------
-- QUERY 1 — Eventos unificados, 5 canales, ultimos 90 dias, sin filtro de
-- campana (exportar como: eventos_90d.csv)
-- ----------------------------------------------------------------------------
-- El filtro de fecha va sobre "dt" (columna de particion en las 5 tablas) con
-- un valor ya calculado, no una funcion sobre la columna misma — asi Trino
-- puede saltarse particiones enteras sin leerlas.

WITH rango AS (
    SELECT date_add('day', -90, current_date) AS desde,
           current_date                        AS hasta
)
SELECT
    'email'          AS canal,
    instance_tp, event_tp, date_send_dt, dt,
    campaign_id, external_user_id,
    canvas_step_id, canvas_step_nm, canvas_variation_nm,
    event_id, campaign_type,
    CAST(NULL AS VARCHAR) AS step_name
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_email_aws_detail, rango
WHERE dt >= rango.desde AND dt < rango.hasta
UNION ALL
SELECT
    'push'           AS canal,
    instance_tp, event_tp, date_send_dt, dt,
    campaign_id, external_user_id,
    canvas_step_id, canvas_step_nm, canvas_variation_nm,
    event_id, campaign_type,
    CAST(NULL AS VARCHAR) AS step_name
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct, rango
WHERE dt >= rango.desde AND dt < rango.hasta
UNION ALL
SELECT
    'webhook'        AS canal,
    instance_tp, event_tp, date_send_dt, dt,
    campaign_id, external_user_id,
    canvas_step_id, canvas_step_nm, canvas_variation_nm,
    event_id, campaign_type,
    step_name
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct, rango
WHERE dt >= rango.desde AND dt < rango.hasta
UNION ALL
SELECT
    'inapp'          AS canal,
    instance_tp, event_tp, date_send_dt, dt,
    campaign_id, external_user_id,
    canvas_step_id, canvas_step_nm, canvas_variation_nm,
    event_id, campaign_type,
    CAST(NULL AS VARCHAR) AS step_name
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_inapp_fct, rango
WHERE dt >= rango.desde AND dt < rango.hasta
UNION ALL
SELECT
    'contentcard'    AS canal,
    instance_tp, event_tp, date_send_dt, dt,
    campaign_id, external_user_id,
    canvas_step_id, canvas_step_nm, canvas_variation_nm,
    event_id, campaign_type,
    CAST(NULL AS VARCHAR) AS step_name
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_contentcard_fct, rango
WHERE dt >= rango.desde AND dt < rango.hasta;


-- ----------------------------------------------------------------------------
-- QUERY 2 — Perfil (msisdn por las 2 llaves, con el fallback ya validado)
-- (exportar como: perfil_90d.csv)
-- ----------------------------------------------------------------------------
-- 3 snapshots calculados dinamicamente dentro del mismo rango de 90 dias
-- (inicio, mitad, mas reciente) en vez de las 90 fotos diarias completas —
-- evita escanear ~90x el volumen para un dato que casi no cambia dia a dia.

WITH fechas_snapshot AS (
    SELECT
        date_add('day', -90, current_date) AS f_inicio,
        date_add('day', -45, current_date) AS f_medio,
        date_add('day', -1,  current_date) AS f_reciente
),
perfil_base AS (
    SELECT external_id, braze_tigo_id, msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct, fechas_snapshot
    WHERE cntry_cd = 'gt'
      AND fct_dt IN (
          CAST(fechas_snapshot.f_inicio AS VARCHAR),
          CAST(fechas_snapshot.f_medio AS VARCHAR),
          CAST(fechas_snapshot.f_reciente AS VARCHAR)
      )
      AND msisdn IS NOT NULL
),
por_braze_tigo AS (
    SELECT braze_tigo_id, arbitrary(msisdn) AS msisdn
    FROM perfil_base
    WHERE braze_tigo_id IS NOT NULL
    GROUP BY braze_tigo_id
),
por_external AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM perfil_base
    GROUP BY external_id
)
SELECT
    braze_tigo_id AS user_key,
    braze_tigo_id,
    CAST(NULL AS VARCHAR) AS external_id,
    msisdn
FROM por_braze_tigo
UNION ALL
SELECT
    external_id AS user_key,
    CAST(NULL AS VARCHAR) AS braze_tigo_id,
    external_id,
    msisdn
FROM por_external;




WITH
-- Rango de fechas: se recalcula solo, sin editar nada, cada vez que corres
-- el query — siempre trae los ultimos 90 dias desde HOY.
rango AS (
    SELECT
        date_add('day', -90, current_date)            AS desde_date,
        current_date                                    AS hasta_date,
        CAST(date_add('day', -90, current_date) AS VARCHAR) AS desde_str,
        CAST(current_date AS VARCHAR)                        AS hasta_str
),
-- 3 snapshots de perfil dentro del mismo rango de 90 dias (inicio, mitad,
-- mas reciente) en vez de las 90 fotos diarias completas — evita escanear
-- ~90x el volumen para un dato que casi no cambia dia a dia.
fechas_snapshot AS (
    SELECT
        date_add('day', -90, current_date) AS f_inicio,
        date_add('day', -45, current_date) AS f_medio,
        date_add('day', -1,  current_date) AS f_reciente
),
perfil_base AS (
    SELECT external_id, braze_tigo_id, msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct, fechas_snapshot
    WHERE cntry_cd = 'gt'
      AND fct_dt IN (
          CAST(fechas_snapshot.f_inicio AS VARCHAR),
          CAST(fechas_snapshot.f_medio AS VARCHAR),
          CAST(fechas_snapshot.f_reciente AS VARCHAR)
      )
      AND msisdn IS NOT NULL
),
perfil_braze_tigo AS (
    SELECT braze_tigo_id, arbitrary(msisdn) AS msisdn
    FROM perfil_base
    WHERE braze_tigo_id IS NOT NULL
    GROUP BY braze_tigo_id
),
perfil_external AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM perfil_base
    GROUP BY external_id
),
-- Eventos unificados de los 5 canales, mismas columnas, sin filtro de
-- campana. El filtro de fecha va sobre "dt" (columna de particion) con un
-- valor ya calculado, no una funcion sobre la columna misma — asi Trino
-- puede saltarse particiones enteras sin leerlas.
eventos AS (
    SELECT
        'email' AS canal, instance_tp, event_tp, CAST(date_send_dt AS VARCHAR) AS date_send_dt, dt,
        campaign_id, external_user_id, canvas_step_id, canvas_step_nm,
        canvas_variation_nm, event_id, campaign_type,
        CAST(NULL AS VARCHAR) AS step_name
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_email_aws_detail, rango
    WHERE dt >= rango.desde_str AND dt < rango.hasta_str
    UNION ALL
    SELECT
        'push' AS canal, instance_tp, event_tp, CAST(date_send_dt AS VARCHAR) AS date_send_dt, CAST(dt AS VARCHAR) AS dt,
        campaign_id, external_user_id, canvas_step_id, canvas_step_nm,
        canvas_variation_nm, event_id, campaign_type,
        CAST(NULL AS VARCHAR) AS step_name
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct, rango
    WHERE dt >= rango.desde_date AND dt < rango.hasta_date
    UNION ALL
    SELECT
        'webhook' AS canal, instance_tp, event_tp, CAST(date_send_dt AS VARCHAR) AS date_send_dt, CAST(dt AS VARCHAR) AS dt,
        campaign_id, external_user_id, canvas_step_id, canvas_step_nm,
        canvas_variation_nm, event_id, campaign_type,
        step_name
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct, rango
    WHERE dt >= rango.desde_date AND dt < rango.hasta_date
    UNION ALL
    SELECT
        'inapp' AS canal, instance_tp, event_tp, CAST(date_send_dt AS VARCHAR) AS date_send_dt, CAST(dt AS VARCHAR) AS dt,
        campaign_id, external_user_id, canvas_step_id, canvas_step_nm,
        canvas_variation_nm, event_id, campaign_type,
        CAST(NULL AS VARCHAR) AS step_name
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_inapp_fct, rango
    WHERE dt >= rango.desde_date AND dt < rango.hasta_date
    UNION ALL
    SELECT
        'contentcard' AS canal, instance_tp, event_tp, CAST(date_send_dt AS VARCHAR) AS date_send_dt, CAST(dt AS VARCHAR) AS dt,
        campaign_id, external_user_id, canvas_step_id, canvas_step_nm,
        canvas_variation_nm, event_id, campaign_type,
        CAST(NULL AS VARCHAR) AS step_name
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_contentcard_fct, rango
    WHERE dt >= rango.desde_date AND dt < rango.hasta_date
)
-- Resultado final: cada evento con su msisdn ya resuelto (fallback de
-- llaves ya validado: braze_tigo_id primero, external_id de respaldo).
-- No se descartan los que no encuentran msisdn (quedan en NULL) — como es
-- un pipeline generico de descarga, mejor conservarlos visibles que
-- perderlos en silencio; filtralos despues segun el analisis que hagas.
SELECT
    COALESCE(pbt.msisdn, pe.msisdn) AS msisdn,
    e.external_user_id AS cuenta_id,
    e.canal,
    e.instance_tp,
    e.event_tp,
    e.date_send_dt,
    e.dt,
    e.campaign_id,
    e.canvas_step_id,
    e.canvas_step_nm,
    e.canvas_variation_nm,
    e.event_id,
    e.campaign_type,
    e.step_name
FROM eventos e
LEFT JOIN perfil_braze_tigo pbt ON pbt.braze_tigo_id = e.external_user_id
LEFT JOIN perfil_external   pe  ON pe.external_id    = e.external_user_id;