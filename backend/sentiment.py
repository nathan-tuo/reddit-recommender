from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

# Keywords that push posts toward specific moods
MOOD_KEYWORDS = {
    "angry": ["outrage", "disgusting", "unacceptable", "furious", "ridiculous",
              "corrupt", "scam", "disgrace", "pathetic", "incompetent"],
    "sad": ["heartbreaking", "devastating", "loss", "died", "cancer", "tragedy",
            "alone", "depression", "grief", "crying", "miss", "gone"],
    "happy": ["wholesome", "amazing", "beautiful", "love", "heartwarming",
              "adorable", "wonderful", "blessed", "excited", "joy"],
    "outraged": ["scandal", "exposed", "lied", "coverup", "abuse", "injustice",
                 "banned", "fired", "arrested", "shocking", "unbelievable"],
    "amused": ["lol", "funny", "hilarious", "ironic", "classic", "cursed",
               "wild", "surreal", "chaotic", "unexpected"],
}

def score_post(post):
    text = f"{post['title']} {post['body']}"
    scores = analyzer.polarity_scores(text)

    # Normalize engagement as a 0–1 signal
    engagement = min((post["score"] + post["num_comments"] * 2) / 10000, 1.0)

    keyword_hits = {}
    lower_text = text.lower()
    for mood, keywords in MOOD_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lower_text)
        keyword_hits[mood] = hits

    return {
        **post,
        "sentiment": scores,
        "engagement": engagement,
        "keyword_hits": keyword_hits,
    }

def compute_mood_score(post_data, target_mood):
    s = post_data["sentiment"]
    engagement = post_data["engagement"]
    kw = post_data["keyword_hits"].get(target_mood, 0)
    keyword_boost = min(kw * 0.1, 0.3)

    if target_mood == "angry":
        # High negativity + engagement
        return (s["neg"] * 0.5) + (engagement * 0.3) + keyword_boost

    elif target_mood == "sad":
        # High negativity, low compound (not just angry)
        sadness = s["neg"] * 0.5 + (1 - s["compound"]) * 0.1
        return sadness + keyword_boost

    elif target_mood == "happy":
        return (s["pos"] * 0.5) + (s["compound"] * 0.2) + keyword_boost

    elif target_mood == "outraged":
        # Negativity + very high engagement
        return (s["neg"] * 0.4) + (engagement * 0.4) + keyword_boost

    elif target_mood == "amused":
        # Neutral/mixed sentiment + engagement
        neutrality = 1 - abs(s["compound"])
        return (neutrality * 0.4) + (engagement * 0.3) + keyword_boost

    return 0.0
