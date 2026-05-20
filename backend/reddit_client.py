import time
import requests

HEADERS = {"User-Agent": "mood-recommender/0.2"}

# Simple in-memory TTL cache for post listings.
# Key: (subreddit, sort, limit) -> (timestamp, posts)
_post_cache = {}
POST_CACHE_TTL = 300  # 5 minutes

# Cache for comments per post — comments rarely change meaningfully within a session.
# Key: post_id -> (timestamp, comments)
_comment_cache = {}
COMMENT_CACHE_TTL = 600  # 10 minutes


def fetch_posts(subreddit_name="all", limit=100, sort="hot"):
    """Fetch a subreddit's post listing, with a short TTL cache."""
    cache_key = (subreddit_name, sort, limit)
    now = time.time()

    cached = _post_cache.get(cache_key)
    if cached and now - cached[0] < POST_CACHE_TTL:
        return cached[1]

    url = f"https://www.reddit.com/r/{subreddit_name}/{sort}.json?limit={limit}"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()

    posts = []
    for child in res.json()["data"]["children"]:
        p = child["data"]
        posts.append({
            "id": p["id"],
            "title": p["title"],
            "body": p.get("selftext", "")[:500],
            "url": f"https://reddit.com{p['permalink']}",
            "permalink": p["permalink"],  # needed for comment fetching
            "subreddit": p["subreddit"],
            "score": p["score"],
            "num_comments": p["num_comments"],
            "thumbnail": p["thumbnail"] if p["thumbnail"].startswith("http") else None,
        })

    _post_cache[cache_key] = (now, posts)
    return posts


def fetch_top_comments(permalink, limit=10):
    """
    Fetch the top N comments for a post. Returns a list of comment body strings.
    Cached per post_id to avoid hammering Reddit on mood-switches.
    """
    # Use permalink as the cache key — it's unique per post.
    now = time.time()
    cached = _comment_cache.get(permalink)
    if cached and now - cached[0] < COMMENT_CACHE_TTL:
        return cached[1]

    url = f"https://www.reddit.com{permalink}.json?limit={limit}&sort=top"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError):
        # On any failure, return empty — comment scoring is optional enrichment.
        _comment_cache[permalink] = (now, [])
        return []

    # Reddit returns [post_data, comments_data] for a permalink request.
    if not isinstance(data, list) or len(data) < 2:
        _comment_cache[permalink] = (now, [])
        return []

    comments = []
    for child in data[1].get("data", {}).get("children", []):
        c = child.get("data", {})
        body = c.get("body", "")
        # Skip deleted, removed, and bot-style comments.
        if body and body not in ("[deleted]", "[removed]") and len(body) > 10:
            comments.append(body[:500])  # cap length per comment
        if len(comments) >= limit:
            break

    _comment_cache[permalink] = (now, comments)
    return comments