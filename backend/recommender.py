from sentiment import score_posts, compute_mood_score

AVAILABLE_MOODS = ["angry", "sad", "happy", "outraged", "amused"]

def recommend(posts, mood, top_n=10):
    if mood not in AVAILABLE_MOODS:
        raise ValueError(f"Unknown mood '{mood}'. Choose from: {AVAILABLE_MOODS}")

    # Score all posts in one batched call — much faster than one-by-one.
    enriched_posts = score_posts(posts)

    scored = []
    for enriched in enriched_posts:
        mood_score = compute_mood_score(enriched, mood)
        scored.append({
            "id": enriched["id"],
            "title": enriched["title"],
            "url": enriched["url"],
            "subreddit": enriched["subreddit"],
            "score": enriched["score"],
            "num_comments": enriched["num_comments"],
            "thumbnail": enriched["thumbnail"],
            "mood_score": round(mood_score, 4),
            # Expose the emotion breakdown — useful for debugging and UI.
            "emotions": {k: round(v, 3) for k, v in enriched["emotions"].items()},
        })

    scored.sort(key=lambda x: x["mood_score"], reverse=True)
    return scored[:top_n]