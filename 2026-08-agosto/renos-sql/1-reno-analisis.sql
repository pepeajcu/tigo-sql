/** 

Tengo 3 db que almacenan registros de envios de "eventos" braze_chnnl_email, braze_chnnl_inapp, braze_chnnl_push; Estas bases una de sus columnas ofrece el "id de campaña", pero no su "nombre de campaña"... (dataset: trim)

El "nombre de campaña" lo tiene braze,campaign_dim buscado por "id de campaña" (dataset: trim)

Las tablas de "eventos" me dan un "id" de usuario pero no es el numero telefonico, si no, el "id de su cuenta", cada cuenta puede tener muchos numeros telefónicos asociados. (dataset: trim)

Tengo otra tabla en donde estan registradas las "conversiones / renovaciones" por numero telefónico. (dataset: horus) pero el dato que tengo del usuario no es su numero telefonico si no su cuenta. 

Tengo otra tabla llamda "profile" que me da la cuenta y su numeros telefonicos asociados (dataset: trim)

Lo que deseo saber es un reporte... donde categorizar por día (fecha) del envio y tipo de envio (eventos) para saber en que día "convirtieron / renovaron" más los clientes (numeros telefónicos) dentro de un periodo de tiempo (2 semanas)

Ayudame a estructurar el pipeline / que consultas sql / como debo de ejecutar las consultas para poder obtener el reporte..  todo debe de estar optimizado para consultas de base de datos de millones (alto volumen de datos) de registros. btw: dime si hace falta algo para lograrlo.

**/

/* Consulta con "contentcard* -- Averiguar que "envio es contentcard" */
select 
	instance_tp, 
	event_tp , 
	date_send_dt , 
	campaign_id , 
	external_user_id , 
	canvas_step_id , 
	canvas_step_nm , 
	event_id 
from 
	gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_contentcard_fct
    -- where CAST(created_at_ts as timestamp)
	-- between timestamp '2026-05-01 00:00:00'
	-- and timestamp '2026-07-28 23:59:59'
	-- and d_instance_tp = 'gt'
where date_send_dt between date '2026-05-01' and date '2026-07-28'
and instance_tp = 'gt'  
 
 
/* Consulta: Tablas por Tipo de Envíos*/
select 
	instance_tp,
	date_send_dt,
	campaign_id , 
	external_user_id ,
	canvas_step_id ,
	canvas_step_nm ,
	event_id ,
from
	gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_inapp_fct
limit 10

select 
	*
from
	gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_push_fct
limit 10

select 
	*
from
	gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_chnnl_webhook_fct
limit 10

/* Consulta: Campañas de Braze*/
select 
	campaign_id_key,
	campaign_nm ,
	md5_key ,
	created_at_ts ,
	braze_campaign_tp ,
	d_instance_tp
from 
	gt_awsmichqice_glue.hq_anl_prd_engmt_link.braze_campaign_dim
where CAST(created_at_ts as timestamp)
	between timestamp '2026-05-01 00:00:00'
	and timestamp '2026-07-28 23:59:59'
	and d_instance_tp = 'gt'
	limit 100