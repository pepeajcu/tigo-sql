/*TASK 0*/

SELECT campaign_id_key, campaign_nm, braze_campaign_tp, journey_nm, channel_tp
FROM gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_campaign_dim
WHERE d_instance_tp = 'gt'
  AND campaign_id_key IN (
      '3151c9f0-6602-4798-8d66-8bd251e5b2ad',
      '6cb29791-72dc-4231-afba-96a024002e3e'
  );