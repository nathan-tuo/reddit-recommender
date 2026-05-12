from sentiment import score_post, compute_mood_score

AVAILABLE_MOODS = ["angry", "sad", "happy", "outraged", "amused"]

def recommend(posts, mood, top_n=10):
    if mood not in AVAILABLE_MOODS:
        raise ValueError(f"Unknown mood '{mood}'. Choose from: {AVAILABLE_MOODS}")

    scored = []
    for post in posts:
        enriched = score_post(post)
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
        })

    scored.sort(key=lambda x: x["mood_score"], reverse=True)
    return scored[:top_n]
