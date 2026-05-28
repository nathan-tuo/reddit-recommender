from flask import Flask, request, jsonify
from flask_cors import CORS
from reddit_client import fetch_posts
from recommender import recommend, AVAILABLE_MOODS
from sentiment import get_classifier, score_posts
import feedback_store as feedback_store

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
    Return a batch of unlabeled posts for the swipe screen.
    Pulls from already-seen posts in the DB; if none, fetches fresh from Reddit.
    """
    batch_size = int(request.args.get("size", 20))
    subreddit = request.args.get("subreddit", "all")

    # First, try to serve from the existing pool.
    unlabeled = feedback_store.get_unlabeled_posts(limit=batch_size)

    # If the pool is thin (cold start or user blew through it), pull fresh from Reddit.
    if len(unlabeled) < batch_size:
        try:
            fresh_posts = fetch_posts(subreddit_name=subreddit, limit=100, sort="hot")
            enriched = score_posts(fresh_posts)
            feedback_store.save_posts(enriched)
            unlabeled = feedback_store.get_unlabeled_posts(limit=batch_size)
        except Exception as e:
            return jsonify({"error": f"Failed to refill pool: {str(e)}"}), 500

    return jsonify({"posts": unlabeled, "count": len(unlabeled)})


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


@app.route("/stats", methods=["GET"])
def get_stats():
    """Return label counts so the UI can show progress."""
    return jsonify(feedback_store.get_stats())


if __name__ == "__main__":
    print("Initializing feedback database...")
    feedback_store.init_db()
    print("Warming up the emotion model...")
    get_classifier()
    print("Ready. Starting server on http://localhost:5000")
    app.run(debug=True, port=5000)
