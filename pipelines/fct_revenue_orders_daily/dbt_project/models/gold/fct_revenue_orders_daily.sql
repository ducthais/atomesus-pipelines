-- Model gold fct_revenue_orders_daily. Sinh tự động từ Spec, không sửa tay.
{{ config(
    materialized='incremental',
    unique_key=['payment_date']
) }}

select
    cast(date_trunc('day', payment.payment_date) as date) as "payment_date",
    SUM(payment.amount_usd) as "total_revenue",
    COUNT(DISTINCT payment.payment_id) as "total_orders"

from {{ ref('stg_fct_revenue_orders_daily__payment') }} as payment
inner join {{ ref('stg_fct_revenue_orders_daily__rental') }} as rental
    on payment.rental_id = rental.rental_id

where true

group by 1
