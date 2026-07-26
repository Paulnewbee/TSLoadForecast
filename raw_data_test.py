import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from DataShuttle.clients.ercot_api import ErcotAPI
from DataShuttle.ingestion.pipeline import IngestionPipeline
from DataShuttle.ingestion.ercot.weather_zone_load import (
    ErcotWeatherZoneLoadJob,
)
from DataShuttle.ingestion.ercot.load_zone_load import (
    ErcotLoadZoneLoadJob,
)

load_dotenv("./.dev.env")

database_url = (
    f"postgresql+psycopg2://"
    f"{os.environ['POSTGRES_USER']}:"
    f"{os.environ['POSTGRES_PASSWORD']}@"
    f"{os.environ['POSTGRES_HOST']}:"
    f"{os.environ['POSTGRES_PORT']}/"
    f"{os.environ['POSTGRES_DB']}"
)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
)

api = ErcotAPI(
    username=os.environ["ERCOT_USERNAME"],
    password=os.environ["ERCOT_PASSWORD"],
    subscription_key=os.environ["ERCOT_SUBSCRIPTION_KEY"],
)

pipeline = IngestionPipeline(
    engine=engine,
    database_name=os.environ["POSTGRES_DB"],
)

start_date = "2026-07-07"
end_date = "2026-07-25"

jobs = [
    ErcotWeatherZoneLoadJob(
        api=api,
        start_date=start_date,
        end_date=end_date,
    ),
    ErcotLoadZoneLoadJob(
        api=api,
        start_date=start_date,
        end_date=end_date,
    ),
]

try:
    for job in jobs:
        print(f"Running {job.dataset_name}...")

        run_id = pipeline.run(
            job=job,
            parameters={
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        print(f"Finished {job.dataset_name}: {run_id}")

finally:
    engine.dispose()
