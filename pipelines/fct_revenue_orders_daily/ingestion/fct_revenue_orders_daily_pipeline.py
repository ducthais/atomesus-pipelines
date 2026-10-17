"""Ingestion cho pipeline fct_revenue_orders_daily. Sinh tự động từ Spec, không sửa tay.

Kết nối đọc từ biến môi trường theo quy ước dlt, ví dụ SOURCES__SALES_PG__CREDENTIALS.
Đích là DuckDB tại WAREHOUSE_PATH, dataset bronze.
"""

import os

import dlt
from dlt.sources.sql_database import sql_table

PIPELINE_NAME = "fct_revenue_orders_daily"
# Nạp DuckDB bằng parquet (cần pyarrow): nhanh hơn nhiều so với định dạng mặc định (insert_values) khi bảng lớn.
LOADER_FILE_FORMAT = "parquet"


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
    )
    return table.apply_hints(
        table_name="raw_rental",
        primary_key=['rental_id'],
        write_disposition="replace",
    )


@dlt.source(name=PIPELINE_NAME)
def source():
    # Nhiều nguồn: mỗi resource đọc trong luồng riêng (dlt extract song song), không chờ nguồn chậm nhất tuần tự.
    return [
        resource_payment().parallelize(),
        resource_rental().parallelize(),
    ]


def pipeline() -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination=dlt.destinations.duckdb(os.environ["WAREHOUSE_PATH"]),
        dataset_name="bronze",
    )


if __name__ == "__main__":
    print(pipeline().run(source(), loader_file_format=LOADER_FILE_FORMAT))
