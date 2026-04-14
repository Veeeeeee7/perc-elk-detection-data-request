# export_data.py

Exports all image records from the Cloud SQL `postgres.images` table, downloads each corresponding photo from Google Cloud Storage, and writes a structured CSV to disk.

Rows are loaded into a **pandas DataFrame** with proper nullable dtypes (via `pandas` and `numpy`), ensuring that integer columns like `elk_count` and float columns like `latitude` handle `NULL` database values correctly without type corruption.

---

## Requirements

- Python 3.10 or higher
- A GCP service account key JSON file with the following roles:
    - `Cloud SQL Client` (for database access)
    - `Storage Object Viewer` (for GCS downloads)

---

## Installation

It is recommended to use a virtual environment to avoid dependency conflicts.

**Create and activate a virtual environment:**

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

**Install dependencies:**

```bash
pip install -r requirements.txt
```

### Dependencies

| Package                              | Version | Purpose                                                   |
| ------------------------------------ | ------- | --------------------------------------------------------- |
| `pg8000`                             | ≥1.30.0 | Pure-Python PostgreSQL driver used by the connector.      |
| `google-cloud-storage`               | ≥2.0.0  | Downloading images from GCS buckets.                      |
| `cloud-sql-python-connector[pg8000]` | ≥1.0.0  | Secure Cloud SQL connections via the GCP connector.       |
| `google-auth`                        | ≥2.0.0  | Service account credential handling.                      |
| `pandas`                             | ≥2.0.0  | DataFrame construction, dtype management, CSV export.     |
| `numpy`                              | ≥1.26.0 | Fast array ops for local path tracking and summary stats. |

---

## Configuration

The script needs four database connection values. These can be supplied as environment variables or as CLI flags. Environment variable names match those used by the Java backend's `SecretConfig`.

| Environment Variable | CLI Flag        | Description                                                          |
| -------------------- | --------------- | -------------------------------------------------------------------- |
| `CLOUD_SQL_INSTANCE` | `--instance`    | Cloud SQL connection name, e.g. `my-project:us-central1:my-instance` |
| `CLOUD_SQL_DB_NAME`  | `--db-name`     | Database name, e.g. `postgres`                                       |
| `DB_USER`            | `--db-user`     | Database user, e.g. `postgres`                                       |
| `DB_PASSWORD`        | `--db-password` | Database password. If omitted, IAM database auth is attempted.       |

**Setting environment variables (recommended for repeated use):**

```bash
export CLOUD_SQL_INSTANCE="my-project:us-central1:my-instance"
export CLOUD_SQL_DB_NAME="postgres"
export DB_USER="myuser"
export DB_PASSWORD="mysecretpassword"
```

---

## Usage

### Basic

```bash
python export_data.py \
  --key path/to/service-account-key.json \
  --output-folder data/
```

### All options via CLI flags

```bash
python export_data.py \
  --key path/to/service-account-key.json \
  --output-folder data/ \
  --instance my-project:us-central1:my-instance \
  --db-name postgres \
  --db-user myuser \
  --db-password mysecretpassword
```

### Skip already-downloaded images (useful for resuming)

```bash
python export_data.py \
  --key path/to/service-account-key.json \
  --output-folder data/ \
  --skip-existing
```

### All CLI flags

| Flag              | Required | Description                                                  |
| ----------------- | -------- | ------------------------------------------------------------ |
| `--key`           | Yes      | Path to GCP service account key JSON file.                   |
| `--output-folder` | Yes      | Root directory for all output (created if it doesn't exist). |
| `--instance`      | No       | Cloud SQL instance connection name. Overrides env var.       |
| `--db-name`       | No       | Database name. Overrides env var.                            |
| `--db-user`       | No       | Database user. Overrides env var.                            |
| `--db-password`   | No       | Database password. Overrides env var.                        |
| `--skip-existing` | No       | Skip GCS download if the image file already exists locally.  |

---

## Output

Running the script produces the following structure inside `--output-folder`:

```
data/
├── images/
│   ├── a3f2b9c8d1e5f7b0...jpeg
│   ├── b7e1c4f0a2d38c91...jpeg
│   └── ...
└── data.csv
```

### Images (`data/images/`)

Each image is saved as:

```
{img_hash}{extension}
```

Where `img_hash` is the SHA-256 hash stored in the database and the extension (`.jpg`, `.jpeg`, `.png`, `.heic`) is inferred from the GCS object name. Using the hash as the filename guarantees uniqueness and makes images easy to cross-reference with the CSV.

### CSV (`data/data.csv`)

The CSV is written directly from the pandas DataFrame using `df.to_csv()`. It contains one row per database record. All columns from the `postgres.images` table are included, plus one additional column (`local_image_path`) pointing to the downloaded file on disk.

#### DataFrame dtypes

The DataFrame applies explicit pandas nullable dtypes before writing, so that SQL `NULL` values survive the round-trip correctly:

| Pandas dtype | Applied to columns                                                      |
| ------------ | ----------------------------------------------------------------------- |
| `Int64`      | `id`, `filesize_bytes`, `width`, `height`, `elk_count`                  |
| `float64`    | `latitude`, `longitude`, `altitude`, `temperature_c`, `humidity`        |
| `datetime64` | `datetime_taken`, `datetime_uploaded` (UTC-aware)                       |
| `boolean`    | `gps_flag`, `processed_status`                                          |
| `object`     | `img_hash`, `cloud_uri`, `filename`, `weather_desc`, `local_image_path` |

Using pandas `Int64` (capital I) instead of numpy `int64` means a missing `elk_count` is written as an empty cell in the CSV rather than being coerced to `0` or `NaN` in a float column.

#### Columns

| Column              | CSV dtype | Description                                                                                                                       |
| ------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `id`                | integer   | Auto-incremented primary key.                                                                                                     |
| `img_hash`          | string    | SHA-256 hash of the image file. Used as the image filename on disk.                                                               |
| `cloud_uri`         | string    | Full GCS URI, e.g. `gs://my-bucket/a3f2b9c8....jpeg`.                                                                             |
| `filename`          | string    | Original filename as uploaded by the landowner.                                                                                   |
| `filesize_bytes`    | integer   | File size in bytes at time of upload.                                                                                             |
| `width`             | integer   | Image width in pixels.                                                                                                            |
| `height`            | integer   | Image height in pixels.                                                                                                           |
| `gps_flag`          | boolean   | `True` if GPS coordinates were extracted from EXIF metadata.                                                                      |
| `latitude`          | float     | GPS latitude in decimal degrees. Empty if `gps_flag` is False.                                                                    |
| `longitude`         | float     | GPS longitude in decimal degrees. Empty if `gps_flag` is False.                                                                   |
| `altitude`          | float     | GPS altitude in meters. Empty if not present in EXIF.                                                                             |
| `datetime_taken`    | timestamp | Date and time the photo was taken, from EXIF metadata (UTC).                                                                      |
| `datetime_uploaded` | timestamp | Date and time the record was inserted into the database (UTC).                                                                    |
| `temperature_c`     | float     | Ambient temperature in Celsius at the photo location and time (Open-Meteo).                                                       |
| `humidity`          | float     | Relative humidity percentage at the photo location and time.                                                                      |
| `weather_desc`      | string    | Human-readable weather description, e.g. `Clear sky`, `Rain`, `Snow`.                                                             |
| `elk_count`         | integer   | Number of elk detected by AnimalDetect. Empty if not yet processed.                                                               |
| `processed_status`  | boolean   | `True` if the image has been run through the animal detection model.                                                              |
| `local_image_path`  | string    | Path to the downloaded image, e.g. `data/images/a3f2b9....jpeg`. Empty string if the download failed or no GCS URI was available. |

#### Example rows

```
id,img_hash,cloud_uri,filename,filesize_bytes,width,height,gps_flag,latitude,longitude,altitude,datetime_taken,datetime_uploaded,temperature_c,humidity,weather_desc,elk_count,processed_status,local_image_path
1,a3f2b9c8d1e5f7b0,gs://my-bucket/a3f2b9c8d1e5f7b0.jpeg,IMG_3141.jpg,2457600,4032,3024,True,44.12345,-110.56789,2134.5,2024-11-03 14:22:00+00:00,2024-11-03 18:05:12+00:00,3.2,61.0,Partly cloudy,2,True,data/images/a3f2b9c8d1e5f7b0.jpeg
2,b7e1c4f0a2d38c91,gs://my-bucket/b7e1c4f0a2d38c91.jpeg,trail_cam_nov4.jpg,1843200,3024,4032,False,,,,,2024-11-04 09:10:00+00:00,2024-11-04 11:30:44+00:00,,,,,False,data/images/b7e1c4f0a2d38c91.jpeg
```

---

## End-of-run summary

After the CSV is written, the script prints a summary computed from the DataFrame and numpy:

```
Done.
  Rows exported      : 142
  Images downloaded  : 139  →  data/images/
  Failed / no URI    :   3
  With GPS           : 118
  Detection complete : 130
  Total elk counted  :  47
  CSV written        : data/data.csv
```

---

## Notes

- **Resuming interrupted runs:** Use `--skip-existing` to avoid re-downloading images already saved locally. The CSV is always fully regenerated from the database regardless of this flag.
- **Timestamps are UTC-aware.** Both `datetime_taken` and `datetime_uploaded` are parsed with `utc=True` by pandas and written to the CSV in ISO 8601 format including the `+00:00` offset.
