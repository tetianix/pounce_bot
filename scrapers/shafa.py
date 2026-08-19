import requests

url = "https://shafa.ua/uk/home?search_text=помада"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}
r = requests.get(url, headers=headers)
print(r.status_code, len(r.text))
with open("shafa.html", "w", encoding="utf-8") as f:
    f.write(r.text)