from filters import filter_by_price
from database import create_table, save_ad, ad_exists, get_link, create_watches_table
from core import search
from scrapers.olx import scrape
from database import get_ads_by_query
from core import search

create_table()
create_watches_table()
from database import get_active_watches
watches = get_active_watches()
