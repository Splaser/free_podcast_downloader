import requests

url = "https://file.cdn.firstory.me/Avatar/ckyjkecle98z10983mzd7venu/1642477004002.jpg"

headers_list = [
    {
        "name": "plain",
        "headers": {},
    },
    {
        "name": "browser image",
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
                "Gecko/20100101 Firefox/150.0"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
        },
    },
    {
        "name": "firstory referer",
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
                "Gecko/20100101 Firefox/150.0"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Referer": "https://open.firstory.me/",
        },
    },
    {
        "name": "feed referer",
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) "
                "Gecko/20100101 Firefox/150.0"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Referer": "https://feed.firstory.me/",
        },
    },
]

for item in headers_list:
    print("===", item["name"], "===")
    try:
        resp = requests.get(
            url,
            headers=item["headers"],
            timeout=20,
            allow_redirects=True,
        )
        print("status:", resp.status_code)
        print("final_url:", resp.url)
        print("content-type:", resp.headers.get("content-type"))
        print("content-length:", resp.headers.get("content-length"))
        print("preview:", resp.content[:20])
        print(resp.text[:500])
    except Exception as e:
        print("error:", e)
    print()