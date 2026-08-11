[Trino] space-int-bi-trino- > [Databases]

gt_awsmichq_glue
gt_awsmichqice_glue
gt_ceph_icbrg
system

Cada [Databases] tiene sus Schemas... 

Para "gt_awsmichqice_glue" su [schema] es: hq_anl_prd_engmt_link y sus tablas de este [schema] son:

braze_campaign_dim /* Tiene la informacion de las campañas (nombre de campaña, id de campaña) */
braze_campaign_dim_backup_20250331
braze_campaign_dim_hist
braze_campaign_dim_tags
braze_chnnl_contentcard_fct
braze_chnnl_email_aws_detail
braze_chnnl_email_aws_fct
braze_chnnl_email_fct /* Envios por Email */
braze_chnnl_email_fct_co
braze_chnnl_inapp_fct
braze_chnnl_push_fct /* Envios push */
braze_chnnl_webhook_fct /* Envios SMS y WhatsApp */
braze_cstmevent_fct
braze_profile_fct /* Contiene información del perfil del cliente (id cuenta externa) (numero de telefono)*
braze_resum
dar_tigoid_profiles_daily
hq_cstmr_digital_pre2post_mitigo_bot
hq_cstmr_digital_tbo_mitigo
tigochat_agent_tracker_per_day
tigochat_conversations_histories
tigochat_conversations_metrics
tigochat_conversations_report
tigochat_ia_typification
tigochat_ia_typification_v0
tigochat_metrics_messages
tigochat_reopened_detail
tigochat_transfer_detail
tigochat_user_time_tracker_interval
tigochat_user_time_trackers_detail
tigosecurity_subscriptions_fact
webanalytics_events_fct_tigo_sports


Ahora te muestro las columnas de: gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_campaign_dim

campaign_id_key
campaign_nm
segment_tp
client_tp
campaign_tp
event_tp
app_tp
product_tp
environment_tp
trigger_tp
channel_tp
md5_key
created_at_ts
country_tp
active_f
d_instance_tp
journey_nm
journey_step_nm
archived_f
draft_f
enabled_f
braze_campaign_tp
addons
base_type
business_unit_product
landing
tags_json

Ahora te muestro las columnas de: gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_inapp_fct

instance_tp
event_tp
date_send_dt
dt
campaign_id
external_user_id
canvas_step_id
canvas_step_nm
canvas_variation_nm
event_id
send_nbr
impression_nbr
click_nbr
min_date_impression_dt
max_date_impression_dt
min_date_click_dt
max_date_click_dt
updated_at_dt
conversion_f
date_conversion_dt
campaign_type


Ahora te muestro las columnas de: gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct

instance_tp
event_tp
date_send_dt
dt
campaign_id
external_user_id
canvas_step_id
canvas_step_nm
canvas_variation_nm
event_id
send_nbr
open_nbr
bounce_nbr
min_date_open_dt
max_date_open_dt
min_date_bounce_dt
max_date_bounce_dt
updated_at_dt
message_extras
event_broker_id
conversion_f
date_conversion_dt
custom_event_id
campaign_type

Ahora te muestro las columnas de: gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct

instance_tp
event_tp
date_send_dt
dt
campaign_id
external_user_id
canvas_step_id
canvas_step_nm
canvas_variation_nm
event_id
send_nbr
updated_at_dt
message_extras
event_broker_id
conversion_f
date_conversion_dt
custom_event_id
campaign_type
step_name

Ahora te muestro las columnas de: gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_profile_fct

external_id
braze_id
phone
email
account_alias
account_identification
account_type
national_identification
national_identification_type
authentication_provider
braze_tigo_id
profile_type
product_type
bs_un
bs_ln
msisdn
contract_id
braze_created_at
update_at
fct_dt
cntry_cd

Esta tabla no es de braze, si no de Horus, gt_std_engtm_pii.st_webanalytics_events y estas son sus columnas:

user_id
bs_un
msisdn
contract_id
event_name
event_source
properties
event_timestamp
context
event_proxy
journey_nm
fct_dt_mic
ppn_dt
prttn_dt
