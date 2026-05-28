import time
import html
import requests

HEADERS = {
    # Reddit increasingly 403s generic library UAs. A descriptive UA in their
    # recommended format is far more reliable for unauthenticated access.
    "User-Agent": "windows:mood-recommender:v0.2 (by /u/your_username)"
}

# Simple in-memory TTL cache for post listings.
# Key: (subreddit, sort, limit) -> (timestamp, posts)
_post_cache = {}
POST_CACHE_TTL = 300  # 5 minutes

# Cache for comments per post — comments rarely change meaningfully within a session.
# Key: post_id -> (timestamp, comments)
_comment_cache = {}
COMMENT_CACHE_TTL = 600  # 10 minutes


def _extract_media(p):
    """
    Figure out what media a post actually has and return a normalized dict:
      {"type": "image"|"video"|"gallery"|"link"|"none", ...type-specific fields}
    Reddit scatters media across several fields depending on post type.
    """
    # 1. Reddit-hosted video (v.redd.it). Has audio in a separate stream we ignore for POC.
    if p.get("is_video") and p.get("media", {}).get("reddit_video"):
        rv = p["media"]["reddit_video"]
        return {
            "type": "video",
            "video_url": rv.get("fallback_url"),
            "poster": _best_preview_image(p),
        }

    # 2. Gallery (multiple images).
    if p.get("is_gallery") and p.get("media_metadata"):
        images = []
        # gallery_data preserves order; media_metadata has the URLs.
        order = [item["media_id"] for item in p.get("gallery_data", {}).get("items", [])]
        for mid in order:
            meta = p["media_metadata"].get(mid, {})
            src = meta.get("s", {})
            u = src.get("u") or src.get("gif")
            if u:
                images.append(html.unescape(u))
        if images:
            return {"type": "gallery", "images": images}

    # 3. Direct image URL.
    url = p.get("url_overridden_by_dest") or p.get("url", "")
    if url and url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return {"type": "image", "image_url": html.unescape(url)}

    # 4. Reddit preview image (covers a lot of image posts that don't have a direct URL).
    preview_img = _best_preview_image(p)
    if preview_img:
        return {"type": "image", "image_url": preview_img}

    # 5. External link (youtube, imgur page, article, etc.).
    if url and not url.startswith(f"https://www.reddit.com{p.get('permalink', '')}"):
        return {"type": "link", "link_url": url}

    return {"type": "none"}


def _best_preview_image(p):
    """Pull the highest-res preview image Reddit generated, if any. Decodes HTML entities."""
    try:
        source = p["preview"]["images"][0]["source"]["url"]
        return html.unescape(source)
    except (KeyError, IndexError, TypeError):
        return None


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
        full_body = p.get("selftext", "") or ""
        posts.append({
            "id": p["id"],
            "title": p["title"],
            # Short body for scoring (model has a token cap anyway)...
            "body": full_body[:500],
            # ...and a longer one for display.
            "body_full": full_body[:4000],
            "url": f"https://reddit.com{p['permalink']}",
            "permalink": p["permalink"],
            "subreddit": p["subreddit"],
            "score": p["score"],
            "num_comments": p["num_comments"],
            "thumbnail": p["thumbnail"] if p.get("thumbnail", "").startswith("http") else None,
            "media": _extract_media(p),
        })

    _post_cache[cache_key] = (now, posts)
    return posts


def fetch_top_comments(permalink, limit=10):
    """
    Fetch the top N comments for a post. Returns a list of comment body strings.
    Cached per post_id to avoid hammering Reddit on mood-switches.
    """
    return [c["body"] for c in fetch_top_comments_detailed(permalink, limit=limit)]


def fetch_top_comments_detailed(permalink, limit=10):
    """
    Like fetch_top_comments but returns dicts with body, author, and score —
    used for displaying comments in the UI, not just scoring them.
    """
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
        _comment_cache[permalink] = (now, [])
        return []

    if not isinstance(data, list) or len(data) < 2:
        _comment_cache[permalink] = (now, [])
        return []

    comments = []
    for child in data[1].get("data", {}).get("children", []):
        c = child.get("data", {})
        body = c.get("body", "")
        if body and body not in ("[deleted]", "[removed]") and len(body) > 10:
            comments.append({
                "body": body[:600],
                "author": c.get("author", "[unknown]"),
                "score": c.get("score", 0),
            })
        if len(comments) >= limit:
            break

    _comment_cache[permalink] = (now, comments)
    return comments


# A curated spread of subreddits across emotional registers, for diverse training data.
# We rotate through these so you're not labeling 100 variations of today's r/all front page.
DIVERSE_SUBREDDITS = [
    "AskReddit", "aww", "news", "politics", "funny",
    "mildlyinfuriating", "MadeMeSmile", "nottheonion", "tifu", "wholesomememes",
    "rage", "UpliftingNews", "TrueOffMyChest", "facepalm", "HumansBeingBros",
    "WTF", "LifeProTips", "Damnthatsinteresting", "interestingasfuck", "PublicFreakout",
]


def fetch_diverse_posts(per_sub=10, sorts=("hot", "new", "top")):
    """
    Pull a spread of posts across many subreddits and multiple sort orders.
    Gives the training pool variety instead of just the most popular hot posts.
    Rotates which sort each subreddit uses so we get a mix.
    """
    import random
    all_posts = []
    seen_ids = set()

    subs = list(DIVERSE_SUBREDDITS)
    random.shuffle(subs)

    for i, sub in enumerate(subs):
        sort = sorts[i % len(sorts)]  # rotate sorts across subs
        try:
            posts = fetch_posts(subreddit_name=sub, limit=per_sub, sort=sort)
        except Exception:
            continue  # skip subs that error out (private, banned, rate-limited)
        for p in posts:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                all_posts.append(p)

    random.shuffle(all_posts)
    return all_posts