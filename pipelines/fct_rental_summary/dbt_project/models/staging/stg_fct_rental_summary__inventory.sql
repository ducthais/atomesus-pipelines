-- Staging của nguồn inventory (postgres pagila_pg) cho pipeline fct_rental_summary.
-- Sinh tự động từ Spec, không sửa tay.
{{ config(
    materialized='table',
    post_hook=[
        "create or replace table {{ this.incorporate(path={'identifier': 'stg_fct_rental_summary__inventory__rejected'}) }} as select * from {{ this }} where _reject_reason is not null",
        "delete from {{ this }} where _reject_reason is not null",
        "alter table {{ this }} drop column _reject_reason",
        "alter table {{ this }} drop column _raw_values",
    ]
) }}

with bronze as (

    select * from {{ source('bronze', 'raw_inventory') }}

),

typed as (

    select
        try_cast(bronze."inventory_id" as integer) as "inventory_id",
        bronze."inventory_id" as _raw_1,
        try_cast(bronze."store_id" as integer) as "store_id",
        bronze."store_id" as _raw_2,
        bronze."inventory_id" as _dedupe_key_1,
        bronze."inventory_id" as _dedupe_order,
        bronze._dlt_id as _bronze_id

    from bronze

),

checked as (

    select
        *,
        case
            when _raw_1 is not null and "inventory_id" is null
                then 'cast:inventory_id'
            when _raw_2 is not null and "store_id" is null
                then 'cast:store_id'
            when (inventory_id IS NULL)
                then 'reject_if:inventory_id IS NULL'
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
    "inventory_id",
    "store_id",
    cast(null as varchar) as _reject_reason,
    cast(null as varchar) as _raw_values
from clean
where _dedupe_rank = 1

union all

select
    "inventory_id",
    "store_id",
    _reject_reason,
    cast(to_json({'inventory_id': _raw_1, 'store_id': _raw_2}) as varchar) as _raw_values
from checked
where _reject_reason is not null
