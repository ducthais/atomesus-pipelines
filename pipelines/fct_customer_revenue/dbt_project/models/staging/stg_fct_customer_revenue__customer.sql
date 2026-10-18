-- Staging của nguồn customer (postgres pagila_pg) cho pipeline fct_customer_revenue.
-- Sinh tự động từ Spec, không sửa tay.
{{ config(
    materialized='table',
    post_hook=[
        "create or replace table {{ this.incorporate(path={'identifier': 'stg_fct_customer_revenue__customer__rejected'}) }} as select * from {{ this }} where _reject_reason is not null",
        "delete from {{ this }} where _reject_reason is not null",
        "alter table {{ this }} drop column _reject_reason",
        "alter table {{ this }} drop column _raw_values",
    ]
) }}

with bronze as (

    select * from {{ source('bronze', 'raw_customer') }}

),

typed as (

    select
        try_cast(bronze."customer_id" as integer) as "customer_id",
        bronze."customer_id" as _raw_1,
        try_cast(bronze."first_name" as varchar) as "first_name",
        bronze."first_name" as _raw_2,
        try_cast(bronze."last_name" as varchar) as "last_name",
        bronze."last_name" as _raw_3,
        try_cast(bronze."create_date" as date) as "create_date",
        bronze."create_date" as _raw_4,
        bronze."customer_id" as _dedupe_key_1,
        bronze."customer_id" as _dedupe_order,
        bronze._dlt_id as _bronze_id

    from bronze

),

checked as (

    select
        *,
        case
            when _raw_1 is not null and "customer_id" is null
                then 'cast:customer_id'
            when _raw_2 is not null and "first_name" is null
                then 'cast:first_name'
            when _raw_3 is not null and "last_name" is null
                then 'cast:last_name'
            when _raw_4 is not null and "create_date" is null
                then 'cast:create_date'
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
    "customer_id",
    "first_name",
    "last_name",
    "create_date",
    cast(null as varchar) as _reject_reason,
    cast(null as varchar) as _raw_values
from clean
where _dedupe_rank = 1

union all

select
    "customer_id",
    "first_name",
    "last_name",
    "create_date",
    _reject_reason,
    cast(to_json({'customer_id': _raw_1, 'first_name': _raw_2, 'last_name': _raw_3, 'create_date': _raw_4}) as varchar) as _raw_values
from checked
where _reject_reason is not null
