/*TASK 0*/

SELECT 
campaign_id_key, 
campaign_nm, 
braze_campaign_tp, 
journey_nm, 
channel_tp
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_campaign_dim
WHERE d_instance_tp = 'gt'
  AND campaign_id_key IN (
      '3151c9f0-6602-4798-8d66-8bd251e5b2ad',
      '6cb29791-72dc-4231-afba-96a024002e3e'
  );

/* Validación de snapshots de perfil */
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


/* Renovaciones en Horus (30 min) */
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