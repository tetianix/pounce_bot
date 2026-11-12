import db
from models import Base


def use_memory_database():
    engine = db.use_engine(db.make_engine("sqlite://"))
    Base.metadata.create_all(engine)
    return engine


def drop_memory_database():
    db.engine.dispose()
