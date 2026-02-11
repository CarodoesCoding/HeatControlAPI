import os
from influxdb_client import InfluxDBClient, BucketsApi, OrgsApi
from influxdb_client.client.write_api import SYNCHRONOUS

INFLUX_URL = os.getenv("INFLUX_URL")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET")

def setup_influxdb():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    orgs_api = client.orgs_api()
    buckets_api = client.buckets_api()

    # Check if org and bucket exist
    orgs = orgs_api.find_orgs()
    org = next((o for o in orgs.orgs if o.name == INFLUX_ORG), None)
    if not org:
        print(f"Organization '{INFLUX_ORG}' not found. Please create it in InfluxDB UI or via CLI.")
        return
    
    buckets = buckets_api.find_buckets()
    bucket = next((b for b in buckets.buckets if b.name == INFLUX_BUCKET), None)
    if bucket:
        print(f"Bucket '{INFLUX_BUCKET}' already exists.")
    # Create bucket if it does not exist
    else:
        retention_rules = []
        bucket = buckets_api.create_bucket(bucket_name=INFLUX_BUCKET, org_id=org.id, retention_rules=retention_rules)
        print(f"Bucket '{INFLUX_BUCKET}' created.")

    client.close()

if __name__ == "__main__":
    setup_influxdb()