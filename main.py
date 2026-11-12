import db
from models import Base

Base.metadata.create_all(db.engine)
