"""Dagster code location cho pipeline fct_rental_summary. Sinh tự động từ Spec, không sửa tay."""

from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData

from ingestion.fct_rental_summary_pipeline import pipeline, source

REPO_ROOT = Path(__file__).resolve().parents[3]
DBT_PROJECT = DbtProject(project_dir=REPO_ROOT / "dbt_project", profiles_dir=REPO_ROOT / "dbt_project")
DBT_PROJECT.prepare_if_dev()


class BronzeTranslator(DagsterDltTranslator):
    def get_asset_spec(self, data: DltResourceTranslatorData):
        return super().get_asset_spec(data).replace_attributes(key=AssetKey(["bronze", data.resource.table_name]))


@dlt_assets(
    dlt_source=source(),
    dlt_pipeline=pipeline(),
    name="fct_rental_summary_ingestion",
    group_name="fct_rental_summary",
    dagster_dlt_translator=BronzeTranslator(),
)
def fct_rental_summary_ingestion(context: AssetExecutionContext, dlt: DagsterDltResource):
    yield from dlt.run(context=context)


@dbt_assets(manifest=DBT_PROJECT.manifest_path, select="+fct_rental_summary", name="fct_rental_summary_transform")
def fct_rental_summary_transform(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


fct_rental_summary_job = define_asset_job(
    "fct_rental_summary_job",
    selection=AssetSelection.assets(fct_rental_summary_ingestion, fct_rental_summary_transform),
)

fct_rental_summary_schedule = ScheduleDefinition(
    job=fct_rental_summary_job,
    cron_schedule="0 2 * * *",
    execution_timezone="Asia/Ho_Chi_Minh",
    default_status=DefaultScheduleStatus.RUNNING,
)

defs = Definitions(
    assets=[
        fct_rental_summary_ingestion,
        fct_rental_summary_transform,
    ],
    jobs=[
        fct_rental_summary_job,
    ],
    schedules=[
        fct_rental_summary_schedule,
    ],
    resources={"dlt": DagsterDltResource(), "dbt": DbtCliResource(project_dir=DBT_PROJECT)},
)
