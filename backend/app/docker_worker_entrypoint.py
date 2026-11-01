import os
import sys
from pathlib import Path

from dotenv import dotenv_values

WORKER_ENV_FILE = Path("/run/secrets/orbit-env")


def main() -> int:
    if not WORKER_ENV_FILE.is_file():
        print(
            "Worker startup failed: runtime environment file is unavailable.",
            file=sys.stderr,
        )
        return 1

    values = dotenv_values(WORKER_ENV_FILE, interpolate=False)
    database_url = values.get("DATABASE_URL")
    if not database_url:
        print("Worker startup failed: DATABASE_URL is missing.", file=sys.stderr)
        return 1

    environment = {
        "DATABASE_URL": database_url,
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONUNBUFFERED": "1",
        "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", ""),
    }
    os.execve(sys.executable, [sys.executable, *sys.argv[1:]], environment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
