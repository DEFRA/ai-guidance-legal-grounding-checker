from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_engine(database_url: str = "sqlite:///./law-proposition-extractor.db") -> Engine:
    return create_engine(database_url, future=True)
