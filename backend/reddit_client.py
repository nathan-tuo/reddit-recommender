import requests

HEADERS = {"User-Agent": "mood-recommender/0.1"}

def fetch_posts(subreddit_name="all", limit=100, sort="hot"):
    url = f"https://www.reddit.com/r/{subreddit_name}/{sort}.json?limit={limit}"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()

    posts = []
    for child in res.json()["data"]["children"]:
        p = child["data"]
        posts.append({
            "id": p["id"],
            "title": p["title"],
            "body": p.get("selftext", "")[:500],
            "url": f"https://reddit.com{p['permalink']}",
            "subreddit": p["subreddit"],
            "score": p["score"],
            "num_comments": p["num_comments"],
            "thumbnail": p["thumbnail"] if p["thumbnail"].startswith("http") else None,
        })

    return posts