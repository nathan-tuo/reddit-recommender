from flask import Flask, request, jsonify
from flask_cors import CORS
from reddit_client import fetch_posts
from recommender import recommend, AVAILABLE_MOODS
from sentiment import get_classifier

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
    use_comments = bool(data.get("use_comments", True))  # new flag, defaults on

    try:
        posts = fetch_posts(subreddit_name=subreddit, limit=limit, sort=sort)
        results = recommend(posts, mood, top_n=top_n, use_comments=use_comments)
        return jsonify({"mood": mood, "results": results})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500

if __name__ == "__main__":
    print("Warming up the emotion model...")
    get_classifier()
    print("Ready. Starting server on http://localhost:5000")
    app.run(debug=True, port=5000)