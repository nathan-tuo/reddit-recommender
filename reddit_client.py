import praw
import os
from dotenv import load_dotenv

load_dotenv()

def get_reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "mood-recommender/0.1"),
    )

def fetch_posts(subreddit_name="all", limit=100, sort="hot"):
    reddit = get_reddit_client()
    subreddit = reddit.subreddit(subreddit_name)

    fetcher = {
        "hot": subreddit.hot,
        "new": subreddit.new,
        "top": subreddit.top,
        "rising": subreddit.rising,
    }.get(sort, subreddit.hot)

    posts = []
    for post in fetcher(limit=limit):
        posts.append({
            "id": post.id,
            "title": post.title,
            "body": post.selftext[:500] if post.selftext else "",
            "url": f"https://reddit.com{post.permalink}",
            "subreddit": post.subreddit.display_name,
            "score": post.score,
            "num_comments": post.num_comments,
            "thumbnail": post.thumbnail if post.thumbnail.startswith("http") else None,
        })

    return posts
