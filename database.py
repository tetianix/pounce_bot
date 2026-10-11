import sqlite3
from datetime import datetime

def create_table():
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ads(
        id TEXT NOT NULL,
        source TEXT NOT NULL,
        name TEXT NOT NULL,
        price INTEGER,
        town TEXT,
        published_date TEXT,
        link TEXT NOT NULL,
        query TEXT,
        first_seen TEXT,
        photo TEXT,
        PRIMARY KEY (source, id))''')
    connection.commit()
    connection.close()

def create_watches_table():
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS watches(
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    user_id INTEGER NOT NULL,
    query TEXT, 
    max_price INTEGER, 
    min_price INTEGER, 
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    UNIQUE(user_id, query, max_price, min_price))''')
    connection.commit()
    connection.close()

def create_price_history_table():
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_history(
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    ad_id TEXT NOT NULL,
    ad_source TEXT NOT NULL,
    price INTEGER NOT NULL,
    changed_at TEXT,
    FOREIGN KEY (ad_source, ad_id) REFERENCES ads(source, id))''')
    connection.commit()
    connection.close()

def create_favorites_table():
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS favorites(
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    user_id INTEGER NOT NULL,
    ad_id TEXT NOT NULL,
    ad_source TEXT NOT NULL,
    saved_at TEXT,
    UNIQUE(user_id, ad_id, ad_source),
    FOREIGN KEY (ad_source, ad_id) REFERENCES ads(source, id))''')
    connection.commit()
    connection.close()

def add_missing_columns(cursor, table, columns):
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    for name, definition in columns:
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

def migrate_price_currency():
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    add_missing_columns(cursor, "ads", [
        ("currency", "TEXT"),
        ("price_converted", "INTEGER NOT NULL DEFAULT 0"),
        ("price_label", "TEXT"),
    ])
    add_missing_columns(cursor, "price_history", [("currency", "TEXT")])
    connection.commit()
    connection.close()

def save_price(ad_id, ad_source, price, currency):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
    INSERT INTO price_history (ad_id, ad_source, price, currency, changed_at)
    VALUES (?, ?, ?, ?, ?)
    """, (ad_id, ad_source, price, currency, datetime.now().isoformat()))
    connection.commit()
    connection.close()

def save_ad(ad, query):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                   INSERT INTO ads (id, source, name, price, currency, price_converted, price_label,
                                    town, published_date, link, query, first_seen, photo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, id) DO UPDATE SET
                        price = excluded.price,
                        currency = excluded.currency,
                        price_converted = excluded.price_converted,
                        price_label = excluded.price_label,
                        name = excluded.name,
                        photo = excluded.photo,
                        published_date = excluded.published_date
                   """,(ad['id'], ad['source'], ad['name'], ad['price'], ad['currency'], int(ad['price_converted']),
                        ad['price_label'], ad['town'], ad['published_date'], ad['link'], query,
                        datetime.now().isoformat(), ad['photo']))
    connection.commit()
    connection.close()

def save_watch(user_id, query, max_price, min_price):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    max_price = max_price if max_price is not None else 0
    min_price = min_price if min_price is not None else 0
    cursor.execute("""
                    INSERT OR IGNORE INTO watches (user_id, query, max_price, min_price, created_at) 
                    VALUES (?, ?, ?, ?, ?)
                    """, (user_id, query, max_price, min_price, datetime.now().isoformat()))
    connection.commit()
    connection.close()

def save_favorite(user_id, ad_id, ad_source):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                    INSERT OR IGNORE INTO favorites (user_id, ad_id, ad_source, saved_at) 
                    VALUES (?, ?, ?, ?)
                    """, (user_id, ad_id, ad_source, datetime.now().isoformat()))
    connection.commit()
    connection.close()

def get_active_watches():
    connection = sqlite3.connect('database.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("""
                    SELECT * FROM watches
                    WHERE is_active = 1
                    """)
    result = cursor.fetchall()
    connection.close()
    return result

def get_last_price(ad_id, ad_source, currency):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
    SELECT price 
    FROM price_history 
    WHERE ad_id = ? 
    AND ad_source = ?
    AND currency = ?
    ORDER BY id DESC LIMIT 1""",(ad_id, ad_source, currency))
    result = cursor.fetchone()
    connection.close()
    if result is None:
        return None
    return result[0]

def get_max_price(ad_id, ad_source, currency):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
    SELECT MAX(price) 
    FROM price_history 
    WHERE ad_id = ? AND ad_source = ? AND currency = ?
    """, (ad_id, ad_source, currency))
    result = cursor.fetchone()
    connection.close()
    return result[0]

def get_user_watches(user_id):
    connection = sqlite3.connect('database.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("""
                    SELECT * 
                    FROM watches 
                    WHERE user_id = ?
                    """, (user_id,))
    result = cursor.fetchall()
    connection.close()
    return result

def get_link(ad_id, source):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                   SELECT link
                   FROM ads
                   WHERE id = ? AND source = ?
                   """, (ad_id, source))
    result = cursor.fetchone()
    connection.close()
    if result is None:
        return None
    return result[0]

def get_favorites(user_id):
    connection = sqlite3.connect('database.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("""
                    SELECT ads.*
                    FROM favorites
                    JOIN ads ON favorites.ad_id = ads.id AND favorites.ad_source = ads.source
                    WHERE favorites.user_id = ?
                    """, (user_id,))
    result = cursor.fetchall()
    connection.close()
    return result

def is_favorite(user_id, ad_id, ad_source):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                    SELECT 1
                    FROM favorites
                    WHERE user_id = ? AND ad_id = ? AND ad_source = ?
                    """, (user_id, ad_id, ad_source))
    result = cursor.fetchone()
    connection.close()
    return result is not None

def get_watch(watch_id):
    connection = sqlite3.connect('database.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("""
                    SELECT *
                    FROM watches 
                    WHERE id = ?
                    """, (watch_id,))
    result = cursor.fetchone()
    connection.close()
    return result

def delete_watch(watch_id):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                    DELETE FROM watches 
                    WHERE id = ?
                    """, (watch_id,))
    connection.commit()
    connection.close()

def delete_favorite(user_id, ad_id, ad_source):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                    DELETE FROM favorites 
                    WHERE user_id = ? AND ad_id = ? AND ad_source = ?
                    """, (user_id, ad_id, ad_source))
    connection.commit()
    connection.close()
                        
def toggle_watch(watch_id):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                    UPDATE watches 
                    SET is_active = 1 - is_active
                    WHERE id = ?
                    """, (watch_id,))
    connection.commit()
    connection.close()

def ad_exists(ad_id, source):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("""
                    SELECT name 
                    FROM ads 
                    WHERE id = ? AND source = ?
                    """, (ad_id, source))
    result = cursor.fetchone()
    connection.close()
    return result is not None