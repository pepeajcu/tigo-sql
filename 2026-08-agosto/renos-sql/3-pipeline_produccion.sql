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
