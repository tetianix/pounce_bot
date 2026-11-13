from fastapi import FastAPI

from api.schemas import Health

app = FastAPI(
    title="Pounce API",
    description="Сервіс, який ходить на OLX замість бота: пошук, деталі оголошень, історія цін.",
    version="1.0.0",
)


@app.get("/health", response_model=Health, summary="Чи живий сервіс", tags=["service"])
async def health():
    return Health()
