"""Ingestion cho pipeline fct_rental_summary. Sinh tự động từ Spec, không sửa tay.

Kết nối đọc từ biến môi trường theo quy ước dlt, ví dụ SOURCES__SALES_PG__CREDENTIALS.
Đích là DuckDB tại WAREHOUSE_PATH, dataset bronze.
"""

import os

import dlt
from dlt.sources.sql_database import sql_table

PIPELINE_NAME = "fct_rental_summary"


def resource_payment():
    table = sql_table(
        credentials=dlt.secrets["sources.pagila_pg.credentials"],
        schema="pagila",
        table="payment",
        defer_table_reflect=True,  # đọc cấu trúc bảng lúc chạy, không phải lúc Dagster nạp code location
        incremental=dlt.sources.incremental("payment_date"),
    )
    return table.apply_hints(
        table_name="raw_payment",
        primary_key=['payment_id'],
        write_disposition="merge",
    )


def resource_rental():
    table = sql_table(
        credentials=dlt.secrets["sources.pagila_pg.credentials"],
        schema="pagila",
        table="rental",
        defer_table_reflect=True,  # đọc cấu trúc bảng lúc chạy, không phải lúc Dagster nạp code location
        incremental=dlt.sources.incremental("rental_date"),
    )
    return table.apply_hints(
        table_name="raw_rental",
        primary_key=['rental_id'],
        write_disposition="merge",
    )


def resource_inventory():
    table = sql_table(
        credentials=dlt.secrets["sources.pagila_pg.credentials"],
        schema="pagila",
        table="inventory",
        defer_table_reflect=True,  # đọc cấu trúc bảng lúc chạy, không phải lúc Dagster nạp code location
    )
    return table.apply_hints(
        table_name="raw_inventory",
        primary_key=['inventory_id'],
        write_disposition="replace",
    )


@dlt.source(name=PIPELINE_NAME)
def source():
    # Nhiều nguồn: mỗi resource đọc trong luồng riêng (dlt extract song song), không chờ nguồn chậm nhất tuần tự.
    return [
        resource_payment().parallelize(),
        resource_rental().parallelize(),
        resource_inventory().parallelize(),
    ]


def pipeline() -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination=dlt.destinations.duckdb(os.environ["WAREHOUSE_PATH"]),
        dataset_name="bronze",
    )


if __name__ == "__main__":
    print(pipeline().run(source()))
