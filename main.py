from database import (create_table, create_watches_table,
                      create_price_history_table, create_favorites_table, migrate_price_currency)

create_table()
create_watches_table()
create_favorites_table()
create_price_history_table()
migrate_price_currency()
