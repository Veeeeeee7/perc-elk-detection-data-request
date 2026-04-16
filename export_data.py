#!/usr/bin/env python3
"""
export_data.py

Downloads all image records from the Cloud SQL postgres.images table,
fetches each image from its GCS bucket, and writes a CSV with all columns
plus a local image path.

Usage:
    python export_data.py \
        --key path/to/service-account-key.json \
        --output-folder data/ \
        [--instance PROJECT:REGION:INSTANCE] \
        [--db-name mydb] \
        [--db-user myuser] \
        [--db-password secret] \
        [--skip-existing]

Required secrets (can also be set as environment variables):
    CLOUD_SQL_INSTANCE   e.g. my-project:us-central1:my-instance
    CLOUD_SQL_DB_NAME    e.g. postgres
    DB_USER              e.g. postgres
    DB_PASSWORD          database password

The service account key is used for both GCS downloads and Cloud SQL IAM
auth. If you supply --db-password (or DB_PASSWORD env var), standard
password auth is used instead of IAM auth for the DB connection.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
MISSING = []
try:
    import pg8000
except ImportError:
    MISSING.append("pg8000")
try:
    import numpy as np
    import pandas as pd
except ImportError:
    MISSING.append("pandas numpy")
try:
    from google.cloud import storage as gcs
    from google.oauth2 import service_account
except ImportError:
    MISSING.append("google-cloud-storage")
try:
    from cloud_sql_connector import Connector, IPTypes
except ImportError:
    try:
        from google.cloud.sql.connector import Connector, IPTypes
    except ImportError:
        MISSING.append("cloud-sql-python-connector[pg8000]")

if MISSING:
    print("ERROR: Missing required packages. Install them with:")
    print(f"  pip install {' '.join(MISSING)}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Export Cloud SQL image records + GCS photos to local disk."
    )
    parser.add_argument(
        "--key", required=True, metavar="KEY.json",
        help="Path to GCP service account JSON key file."
    )
    parser.add_argument(
        "--output-folder", required=True, metavar="DIR",
        help="Root output directory (images saved to DIR/images/, CSV to DIR/data.csv)."
    )
    parser.add_argument(
        "--instance", metavar="PROJECT:REGION:INSTANCE",
        help="Cloud SQL instance connection name. Overrides CLOUD_SQL_INSTANCE env var."
    )
    parser.add_argument(
        "--db-name", metavar="NAME",
        help="Database name. Overrides CLOUD_SQL_DB_NAME env var."
    )
    parser.add_argument(
        "--db-user", metavar="USER",
        help="Database user. Overrides DB_USER env var."
    )
    parser.add_argument(
        "--db-password", metavar="PASS",
        help="Database password. Overrides DB_PASSWORD env var. "
             "If omitted, IAM database authentication is attempted."
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip downloading images that already exist on disk."
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def require_env(name: str, override: str | None) -> str:
    value = override or os.environ.get(name, "").strip()
    if not value:
        print(f"ERROR: '{name}' is required. Set it via --{name.lower().replace('_', '-')} "
              f"or the {name} environment variable.")
        sys.exit(1)
    return value


def parse_gs_uri(uri: str) -> tuple[str, str]:
    """Parse gs://bucket/object into (bucket, object_name)."""
    if not uri.startswith("gs://"):
        raise ValueError(f"Not a gs:// URI: {uri!r}")
    without_scheme = uri[5:]
    slash = without_scheme.index("/")
    return without_scheme[:slash], without_scheme[slash + 1:]


def extension_from_uri(uri: str) -> str:
    """Best-effort extension from GCS object name; default to .jpg."""
    name = uri.rstrip("/").split("/")[-1]
    return Path(name).suffix.lower() if "." in name else ".jpg"


def build_local_path(images_dir: Path, img_hash: str, cloud_uri: str) -> Path:
    return images_dir / f"{img_hash}{extension_from_uri(cloud_uri)}"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_COLUMNS = [
    "id", "img_hash", "cloud_uri", "filename", "filesize_bytes",
    "width", "height", "gps_flag", "latitude", "longitude", "altitude",
    "datetime_taken", "datetime_uploaded", "temperature_c", "humidity",
    "weather_desc", "elk_count", "processed_status",
]

# Columns that should be stored as nullable integers in the DataFrame
INT_NULLABLE_COLS = ["id", "filesize_bytes", "width", "height", "elk_count"]

# Columns that should be stored as nullable floats
FLOAT_COLS = ["latitude", "longitude", "altitude", "temperature_c", "humidity"]


def fetch_dataframe(conn) -> pd.DataFrame:
    """Query postgres.images and return a typed pandas DataFrame."""
    cursor = conn.cursor()
    cursor.execute("SET search_path TO postgres")
    cursor.execute(
        f"SELECT {', '.join(DB_COLUMNS)} FROM postgres.images ORDER BY id ASC"
    )
    rows = cursor.fetchall()
    cursor.close()

    df = pd.DataFrame(rows, columns=DB_COLUMNS)

    # Apply proper dtypes using pandas nullable types so NaN doesn't corrupt
    # integer columns (the default numpy int64 cannot hold NaN).
    for col in INT_NULLABLE_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    for col in ["datetime_taken", "datetime_uploaded"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    for col in ["gps_flag", "processed_status"]:
        if col in df.columns:
            df[col] = df[col].astype("boolean")

    return df


# ---------------------------------------------------------------------------
# GCS downloads
# ---------------------------------------------------------------------------
def download_images(df: pd.DataFrame, images_dir: Path, gcs_client, skip_existing: bool):
    """
    Iterate over the DataFrame, download each GCS image, and return a numpy
    array of local path strings (empty string where download failed or N/A).
    """
    n = len(df)
    local_paths = np.empty(n, dtype=object)
    local_paths[:] = ""

    for i, (_, row) in enumerate(df.iterrows(), 1):
        cloud_uri = row["cloud_uri"] if pd.notna(row["cloud_uri"]) else ""
        img_hash  = row["img_hash"]  if pd.notna(row["img_hash"])  else f"row_{i}"

        if not cloud_uri.startswith("gs://"):
            print(f"[{i}/{n}] SKIP (no gs:// URI): img_hash={img_hash}")
            continue

        dest = build_local_path(images_dir, img_hash, cloud_uri)
        local_paths[i - 1] = str(dest)

        if skip_existing and dest.exists():
            print(f"[{i}/{n}] SKIP (exists): {dest.name}")
            continue

        try:
            bucket_name, object_name = parse_gs_uri(cloud_uri)
            blob = gcs_client.bucket(bucket_name).blob(object_name)
            blob.download_to_filename(str(dest))
            print(f"[{i}/{n}] Downloaded: {dest.name}")
        except Exception as e:
            print(f"[{i}/{n}] WARN: Failed to download {cloud_uri}: {e}")
            local_paths[i - 1] = ""

    return local_paths


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(args=None):
    if args is None:
        args = parse_args()

    # Resolve config
    key_path = Path(args.key).expanduser().resolve()
    if not key_path.exists():
        print(f"ERROR: Key file not found: {key_path}")
        sys.exit(1)

    with open(key_path) as f:
        key_data = json.load(f)

    instance = require_env("CLOUD_SQL_INSTANCE", args.instance)
    db_name  = require_env("CLOUD_SQL_DB_NAME",  args.db_name)
    db_user  = require_env("DB_USER",             args.db_user)
    db_pass  = args.db_password or os.environ.get("DB_PASSWORD", "").strip() or None

    # Prepare output dirs
    output_dir = Path(args.output_folder).expanduser()
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "data.csv"

    # GCS client
    credentials = service_account.Credentials.from_service_account_file(
        str(key_path),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    gcs_client = gcs.Client(project=key_data.get("project_id"), credentials=credentials)

    # Cloud SQL connection
    print(f"Connecting to Cloud SQL instance: {instance}")
    connector = Connector(credentials=credentials)

    def getconn():
        kwargs = dict(
            instance_connection_string=instance,
            driver="pg8000",
            db=db_name,
            user=db_user,
            ip_type=IPTypes.PUBLIC,
        )
        if db_pass:
            kwargs["password"] = db_pass
        else:
            kwargs["enable_iam_auth"] = True
        return connector.connect(**kwargs)

    try:
        conn = getconn()
    except Exception as e:
        print(f"ERROR: Could not connect to Cloud SQL: {e}")
        connector.close()
        sys.exit(1)

    # Fetch into DataFrame
    print("Fetching rows from postgres.images …")
    try:
        df = fetch_dataframe(conn)
    except Exception as e:
        print(f"ERROR: Query failed: {e}")
        conn.close()
        connector.close()
        sys.exit(1)
    finally:
        conn.close()

    connector.close()
    print(f"Found {len(df)} rows.")

    if df.empty:
        print("No rows to export. Exiting.")
        sys.exit(0)

    # Download images; get back a numpy array of local path strings
    print()
    local_paths = download_images(df, images_dir, gcs_client, args.skip_existing)

    # Attach local paths as a new column and write CSV
    df["local_image_path"] = local_paths

    print(f"\nWriting CSV to {csv_path} …")
    df.to_csv(csv_path, index=False)

    # Summary using numpy for quick stats
    n_total      = len(df)
    n_downloaded = int(np.count_nonzero(local_paths))
    n_failed     = int(np.sum(local_paths == ""))
    n_with_gps   = int(df["gps_flag"].eq(True).sum())
    n_processed  = int(df["processed_status"].eq(True).sum())
    total_elk    = int(df["elk_count"].dropna().astype(int).sum())

    print(f"\nDone.")
    print(f"  Rows exported      : {n_total}")
    print(f"  Images downloaded  : {n_downloaded}  →  {images_dir}/")
    print(f"  Failed / no URI    : {n_failed}")
    print(f"  With GPS           : {n_with_gps}")
    print(f"  Detection complete : {n_processed}")
    print(f"  Total elk counted  : {total_elk}")
    print(f"  CSV written        : {csv_path}")


if __name__ == "__main__":
    main()