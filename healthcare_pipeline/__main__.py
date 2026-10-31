"""Local CLI. Databricks should call pipeline.run with its existing spark session."""

import argparse
import os
from pathlib import Path
import sys

from .sources import DEFAULT_ROOT, RELEASE, download_sources, verify_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["download", "verify", "run"])
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_ROOT / "raw" / RELEASE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT / "runs")
    args = parser.parse_args()
    if args.command == "download":
        print(download_sources(args.raw_dir))
    elif args.command == "verify":
        print(verify_sources(args.raw_dir))
    else:
        verify_sources(args.raw_dir)
        os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
        os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
        from pyspark.sql import SparkSession
        from .pipeline import run
        spark = (SparkSession.builder.master("local[2]").appName("healthcare-operations-phase2")
                 .config("spark.sql.shuffle.partitions", "4")
                 .config("spark.ui.enabled", "false").getOrCreate())
        spark.sparkContext.setLogLevel("ERROR")
        try:
            run(spark, args.raw_dir, args.output_root)
        finally:
            spark.stop()


if __name__ == "__main__":
    main()
