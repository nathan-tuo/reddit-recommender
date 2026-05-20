"""
Two-stage ranking:
  1. Score all fetched posts on title + body (fast, batched).
  2. For the top K candidates, fetch top comments and re-score with comment signal.
  3. Re-sort and return the top N.

This avoids hammering Reddit's comment API for posts that wouldn't make the cut anyway.
"""

from sentiment import score_posts, add_comment_signal, compute_mood_score
from reddit_client import fetch_top_comments

AVAILABLE_MOODS = ["angry", "sad", "happy", "outraged", "amused"]

# How many top candidates to fetch comments for. Bigger = better quality, slower + more API calls.
COMMENT_SHORTLIST_SIZE = 20


def _serialize(enriched, mood_score):
    return {
        "id": enriched["id"],
        "title": enriched["title"],
        "url": enriched["url"],
        "subreddit": enriched["subreddit"],
        "score": enriched["score"],
        "num_comments": enriched["num_comments"],
        "thumbnail": enriched["thumbnail"],
        "mood_score": round(mood_score, 4),
        "emotions": {k: round(v, 3) for k, v in enriched["emotions"].items()},
        "has_comment_signal": enriched.get("comment_emotions") is not None,
    }


def recommend(posts, mood, top_n=10, use_comments=True):
    if mood not in AVAILABLE_MOODS:
        raise ValueError(f"Unknown mood '{mood}'. Choose from: {AVAILABLE_MOODS}")

    # Stage 1: score everything on title + body.
    enriched_posts = score_posts(posts)

    # Initial ranking based on title/body only.
    initial = sorted(
        enriched_posts,
        key=lambda p: compute_mood_score(p, mood),
        reverse=True,
    )

    if use_comments:
        # Stage 2: for the top K, fetch comments and blend them in.
        shortlist = initial[:COMMENT_SHORTLIST_SIZE]
        for post in shortlist:
            # Skip posts that already have comment signal cached from a previous run.
            if post.get("comment_emotions") is None and post.get("num_comments", 0) > 0:
                permalink = post.get("permalink", "")
                if permalink:
                    comments = fetch_top_comments(permalink, limit=8)
                    if comments:
                        add_comment_signal(post, comments)

        # Re-rank the shortlist with the new comment-blended scores.
        shortlist.sort(
            key=lambda p: compute_mood_score(p, mood),
            reverse=True,
        )
        final = shortlist[:top_n]
    else:
        final = initial[:top_n]

    return [_serialize(p, compute_mood_score(p, mood)) for p in final]