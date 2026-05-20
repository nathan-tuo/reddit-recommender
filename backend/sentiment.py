"""
Emotion-based post scoring using a transformer model.

Uses j-hartmann/emotion-english-distilroberta-base, which classifies text into:
  anger, disgust, fear, joy, neutral, sadness, surprise

Mapped onto the app's 5 moods. We score titles, bodies, and (optionally)
top comments separately, then blend them — the comment section often reveals
the actual emotional tenor of a post better than the post itself.
"""

from transformers import pipeline
import torch

_classifier = None

# Cache of fully-scored posts. Key: post_id -> enriched post dict.
# Lives for the life of the process — emotion content of a post doesn't change.
_score_cache = {}


def get_classifier():
    global _classifier
    if _classifier is None:
        device = 0 if torch.cuda.is_available() else -1
        _classifier = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=None,
            device=device,
            truncation=True,
            max_length=512,
        )
    return _classifier


MOOD_TO_EMOTIONS = {
    "angry":    {"anger": 1.0},
    "sad":      {"sadness": 1.0},
    "happy":    {"joy": 1.0},
    "outraged": {"anger": 0.5, "disgust": 0.3, "surprise": 0.2},
    "amused":   {"joy": 0.6, "surprise": 0.4},
}

MOOD_KEYWORDS = {
    "angry":    ["furious", "outrage", "disgrace", "incompetent"],
    "sad":      ["heartbreaking", "devastating", "tragedy", "grief"],
    "happy":    ["wholesome", "heartwarming", "blessed", "adorable"],
    "outraged": ["scandal", "exposed", "coverup", "shocking"],
    "amused":   ["hilarious", "cursed", "chaotic", "absurd"],
}

EMOTION_LABELS = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]


def _emotions_for_texts(texts):
    """Run the model on a batch of texts. Returns list of {label: score} dicts."""
    if not texts:
        return []
    classifier = get_classifier()
    safe_texts = [t if t.strip() else " " for t in texts]
    raw = classifier(safe_texts, batch_size=16)
    return [
        {item["label"]: item["score"] for item in result}
        for result in raw
    ]


def _average_emotions(emotion_dicts):
    """Average a list of emotion dicts into one. Returns None if list is empty."""
    if not emotion_dicts:
        return None
    avg = {label: 0.0 for label in EMOTION_LABELS}
    for d in emotion_dicts:
        for label in EMOTION_LABELS:
            avg[label] += d.get(label, 0.0)
    n = len(emotion_dicts)
    return {label: avg[label] / n for label in EMOTION_LABELS}


def score_posts(posts):
    """
    Batch-score posts on title + body. Uses the per-post cache so previously
    scored posts are reused across mood-switches and refetches.
    """
    to_score = []
    to_score_indices = []
    enriched = [None] * len(posts)

    for i, post in enumerate(posts):
        cached = _score_cache.get(post["id"])
        if cached is not None:
            # Refresh engagement numbers in case score/comments grew since last cache.
            cached["score"] = post["score"]
            cached["num_comments"] = post["num_comments"]
            cached["engagement"] = min(
                (post["score"] + post["num_comments"] * 2) / 10000, 1.0
            )
            enriched[i] = cached
        else:
            to_score.append(post)
            to_score_indices.append(i)

    if to_score:
        titles = [p["title"] for p in to_score]
        bodies = [p.get("body", "") for p in to_score]

        title_emotions = _emotions_for_texts(titles)
        body_indices = [j for j, b in enumerate(bodies) if b.strip()]
        body_emotions_raw = _emotions_for_texts([bodies[j] for j in body_indices])
        body_emotions = [None] * len(to_score)
        for j, result in zip(body_indices, body_emotions_raw):
            body_emotions[j] = result

        for j, post in enumerate(to_score):
            t_emo = title_emotions[j]
            b_emo = body_emotions[j]

            if b_emo is not None:
                base_emotions = {k: 0.7 * t_emo[k] + 0.3 * b_emo[k] for k in t_emo}
            else:
                base_emotions = t_emo

            engagement = min(
                (post["score"] + post["num_comments"] * 2) / 10000, 1.0
            )

            text_lower = f"{post['title']} {post.get('body', '')}".lower()
            keyword_hits = {
                mood: sum(1 for kw in kws if kw in text_lower)
                for mood, kws in MOOD_KEYWORDS.items()
            }

            scored = {
                **post,
                "base_emotions": base_emotions,  # title + body only
                "comment_emotions": None,        # filled in later if available
                "emotions": base_emotions,       # final blended emotions
                "engagement": engagement,
                "keyword_hits": keyword_hits,
            }
            _score_cache[post["id"]] = scored
            enriched[to_score_indices[j]] = scored

    return enriched


def add_comment_signal(enriched_post, comment_bodies, comment_weight=0.35):
    """
    Enrich a post with comment-section emotions. Blends comment emotions
    into the final `emotions` field. Mutates and returns the post dict.
    """
    if not comment_bodies:
        return enriched_post

    comment_emotion_list = _emotions_for_texts(comment_bodies)
    avg_comment_emo = _average_emotions(comment_emotion_list)

    base = enriched_post["base_emotions"]
    blended = {
        k: (1 - comment_weight) * base[k] + comment_weight * avg_comment_emo[k]
        for k in base
    }

    enriched_post["comment_emotions"] = avg_comment_emo
    enriched_post["emotions"] = blended
    _score_cache[enriched_post["id"]] = enriched_post
    return enriched_post


def compute_mood_score(post_data, target_mood):
    """Combine emotion probabilities, engagement, and keyword boost into [0, 1]."""
    emotions = post_data["emotions"]
    engagement = post_data["engagement"]
    kw = post_data["keyword_hits"].get(target_mood, 0)
    keyword_boost = min(kw * 0.05, 0.15)

    emotion_weights = MOOD_TO_EMOTIONS.get(target_mood, {})
    emotion_score = sum(
        emotions.get(emo, 0.0) * weight
        for emo, weight in emotion_weights.items()
    )

    if target_mood in ("outraged", "angry"):
        return (emotion_score * 0.65) + (engagement * 0.25) + keyword_boost
    elif target_mood == "amused":
        return (emotion_score * 0.7) + (engagement * 0.2) + keyword_boost
    else:
        return (emotion_score * 0.85) + (engagement * 0.1) + keyword_boost


# Kept for backwards compatibility.
def score_post(post):
    return score_posts([post])[0]