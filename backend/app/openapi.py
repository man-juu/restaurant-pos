"""Write the OpenAPI schemas the frontend client is generated from (docs/04 section 8).

    python -m app.openapi ../frontend/src/lib/api

CI regenerates them and fails if the committed copies differ, so the frontend types can
never drift from the API.
"""

import json
import sys
from pathlib import Path

from app.admin.main import create_admin_app
from app.core.config import Settings
from app.main import create_app


def main(out_dir: str) -> None:
    settings = Settings.model_validate(
        {"environment": "test", "admin_database_url": "postgresql+asyncpg://x:y@localhost/z"}
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, api in (("tenant", create_app(settings)), ("admin", create_admin_app(settings))):
        schema = json.dumps(api.openapi(), indent=2, sort_keys=True) + "\n"
        (out / f"{name}.openapi.json").write_text(schema)


if __name__ == "__main__":
    main(sys.argv[1])
