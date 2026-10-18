-- Model gold fct_customer_revenue. Sinh tự động từ Spec, không sửa tay.
{{ config(
    materialized='incremental',
    unique_key=['customer_id']
) }}

select
    customer.customer_id as "customer_id",
    SUM(payment.__m1) as "total_revenue",
    COALESCE(SUM(payment.__m2), 0) as "order_count"

from {{ ref('stg_fct_customer_revenue__customer') }} as customer
inner join (SELECT payment.customer_id, SUM(payment.amount) AS __m1, COUNT(payment.payment_id) AS __m2 FROM {{ ref('stg_fct_customer_revenue__payment') }} AS payment GROUP BY payment.customer_id) as payment
    on payment.customer_id = customer.customer_id

where true
{% if is_incremental() %}
    -- Chỉ tính lại từ phân vùng mới nhất đã có; unique_key gộp đè phần trùng.
    and customer.customer_id >= (select max("customer_id") from {{ this }})
{% endif %}

group by 1
