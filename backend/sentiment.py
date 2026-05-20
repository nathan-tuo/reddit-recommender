"""
Emotion-based post scoring using a transformer model.

Uses j-hartmann/emotion-english-distilroberta-base, which classifies text into:
  anger, disgust, fear, joy, neutral, sadness, surprise

We map these onto the app's 5 moods. Title and body are scored separately
and combined, since titles carry most of the emotional signal on Reddit.
"""

from transformers import pipeline
import torch

# Lazy-init so the model loads once and only when first needed.
_classifier = None

def get_classifier():
    global _classifier
    if _classifier is None:
        device = 0 if torch.cuda.is_available() else -1
        _classifier = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=None,  # return all class scores, not just the top one
            device=device,
            truncation=True,
            max_length=512,
        )
    return _classifier


# How our app's moods map onto the model's emotion classes.
# Values are weights — they sum to 1.0 for each mood so the score stays in [0, 1].
MOOD_TO_EMOTIONS = {
    "angry":    {"anger": 1.0},
    "sad":      {"sadness": 1.0},
    "happy":    {"joy": 1.0},
    "outraged": {"anger": 0.5, "disgust": 0.3, "surprise": 0.2},
    "amused":   {"joy": 0.6, "surprise": 0.4},
}

# Small keyword booster — kept as a tiebreaker, not the main signal.
# The model handles the heavy lifting now, so these are slimmed down.
MOOD_KEYWORDS = {
    "angry":    ["furious", "outrage", "disgrace", "incompetent"],
    "sad":      ["heartbreaking", "devastating", "tragedy", "grief"],
    "happy":    ["wholesome", "heartwarming", "blessed", "adorable"],
    "outraged": ["scandal", "exposed", "coverup", "shocking"],
    "amused":   ["hilarious", "cursed", "chaotic", "absurd"],
}


def _emotions_for_texts(texts):
    """
    Run the model on a batch of texts. Returns a list of dicts
    like {"anger": 0.12, "joy": 0.04, ...} — one per input text.
    """
    if not texts:
        return []
    classifier = get_classifier()
    # Replace empty strings with a single space so the tokenizer doesn't choke.
    safe_texts = [t if t.strip() else " " for t in texts]
    raw = classifier(safe_texts, batch_size=16)
    return [
        {item["label"]: item["score"] for item in result}
        for result in raw
    ]


def score_posts(posts):
    """
    Batch-score a list of posts. Much faster than calling score_post in a loop
    because the transformer can process texts in parallel.
    Returns a list of enriched post dicts.
    """
    titles = [p["title"] for p in posts]
    bodies = [p.get("body", "") for p in posts]

    title_emotions = _emotions_for_texts(titles)
    # Only run the model on bodies that actually have text — saves compute.
    body_indices = [i for i, b in enumerate(bodies) if b.strip()]
    body_texts = [bodies[i] for i in body_indices]
    body_results = _emotions_for_texts(body_texts)
    body_emotions = [None] * len(posts)
    for idx, result in zip(body_indices, body_results):
        body_emotions[idx] = result

    enriched = []
    for post, t_emo, b_emo in zip(posts, title_emotions, body_emotions):
        # Title carries 70% of the emotional signal; body 30% when present.
        if b_emo is not None:
            combined = {k: 0.7 * t_emo[k] + 0.3 * b_emo[k] for k in t_emo}
        else:
            combined = t_emo

        # Normalize engagement as a 0–1 signal.
        engagement = min((post["score"] + post["num_comments"] * 2) / 10000, 1.0)

        text_lower = f"{post['title']} {post.get('body', '')}".lower()
        keyword_hits = {
            mood: sum(1 for kw in kws if kw in text_lower)
            for mood, kws in MOOD_KEYWORDS.items()
        }

        enriched.append({
            **post,
            "emotions": combined,
            "engagement": engagement,
            "keyword_hits": keyword_hits,
        })
    return enriched


def score_post(post):
    """Single-post version for compatibility — prefer score_posts for batching."""
    return score_posts([post])[0]


def compute_mood_score(post_data, target_mood):
    """
    Combine the model's emotion probabilities with engagement and a small
    keyword boost. Returns a score in roughly [0, 1].
    """
    emotions = post_data["emotions"]
    engagement = post_data["engagement"]
    kw = post_data["keyword_hits"].get(target_mood, 0)
    keyword_boost = min(kw * 0.05, 0.15)  # smaller boost now that the model is doing real work

    # Weighted sum of the model's emotion probabilities according to the mood mapping.
    emotion_weights = MOOD_TO_EMOTIONS.get(target_mood, {})
    emotion_score = sum(
        emotions.get(emo, 0.0) * weight
        for emo, weight in emotion_weights.items()
    )

    # Outraged and angry posts get an extra engagement boost — outrage spreads.
    if target_mood in ("outraged", "angry"):
        return (emotion_score * 0.65) + (engagement * 0.25) + keyword_boost
    # Amused content also tends to be high-engagement.
    elif target_mood == "amused":
        return (emotion_score * 0.7) + (engagement * 0.2) + keyword_boost
    # Sad and happy lean more on the emotion signal itself.
    else:
        return (emotion_score * 0.85) + (engagement * 0.1) + keyword_boost