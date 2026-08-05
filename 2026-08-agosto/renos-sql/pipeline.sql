/*TASK 0 - DONE*/ 

SELECT 
campaign_id_key, 
campaign_nm, 
braze_campaign_tp, 
journey_nm, 
channel_tp
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_campaign_dim
WHERE d_instance_tp = 'gt'
  AND campaign_id_key IN (
      '0342f305-7e46-4b9a-bff0-4d075093a1f5',
      '59f07812-1cd1-4a86-997f-192992a83ec1'
  );

/* Validación de snapshots de perfil - DONE*/
SELECT fct_dt, count(*) AS filas
FROM 
gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
WHERE cntry_cd = 'gt'
  AND fct_dt IN ('2026-06-01', '2026-07-01', '2026-07-31')
GROUP BY 1;  

/* V2 — Medir antes de exportar (dentro de este mismo bloque, no es paso aparte) */
SELECT count(*) AS envios_con_msisdn,
       count(DISTINCT e.external_user_id) AS usuarios,
       count(DISTINCT p.msisdn) AS telefonos,
       min(e.fecha_envio) AS desde, max(e.fecha_envio) AS hasta
FROM envios e JOIN perfil p ON p.external_id = e.external_user_id;


/* Fase 1+2 — Envíos + resolución de teléfono   */
WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-06-01', '2026-07-01', '2026-07-31')
      AND cntry_cd = 'gt'
      AND msisdn IS NOT NULL
    GROUP BY external_id
),
envios AS (
    SELECT lower(step_name) AS canal, external_user_id, date_send_dt AS fecha_envio,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
    WHERE dt >= DATE '2026-05-22' AND dt < DATE '2026-08-01'
      AND instance_tp = 'gt'
      AND step_name IN ('SMS', 'WhatsApp')
      AND campaign_id IN (<IDS>)

    UNION ALL
    SELECT 'push', external_user_id, date_send_dt,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-05-22' AND dt < DATE '2026-08-01' AND instance_tp = 'gt'
      AND campaign_id IN (<IDS>)
)
SELECT
    p.msisdn AS msisdn, e.external_user_id AS cuenta_id, e.fecha_envio,
    e.canal, e.canvas_step_nm, e.canvas_variation_nm, e.campaign_id
FROM envios e
JOIN perfil p ON p.external_id = e.external_user_id
GROUP BY 1, 2, 3, 4, 5, 6, 7;


/* Renovaciones en Horus (30 min) / Propuesta */
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

/* Consulta Original */
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


SELECT DISTINCT step_name, length(step_name) AS largo
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
WHERE dt >= DATE '2026-05-22' AND dt < DATE '2026-08-01'
  AND instance_tp = 'gt'
  AND campaign_id = '0342f305-7e46-4b9a-bff0-4d075093a1f5';

  AND trim(lower(step_name)) IN ('sms', 'whatsapp')

  AND lower(trim(campaign_id)) = lower(trim('0342f305-7e46-4b9a-bff0-4d075093a1f5'))

/*+++++++++++++++++++++++++++++*/

WITH perfiles AS (
    SELECT DISTINCT
        external_id,
        msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-06-01', '2026-07-01', '2026-07-31')
      AND cntry_cd = 'gt'
      AND external_id IS NOT NULL
      AND msisdn IS NOT NULL
),
envios AS (
    SELECT DISTINCT external_user_id
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-05-22'
      AND dt < DATE '2026-08-01'
      AND instance_tp = 'gt'
      AND campaign_id IN (
        '0342f305-7e46-4b9a-bff0-4d075093a1f5',
      '59f07812-1cd1-4a86-997f-192992a83ec1'
      )
)
SELECT
    p.msisdn,
    count(DISTINCT p.external_id) AS external_ids_con_envio
FROM perfiles p
JOIN envios e
    ON e.external_user_id = p.external_id
GROUP BY p.msisdn
HAVING count(DISTINCT p.external_id) > 1
ORDER BY external_ids_con_envio DESC;

/* ++++++++++++++++++++++++++++++++++++++++++++++++++++++ */

WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-06-04', '2026-06-12', '2026-07-02')
      AND cntry_cd = 'gt'
      AND msisdn IS NOT NULL
    GROUP BY external_id
),
envios AS (
    SELECT lower(step_name) AS canal, external_user_id, date_send_dt AS fecha_envio,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
    WHERE dt >= DATE '2026-06-04' AND dt < DATE '2026-07-10'
      AND instance_tp = 'gt'
      AND trim(lower(step_name)) IN ('sms', 'whatsapp')
      AND trim(lower(campaign_id)) IN (
    trim(lower('0342f305-7e46-4b9a-bff0-4d075093a1f5')),
    trim(lower('59f07812-1cd1-4a86-997f-192992a83ec1')))

    UNION all
    SELECT 'push', external_user_id, date_send_dt,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-06-04' AND dt < DATE '2026-07-10' AND instance_tp = 'gt'
      AND trim(lower(campaign_id)) IN (
    trim(lower('0342f305-7e46-4b9a-bff0-4d075093a1f5')),
    trim(lower('59f07812-1cd1-4a86-997f-192992a83ec1')))
)
SELECT
    p.msisdn AS msisdn, e.external_user_id AS cuenta_id, e.fecha_envio,
    e.canal, e.canvas_step_nm, e.canvas_variation_nm, e.campaign_id
FROM envios e
JOIN perfil p ON p.external_id = e.external_user_id
GROUP BY 1, 2, 3, 4, 5, 6, 7;

/* + + + + + + + + + + + + + + + + + + + + + + + + + + + + + + + */

WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-06-04', '2026-06-12', '2026-07-02')
      AND cntry_cd = 'gt'
      AND msisdn IS NOT NULL
    GROUP BY external_id
),
envios AS (
    SELECT lower(step_name) AS canal, external_user_id, date_send_dt AS fecha_envio,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
    WHERE dt >= DATE '2026-06-04' AND dt < DATE '2026-07-10'
      AND instance_tp = 'gt'
      AND trim(lower(step_name)) IN ('sms', 'whatsapp')
      AND trim(lower(campaign_id)) IN (
          trim(lower('0342f305-7e46-4b9a-bff0-4d075093a1f5')),
          trim(lower('59f07812-1cd1-4a86-997f-192992a83ec1')))
    UNION ALL
    SELECT 'push', external_user_id, date_send_dt,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-06-04' AND dt < DATE '2026-07-10' AND instance_tp = 'gt'
      AND trim(lower(campaign_id)) IN (
          trim(lower('0342f305-7e46-4b9a-bff0-4d075093a1f5')),
          trim(lower('59f07812-1cd1-4a86-997f-192992a83ec1')))
)
SELECT e.canal, count(*) AS filas
FROM envios e
JOIN perfil p ON p.external_id = e.external_user_id
GROUP BY 1;

/* + + + + + + + + + + + + + + + + + + + + + + + + + + + + + + + */


WITH perfil AS (
    SELECT external_id, arbitrary(msisdn) AS msisdn
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct
    WHERE fct_dt IN ('2026-06-04', '2026-06-12', '2026-07-02')
      AND cntry_cd = 'gt'
      AND msisdn IS NOT NULL
    GROUP BY external_id
),
push AS (
    SELECT 'push' AS canal, external_user_id, date_send_dt AS fecha_envio,
           campaign_id, canvas_step_nm, canvas_variation_nm
    FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
    WHERE dt >= DATE '2026-06-04' AND dt < DATE '2026-07-10' AND instance_tp = 'gt'
      AND trim(lower(campaign_id)) IN (
          trim(lower('0342f305-7e46-4b9a-bff0-4d075093a1f5')),
          trim(lower('59f07812-1cd1-4a86-997f-192992a83ec1')))
)
SELECT count(*) AS filas
FROM push e
JOIN perfil p ON p.external_id = e.external_user_id;