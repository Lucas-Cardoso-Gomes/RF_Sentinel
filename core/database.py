from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# This module sets up the database connection and session management.

# The database URL is constructed from the application config.
# We will pass the db_path from the config when initializing.
# Example: SQLALCHEMY_DATABASE_URL = "sqlite:///./data/rfsentinel.db"

# create_engine is the entry point to the database.
# The `connect_args` is needed only for SQLite to allow multithreaded access.
engine = None

# SessionLocal is the class that will be used to create DB sessions.
SessionLocal = None

# Base is the class from which all our ORM models will inherit.
Base = declarative_base()

def initialize_database(db_path: str):
    """
    Initializes the database engine and session maker.
    This function must be called once at application startup.
    """
    global engine, SessionLocal

    database_url = f"sqlite:///{db_path}"

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} # Needed for SQLite with FastAPI
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # In a real application, you would use Alembic or a similar tool
    # to create and migrate the database schema. For now, we can create
    # all tables from the Base metadata. This is good for development.
    Base.metadata.create_all(bind=engine)

def get_db():
    """
    FastAPI dependency to get a DB session for a request.
    It ensures the database connection is always closed after the request.
    """
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized. Call initialize_database() first.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()