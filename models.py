from sqlalchemy import BigInteger, ForeignKeyConstraint, Integer, MetaData, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Ad(Base):
    __tablename__ = "ads"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    price: Mapped[int | None] = mapped_column(Integer)
    town: Mapped[str | None] = mapped_column(Text)
    published_date: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str] = mapped_column(Text)
    query: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[str | None] = mapped_column(Text)
    photo: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(Text)
    price_converted: Mapped[int] = mapped_column(Integer, server_default="0")
    price_label: Mapped[str | None] = mapped_column(Text)


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (
        UniqueConstraint("user_id", "query", "max_price", "min_price", "city", "state", "exact"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    query: Mapped[str | None] = mapped_column(Text)
    max_price: Mapped[int | None] = mapped_column(Integer)
    min_price: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text, server_default="")
    state: Mapped[str] = mapped_column(Text, server_default="")
    exact: Mapped[int] = mapped_column(Integer, server_default="0")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        ForeignKeyConstraint(["ad_source", "ad_id"], ["ads.source", "ads.id"]),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ad_id: Mapped[str] = mapped_column(Text)
    ad_source: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(Text)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "ad_id", "ad_source"),
        ForeignKeyConstraint(["ad_source", "ad_id"], ["ads.source", "ads.id"]),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    ad_id: Mapped[str] = mapped_column(Text)
    ad_source: Mapped[str] = mapped_column(Text)
    saved_at: Mapped[str | None] = mapped_column(Text)
