-- Staging của nguồn rental (postgres pagila_pg) cho pipeline fct_revenue_orders_daily.
-- Sinh tự động từ Spec, không sửa tay.
{{ config(
    materialized='table',
    post_hook=[
        "create or replace table {{ this.incorporate(path={'identifier': 'stg_fct_revenue_orders_daily__rental__rejected'}) }} as select * from {{ this }} where _reject_reason is not null",
        "delete from {{ this }} where _reject_reason is not null",
        "alter table {{ this }} drop column _reject_reason",
        "alter table {{ this }} drop column _raw_values",
    ]
) }}

with bronze as (

    select * from {{ source('bronze', 'raw_rental') }}

),

typed as (

    select
        try_cast(bronze."rental_id" as integer) as "rental_id",
        bronze."rental_id" as _raw_1,
        try_cast(bronze."rental_date" as timestamp) as "rental_date",
        bronze."rental_date" as _raw_2,
        bronze."rental_id" as _dedupe_key_1,
        bronze."rental_id" as _dedupe_order,
        bronze._dlt_id as _bronze_id

    from bronze

),

checked as (

    select
        *,
        case
            when _raw_1 is not null and "rental_id" is null
                then 'cast:rental_id'
            when _raw_2 is not null and "rental_date" is null
                then 'cast:rental_date'
            when (rental_id IS NULL)
                then 'reject_if:rental_id IS NULL'
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
    "rental_id",
    "rental_date",
    cast(null as varchar) as _reject_reason,
    cast(null as varchar) as _raw_values
from clean
where _dedupe_rank = 1

union all

select
    "rental_id",
    "rental_date",
    _reject_reason,
    cast(to_json({'rental_id': _raw_1, 'rental_date': _raw_2}) as varchar) as _raw_values
from checked
where _reject_reason is not null
