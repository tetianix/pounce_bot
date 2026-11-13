import asyncio
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from api.schemas import (AdDetails, CityKey, ErrorBody, Health, PeriodKey, PriceHistory, PricePoint, SearchResponse,
                         SortKey, SourceKey, StateKey)
from api.service import OlxService, get_olx_service
from database import ad_exists, get_link, get_price_history
from filters import filter_by_price, filter_exact
from scrapers.olx import OlxError, scrape_details

app = FastAPI(
    title="Pounce API",
    description="Сервіс, який ходить на OLX замість бота: пошук, деталі оголошень, історія цін.",
    version="1.0.0",
)

NOT_FOUND_RESPONSE = {404: {"model": ErrorBody, "description": "Бот ще не бачив цього оголошення"}}
OLX_ERROR_RESPONSE = {502: {"model": ErrorBody, "description": "OLX не відповів: таймаут, мережа або HTTP-помилка"}}


@app.exception_handler(OlxError)
async def olx_error_handler(request, error):
    return JSONResponse(status_code=502, content={"detail": f"OLX не відповів: {error}"})


@app.get("/health", response_model=Health, summary="Чи живий сервіс", tags=["service"])
async def health():
    return Health()


@app.get("/search", response_model=SearchResponse, responses=OLX_ERROR_RESPONSE, tags=["ads"],
         summary="Пошук оголошень")
async def search_ads(
    service: Annotated[OlxService, Depends(get_olx_service)],
    q: Annotated[str, Query(min_length=1, max_length=200, description="Що шукати")],
    min_price: Annotated[int | None, Query(ge=1, description="Мінімальна ціна, грн")] = None,
    max_price: Annotated[int | None, Query(ge=1, description="Максимальна ціна, грн")] = None,
    sort: Annotated[SortKey, Query(description="Сортування")] = "new",
    period: Annotated[PeriodKey, Query(description="Лише за період: 1d, 3d, 7d; any — без обмеження")] = "any",
    city: Annotated[CityKey | None, Query(description="Місто; без нього — вся Україна")] = None,
    state: Annotated[StateKey | None, Query(description="Стан товару; без нього — будь-який")] = None,
    exact: Annotated[bool, Query(description="Лише назви з усіма словами запиту")] = False,
    page: Annotated[int, Query(ge=1, le=50, description="Сторінка видачі; ігнорується, якщо задано period")] = 1,
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price більша за max_price")
    ads, cached = await service.find_ads(q, min_price, max_price, sort, period, city, state, page)
    if min_price is not None or max_price is not None:
        ads = filter_by_price(ads, max_price=max_price, min_price=min_price)
    if exact:
        ads = filter_exact(ads, q)
    ads.sort(key=lambda ad: ad["promoted"])
    return SearchResponse(count=len(ads), cached=cached, ads=ads)


@app.get("/ads/{source}/{ad_id}", response_model=AdDetails, responses=NOT_FOUND_RESPONSE, tags=["ads"],
         summary="Деталі оголошення: опис, фото, оригінальна ціна")
async def ad_details(
    service: Annotated[OlxService, Depends(get_olx_service)],
    source: Annotated[SourceKey, Path(description="Джерело оголошення")],
    ad_id: Annotated[str, Path(description="Ідентифікатор оголошення з видачі")],
):
    link = await asyncio.to_thread(get_link, ad_id, source)
    if link is None:
        raise HTTPException(status_code=404, detail="Оголошення не знайдено")
    return await service.run_in_slot(scrape_details, link)


@app.get("/ads/{source}/{ad_id}/price-history", response_model=PriceHistory, responses=NOT_FOUND_RESPONSE,
         tags=["ads"], summary="Історія цін оголошення з бази")
def ad_price_history(
    source: Annotated[SourceKey, Path(description="Джерело оголошення")],
    ad_id: Annotated[str, Path(description="Ідентифікатор оголошення з видачі")],
):
    if not ad_exists(ad_id, source):
        raise HTTPException(status_code=404, detail="Оголошення не знайдено")
    points = [PricePoint(**row) for row in get_price_history(ad_id, source)]
    return PriceHistory(source=source, ad_id=ad_id, points=points)
