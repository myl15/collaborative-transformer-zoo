# database.py
from sqlmodel import SQLModel, create_engine, Session
# from models import Visualization  # Not strictly needed here, but good for circular import checks

# 1. The Connection String
# Syntax: postgresql://<user>:<password>@<host>:<port>/<db_name>
# These MUST match your docker-compose.yml file exactly.
DATABASE_URL = "postgresql://user:password@localhost:5432/transformer_zoo"

# 2. Create the Engine
# Note: We REMOVED 'connect_args={"check_same_thread": False}' 
# because that is only for SQLite. Postgres handles threads natively.
engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    # This sends SQL commands to Postgres to create the table
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session