"""Download and verify the configured hourly archives."""
import _bootstrap  # noqa: F401
from gharchive_a.cli import main_stage

if __name__ == "__main__":
    main_stage("download")
