from logging.config import fileConfig
import sys
from pathlib import Path
import json

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Customizations for RFSentinel ---

# 1. Add project root to sys.path to find our modules
project_dir = str(Path(__file__).resolve().parents[1])
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from core.models import Base
from core.config import AppConfig

# 2. Set the target metadata for autogeneration
target_metadata = Base.metadata

# 3. Load the database URL from the application's config.json
def get_db_url():
    """Reads the database path from config.json and returns the full URL."""
    config_path = Path(project_dir) / "config.json"
    example_path = Path(project_dir) / "config.json.example"

    if not config_path.exists():
        print(f"INFO: '{config_path}' not found. Creating from '{example_path}'.")
        import shutil
        if not example_path.exists():
            raise FileNotFoundError(f"'{example_path}' is missing. Cannot create config for Alembic.")
        shutil.copy(example_path, config_path)

    with open(config_path, "r") as f:
        config_data = json.load(f)

    app_config = AppConfig.parse_obj(config_data)
    # The path in config might be relative, so resolve it against the project dir
    db_path = Path(project_dir) / app_config.data_paths.db
    return f"sqlite:///{db_path.resolve()}"

# 4. Set the sqlalchemy.url in the config object
# This will be used by run_migrations_offline and engine_from_config
db_url = get_db_url()
config.set_main_option("sqlalchemy.url", db_url)

# --- End of Customizations ---

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()