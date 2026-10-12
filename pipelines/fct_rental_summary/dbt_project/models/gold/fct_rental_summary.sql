-- Model gold fct_rental_summary. Sinh tự động từ Spec, không sửa tay.
{{ config(
    materialized='incremental',
    unique_key=['payment_date', 'store_id']
) }}

select
    cast(date_trunc('month', payment.payment_date) as date) as "payment_date",
    inventory.store_id as "store_id",
    SUM(payment.amount) as "total_revenue",
    COUNT(DISTINCT rental.rental_id) as "total_rentals"

from {{ ref('stg_fct_rental_summary__payment') }} as payment
inner join {{ ref('stg_fct_rental_summary__rental') }} as rental
    on payment.rental_id = rental.rental_id
inner join {{ ref('stg_fct_rental_summary__inventory') }} as inventory
    on rental.inventory_id = inventory.inventory_id

where true
{% if is_incremental() %}
    -- Chỉ tính lại từ phân vùng mới nhất đã có; unique_key gộp đè phần trùng.
    and payment.payment_date >= (select max("payment_date") from {{ this }})
{% endif %}

group by 1, 2
