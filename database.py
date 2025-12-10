# database.py
import os
from sqlmodel import SQLModel, create_engine, Session

# 1. The Connection String
# Get the database URL from the environment variable.
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"Connecting to database at: {DATABASE_URL}")

# 2. Create the Engine
engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    # This sends SQL commands to Postgres to create the table
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session