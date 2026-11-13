import httpx

DEFAULT_API_URL = "http://127.0.0.1:8000"
API_TIMEOUT = httpx.Timeout(70, connect=5)
EMPTY_DETAILS = {"description": None, "photos": [], "price": None}


class ApiError(Exception):
    pass


class ApiUnavailable(ApiError):
    pass


class OlxUnavailable(ApiError):
    pass


def make_client(api_url=DEFAULT_API_URL):
    return httpx.AsyncClient(base_url=api_url, timeout=API_TIMEOUT)


class ApiClient:
    def __init__(self, client):
        self.client = client

    async def get(self, path, params=None):
        try:
            response = await self.client.get(path, params=params)
        except httpx.TimeoutException as e:
            raise ApiUnavailable("API не відповів вчасно") from e
        except httpx.HTTPError as e:
            raise ApiUnavailable("API недоступний") from e
        if response.status_code == 502:
            raise OlxUnavailable(error_detail(response))
        if response.status_code >= 400 and response.status_code != 404:
            raise ApiUnavailable(f"API: HTTP {response.status_code}")
        return response

    async def search(self, query, min_price=None, max_price=None, sort="new", period="any", city=None, state=None,
                     exact=False, page=1):
        params = {"q": query, "sort": sort, "period": period, "exact": exact, "page": page}
        optional = {"min_price": min_price, "max_price": max_price, "city": city, "state": state}
        params.update({name: value for name, value in optional.items() if value is not None})
        response = await self.get("/search", params)
        if response.status_code != 200:
            raise ApiUnavailable(f"API: HTTP {response.status_code}")
        return response.json()["ads"]

    async def details(self, source, ad_id):
        response = await self.get(f"/ads/{source}/{ad_id}")
        if response.status_code == 404:
            return None
        return response.json()


def error_detail(response):
    try:
        return response.json()["detail"]
    except (ValueError, KeyError, TypeError):
        return "OLX не відповів"
