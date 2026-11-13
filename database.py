from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

import db
from models import Ad, Favorite, PriceHistory, Watch


def insert_for(session, model):
    if session.get_bind().dialect.name == "postgresql":
        return postgresql_insert(model)
    return sqlite_insert(model)


def save_price(ad_id, ad_source, price, currency):
    with db.Session.begin() as session:
        session.add(PriceHistory(ad_id=ad_id, ad_source=ad_source, price=price, currency=currency,
                                 changed_at=datetime.now().isoformat()))


def save_ad(ad, query):
    with db.Session.begin() as session:
        statement = insert_for(session, Ad).values(
            id=ad['id'], source=ad['source'], name=ad['name'], price=ad['price'], currency=ad['currency'],
            price_converted=int(ad['price_converted']), price_label=ad['price_label'], town=ad['town'],
            published_date=ad['published_date'], link=ad['link'], query=query,
            first_seen=datetime.now().isoformat(), photo=ad['photo'])
        session.execute(statement.on_conflict_do_update(
            index_elements=[Ad.source, Ad.id],
            set_={
                'price': statement.excluded.price,
                'currency': statement.excluded.currency,
                'price_converted': statement.excluded.price_converted,
                'price_label': statement.excluded.price_label,
                'name': statement.excluded.name,
                'photo': statement.excluded.photo,
                'published_date': statement.excluded.published_date,
            }))


def watch_key(max_price, min_price, city, state, exact):
    return (max_price if max_price is not None else 0, min_price if min_price is not None else 0,
            city or "", state or "", int(bool(exact)))


def save_watch(user_id, query, max_price, min_price, city=None, state=None, exact=False):
    max_price, min_price, city, state, exact = watch_key(max_price, min_price, city, state, exact)
    with db.Session.begin() as session:
        statement = insert_for(session, Watch).values(
            user_id=user_id, query=query, max_price=max_price, min_price=min_price, city=city, state=state,
            exact=exact, created_at=datetime.now().isoformat())
        session.execute(statement.on_conflict_do_nothing())


def save_favorite(user_id, ad_id, ad_source):
    with db.Session.begin() as session:
        statement = insert_for(session, Favorite).values(
            user_id=user_id, ad_id=ad_id, ad_source=ad_source, saved_at=datetime.now().isoformat())
        session.execute(statement.on_conflict_do_nothing())


def get_active_watches():
    with db.Session() as session:
        return session.execute(
            select(Watch.__table__).where(Watch.is_active == 1).order_by(Watch.id)).mappings().all()


def get_last_price(ad_id, ad_source, currency):
    if currency is None:
        return None
    with db.Session() as session:
        return session.execute(
            select(PriceHistory.price)
            .where(PriceHistory.ad_id == ad_id, PriceHistory.ad_source == ad_source,
                   PriceHistory.currency == currency)
            .order_by(PriceHistory.id.desc()).limit(1)).scalar_one_or_none()


def get_max_price(ad_id, ad_source, currency):
    if currency is None:
        return None
    with db.Session() as session:
        return session.execute(
            select(func.max(PriceHistory.price))
            .where(PriceHistory.ad_id == ad_id, PriceHistory.ad_source == ad_source,
                   PriceHistory.currency == currency)).scalar_one()


def get_price_history(ad_id, ad_source):
    with db.Session() as session:
        return session.execute(
            select(PriceHistory.price, PriceHistory.currency, PriceHistory.changed_at)
            .where(PriceHistory.ad_id == ad_id, PriceHistory.ad_source == ad_source)
            .order_by(PriceHistory.id)).mappings().all()


def get_user_watches(user_id):
    with db.Session() as session:
        return session.execute(
            select(Watch.__table__).where(Watch.user_id == user_id).order_by(Watch.id.desc())).mappings().all()


def get_link(ad_id, source):
    with db.Session() as session:
        return session.execute(select(Ad.link).where(Ad.id == ad_id, Ad.source == source)).scalar_one_or_none()


def get_favorites(user_id):
    with db.Session() as session:
        return session.execute(
            select(Ad.__table__)
            .join(Favorite, (Favorite.ad_id == Ad.id) & (Favorite.ad_source == Ad.source))
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.id)).mappings().all()


def is_favorite(user_id, ad_id, ad_source):
    with db.Session() as session:
        return session.execute(
            select(Favorite.id)
            .where(Favorite.user_id == user_id, Favorite.ad_id == ad_id, Favorite.ad_source == ad_source)
            .limit(1)).first() is not None


def get_watch(watch_id):
    with db.Session() as session:
        return session.execute(select(Watch.__table__).where(Watch.id == watch_id)).mappings().first()


def delete_watch(watch_id):
    with db.Session.begin() as session:
        session.execute(delete(Watch).where(Watch.id == watch_id))


def delete_user_watch(user_id, query, max_price, min_price, city=None, state=None, exact=False):
    max_price, min_price, city, state, exact = watch_key(max_price, min_price, city, state, exact)
    with db.Session.begin() as session:
        session.execute(delete(Watch).where(
            Watch.user_id == user_id, Watch.query == query, Watch.max_price == max_price,
            Watch.min_price == min_price, Watch.city == city, Watch.state == state, Watch.exact == exact))


def delete_favorite(user_id, ad_id, ad_source):
    with db.Session.begin() as session:
        session.execute(delete(Favorite).where(
            Favorite.user_id == user_id, Favorite.ad_id == ad_id, Favorite.ad_source == ad_source))


def toggle_watch(watch_id):
    with db.Session.begin() as session:
        session.execute(update(Watch).where(Watch.id == watch_id).values(is_active=1 - Watch.is_active))


def ad_exists(ad_id, source):
    with db.Session() as session:
        return session.execute(select(Ad.id).where(Ad.id == ad_id, Ad.source == source).limit(1)).first() is not None
