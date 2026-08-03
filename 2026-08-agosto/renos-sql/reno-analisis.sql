/** 

Tengo 3 db que almacenan registros de envios de "eventos" braze_chnnl_email, braze_chnnl_inapp, braze_chnnl_push; Estas bases una de sus columnas ofrece el "id de campaña", pero no su "nombre de campaña"... (dataset: trim)

El "nombre de campaña" lo tiene braze,campaign_dim buscado por "id de campaña" (dataset: trim)

Las tablas de "eventos" me dan un "id" de usuario pero no es el numero telefonico, si no, el "id de su cuenta", cada cuenta puede tener muchos numeros telefónicos asociados. (dataset: trim)

Tengo otra tabla en donde estan registradas las "conversiones / renovaciones" por numero telefónico. (dataset: horus) pero el dato que tengo del usuario no es su numero telefonico si no su cuenta. 

Tengo otra tabla llamda "profile" que me da la cuenta y su numeros telefonicos asociados (dataset: trim)

Lo que deseo saber es un reporte... donde categorizar por día (fecha) del envio y tipo de envio (eventos) para saber en que día "convirtieron / renovaron" más los clientes (numeros telefónicos) dentro de un periodo de tiempo (2 semanas)

Ayudame a estructurar el pipeline / que consultas sql / como debo de ejecutar las consultas para poder obtener el reporte..  todo debe de estar optimizado para consultas de base de datos de millones (alto volumen de datos) de registros. btw: dime si hace falta algo para lograrlo.

**/