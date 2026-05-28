from flask import Flask, request, jsonify
from flask_cors import CORS
from reddit_client import (
    fetch_posts, fetch_diverse_posts, fetch_top_comments_detailed
)
from recommender import recommend, AVAILABLE_MOODS
from sentiment import get_classifier, score_posts, add_comment_signal
import feedback_store

app = Flask(__name__)
CORS(app)


@app.route("/moods", methods=["GET"])
def get_moods():
    return jsonify({"moods": AVAILABLE_MOODS})


@app.route("/recommend", methods=["POST"])
def get_recommendations():
    data = request.get_json()

    mood = data.get("mood", "happy")
    subreddit = data.get("subreddit", "all")
    limit = min(int(data.get("limit", 100)), 200)
    sort = data.get("sort", "hot")
    top_n = int(data.get("top_n", 10))
    use_comments = bool(data.get("use_comments", True))

    try:
        posts = fetch_posts(subreddit_name=subreddit, limit=limit, sort=sort)
        results = recommend(posts, mood, top_n=top_n, use_comments=use_comments)
        return jsonify({"mood": mood, "results": results})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500


@app.route("/training-batch", methods=["GET"])
def get_training_batch():
    """
    Return a batch of unlabeled posts for the swipe screen, enriched with
    comments and comment-aware emotion scores so the displayed emotions
    reflect the whole post (not just a bodyless title).
    """
    batch_size = int(request.args.get("size", 20))

    # Serve from existing unlabeled pool first.
    unlabeled = feedback_store.get_unlabeled_posts(limit=batch_size)

    # Refill from a DIVERSE set of subreddits if the pool is thin.
    if len(unlabeled) < batch_size:
        try:
            fresh = fetch_diverse_posts(per_sub=10)
            enriched = score_posts(fresh)
            feedback_store.save_posts(enriched)
            unlabeled = feedback_store.get_unlabeled_posts(limit=batch_size)
        except Exception as e:
            return jsonify({"error": f"Failed to refill pool: {str(e)}"}), 500

    # Enrich each post in the batch with comments + comment-aware emotions.
    # This is the fix for "link posts show wrong emotions" — we now fold in
    # the comment section, which carries the real emotional signal.
    enriched_batch = []
    for post in unlabeled:
        comments = []
        if post.get("permalink"):
            try:
                comments = fetch_top_comments_detailed(post["permalink"], limit=8)
            except Exception:
                comments = []

        # Blend comment emotions into the post's emotion profile for display.
        if comments:
            # We need the enriched (scored) version to blend into.
            scored = score_posts([post])[0]
            comment_bodies = [c["body"] for c in comments]
            add_comment_signal(scored, comment_bodies)
            post["emotions"] = {k: round(v, 3) for k, v in scored["emotions"].items()}
            # Persist the improved emotions back to the DB.
            feedback_store.save_post(scored)

        post["comments"] = comments
        enriched_batch.append(post)

    return jsonify({"posts": enriched_batch, "count": len(enriched_batch)})


@app.route("/feedback", methods=["POST"])
def submit_feedback():
    """Save a thumbs up (label=1) or down (label=0) for a post."""
    data = request.get_json()
    post_id = data.get("post_id")
    label = data.get("label")

    if not post_id or label not in (0, 1):
        return jsonify({"error": "post_id and label (0 or 1) required"}), 400

    try:
        feedback_store.save_feedback(post_id, label)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/clear-feedback", methods=["POST"])
def clear_feedback():
    """Wipe all labels (and optionally the post pool). Used by the Clear button."""
    data = request.get_json(silent=True) or {}
    wipe_posts = bool(data.get("wipe_posts", False))
    try:
        feedback_store.clear_feedback(wipe_posts=wipe_posts)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stats", methods=["GET"])
def get_stats():
    """Return label counts so the UI can show progress."""
    return jsonify(feedback_store.get_stats())


@app.route("/debug-media", methods=["GET"])
def debug_media():
    """
    Diagnostic: fetch a few live posts and show what media we extract vs.
    what raw fields Reddit actually returned. Visit in browser:
    http://localhost:5001/debug-media?subreddit=aww
    """
    import requests as _rq
    sub = request.args.get("subreddit", "aww")
    ua = request.args.get("ua", "mood-recommender/0.2")
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=8"
    try:
        res = _rq.get(url, headers={"User-Agent": ua}, timeout=10)
        status = res.status_code
        data = res.json()
    except Exception as e:
        return jsonify({"error": str(e), "status": locals().get("status")}), 500

    from reddit_client import _extract_media
    out = []
    for child in data.get("data", {}).get("children", []):
        p = child["data"]
        out.append({
            "title": p["title"][:60],
            "post_hint": p.get("post_hint"),
            "url": p.get("url", "")[:100],
            "has_preview_field": "preview" in p,
            "is_video": p.get("is_video"),
            "is_gallery": p.get("is_gallery"),
            "extracted": _extract_media(p),
        })
    return jsonify({"reddit_status": status, "user_agent_used": ua, "posts": out})


if __name__ == "__main__":
    print("Initializing feedback database...")
    feedback_store.init_db()
    print("Warming up the emotion model...")
    get_classifier()
    print("Ready. Starting server on http://localhost:5001")
    app.run(debug=True, port=5001)