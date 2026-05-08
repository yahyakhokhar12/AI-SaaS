import os
from sqlalchemy import text
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_startup_migrations() -> None:
    with engine.begin() as connection:
        dialect = connection.dialect.name
        if dialect == "sqlite":
            existing_tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "chat_messages" in existing_tables:
                connection.exec_driver_sql("DROP TABLE chat_messages")
            user_columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()
            }
            if "is_active" not in user_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                )
        elif dialect == "postgresql":
            connection.execute(text("DROP TABLE IF EXISTS chat_messages"))
            connection.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE")
            )
