"""Dagster code location cho pipeline fct_customer_revenue. Sinh tự động từ Spec, không sửa tay."""

import os
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    in_process_executor,
    multi_asset,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from src.dagster_runtime.execute import run_ingestion, warehouse_path

RUNTIME_CONTRACT = 2
MODEL = "fct_customer_revenue"
REPO_ROOT = Path(__file__).resolve().parents[3]
DBT_PROJECT = DbtProject(project_dir=REPO_ROOT / "dbt_project", profiles_dir=REPO_ROOT / "dbt_project")
DBT_PROJECT.prepare_if_dev()
# Bảng bronze do dlt ghi; key trùng key của dbt source ("bronze", <bảng>) sau khi thêm tiền tố model, nên Dagster nối
# lineage dlt → staging → gold.
BRONZE_TABLES = ['raw_customer', 'raw_payment']


class PrefixTranslator(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props):
        return AssetKey([MODEL, *super().get_asset_key(dbt_resource_props).path])

    def get_group_name(self, dbt_resource_props):
        return MODEL


@multi_asset(
    specs=[AssetSpec(AssetKey([MODEL, "bronze", table]), group_name=MODEL, kinds={"dlt", "duckdb"}) for table in BRONZE_TABLES],
    name="fct_customer_revenue_ingestion",
)
def fct_customer_revenue_ingestion(context: AssetExecutionContext):
    # dlt chạy trong subprocess, chỉ nhận credential của các nguồn pipeline này đọc và file DuckDB riêng của nó.
    yield from run_ingestion(context, MODEL, REPO_ROOT)


@dbt_assets(
    manifest=DBT_PROJECT.manifest_path,
    select="+fct_customer_revenue",
    name="fct_customer_revenue_transform",
    dagster_dbt_translator=PrefixTranslator(),
)
def fct_customer_revenue_transform(context: AssetExecutionContext):
    # Đặt ở đây, không đặt lúc import: run worker nạp mọi pipeline, mỗi run chỉ chạy job của một pipeline.
    os.environ["WAREHOUSE_PATH"] = warehouse_path(MODEL)
    yield from DbtCliResource(project_dir=DBT_PROJECT).cli(["build"], context=context).stream()


fct_customer_revenue_job = define_asset_job(
    "fct_customer_revenue_job",
    selection=AssetSelection.assets(fct_customer_revenue_ingestion, fct_customer_revenue_transform),
    executor_def=in_process_executor,  # không nạp lại toàn bộ code location cho từng step
)

fct_customer_revenue_schedule = ScheduleDefinition(
    job=fct_customer_revenue_job,
    cron_schedule="0 2 * * *",
    execution_timezone="Asia/Ho_Chi_Minh",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[
        fct_customer_revenue_ingestion,
        fct_customer_revenue_transform,
    ],
    jobs=[
        fct_customer_revenue_job,
    ],
    schedules=[
        fct_customer_revenue_schedule,
    ],
)
