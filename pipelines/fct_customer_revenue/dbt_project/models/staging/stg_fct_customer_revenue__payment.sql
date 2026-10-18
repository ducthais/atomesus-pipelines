-- Staging của nguồn payment (postgres pagila_pg) cho pipeline fct_customer_revenue.
-- Sinh tự động từ Spec, không sửa tay.
{{ config(
    materialized='table',
    post_hook=[
        "create or replace table {{ this.incorporate(path={'identifier': 'stg_fct_customer_revenue__payment__rejected'}) }} as select * from {{ this }} where _reject_reason is not null",
        "delete from {{ this }} where _reject_reason is not null",
        "alter table {{ this }} drop column _reject_reason",
        "alter table {{ this }} drop column _raw_values",
    ]
) }}

with bronze as (

    select * from {{ source('bronze', 'raw_payment') }}

),

typed as (

    select
        try_cast(bronze."payment_id" as integer) as "payment_id",
        bronze."payment_id" as _raw_1,
        try_cast(bronze."customer_id" as integer) as "customer_id",
        bronze."customer_id" as _raw_2,
        try_cast(bronze."amount" as decimal(18,2)) as "amount",
        bronze."amount" as _raw_3,
        bronze."payment_id" as _dedupe_key_1,
        bronze."payment_id" as _dedupe_order,
        bronze._dlt_id as _bronze_id

    from bronze

),

checked as (

    select
        *,
        case
            when _raw_1 is not null and "payment_id" is null
                then 'cast:payment_id'
            when _raw_2 is not null and "customer_id" is null
                then 'cast:customer_id'
            when _raw_3 is not null and "amount" is null
                then 'cast:amount'
        end as _reject_reason

    from typed

),

clean as (

    select
        *,
        row_number() over (
            partition by _dedupe_key_1
            order by _dedupe_order asc nulls last, _bronze_id
        ) as _dedupe_rank

    from checked
    where _reject_reason is null

)

select
    "payment_id",
    "customer_id",
    "amount",
    cast(null as varchar) as _reject_reason,
    cast(null as varchar) as _raw_values
from clean
where _dedupe_rank = 1

union all

select
    "payment_id",
    "customer_id",
    "amount",
    _reject_reason,
    cast(to_json({'payment_id': _raw_1, 'customer_id': _raw_2, 'amount': _raw_3}) as varchar) as _raw_values
from checked
where _reject_reason is not null
