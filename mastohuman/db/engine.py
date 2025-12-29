from sqlmodel import Session, SQLModel, create_engine

from mastohuman.config.settings import get_db_url, settings

engine = create_engine(get_db_url(), echo=settings.db_echo)


def init_db():
    """Create tables if they don't exist."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Dependency for getting a session."""
    with Session(engine) as session:
        yield session
