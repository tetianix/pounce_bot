from typing import Literal

from pydantic import BaseModel, Field

from core import SOURCES
from scrapers.olx import CITIES, SORTS, STATES

SourceKey = Literal[tuple(SOURCES)]
SortKey = Literal[tuple(SORTS)]
CityKey = Literal[tuple(CITIES)]
StateKey = Literal[tuple(STATES)]
PeriodKey = Literal["any", "1d", "3d", "7d"]


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class Ad(BaseModel):
    id: str = Field(description="Ідентифікатор оголошення на сайті", examples=["909426485"])
    source: str = Field(description="Джерело оголошення", examples=["olx"])
    name: str = Field(description="Назва оголошення")
    price: int | None = Field(description="Ціна без копійок; null, якщо ціни немає (обмін, безкоштовно)")
    currency: Literal["UAH", "USD", "EUR"] = Field(description="Валюта ціни")
    price_converted: bool = Field(description="true, якщо OLX перерахував валютну ціну в гривні (є копійки)")
    price_label: str | None = Field(description="Позначка біля ціни: «Договірна», «Безкоштовно», «Обмін»")
    town: str = Field(description="Місто")
    published_date: str = Field(description="Дата публікації як на OLX, час за Києвом")
    photo: str | None = Field(description="Посилання на головне фото")
    promoted: bool = Field(description="true, якщо оголошення рекламне (піднятте в топ)")
    link: str = Field(description="Посилання на оголошення")


class SearchResponse(BaseModel):
    count: int = Field(description="Скільки оголошень у відповіді")
    cached: bool = Field(description="true, якщо відповідь узята з короткого кешу, а не з OLX")
    ads: list[Ad]


class OriginalPrice(BaseModel):
    price: int | None
    currency: Literal["UAH", "USD", "EUR"]
    converted: bool
    label: str | None


class AdDetails(BaseModel):
    description: str | None = Field(description="Опис оголошення; null, якщо не вдалося отримати")
    photos: list[str] = Field(description="Посилання на всі фото")
    price: OriginalPrice | None = Field(description="Ціна зі сторінки оголошення: тут є оригінальна валюта")


class PricePoint(BaseModel):
    price: int
    currency: Literal["UAH", "USD", "EUR"] | None = Field(
        description="Валюта запису; null у старих записів, де ціни були зіпсовані")
    changed_at: str | None = Field(description="Коли бот записав цю ціну (ISO)")


class PriceHistory(BaseModel):
    source: str
    ad_id: str
    points: list[PricePoint] = Field(description="Від найстаршої ціни до найновішої")


class ErrorBody(BaseModel):
    detail: str
