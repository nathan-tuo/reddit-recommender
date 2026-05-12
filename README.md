# Reddit Mood Recommender

A browser extension that recommends Reddit posts based on your desired emotional state — angry, sad, happy, outraged, or amused.

---

## Setup

### 1. Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click **"Create App"** → select **script**
3. Note your `client_id` (under the app name) and `client_secret`

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file in `backend/`:

```
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=mood-recommender/0.1
```

Run the server:

```bash
python app.py
```

Server starts at `http://localhost:5000`.

### 3. Chrome Extension

1. Open Chrome → go to `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** → select the `extension/` folder
4. The extension icon appears in your toolbar

---

## Usage

1. Make sure the backend is running (`python app.py`)
2. Click the extension icon
3. Pick a **mood**, optional **subreddit**, and **sort order**
4. Hit **Find Posts** — top 10 matches appear ranked by mood score
5. Click any post to open it on Reddit

---

## How Mood Scoring Works

Each post is analyzed with VADER sentiment analysis and scored against your target mood:

| Mood | Signal |
|---|---|
| Angry | High negativity + engagement |
| Sad | High negativity + low arousal |
| Happy | High positivity + positive compound score |
| Outraged | Negativity + very high engagement (comments/score) |
| Amused | Neutral/mixed sentiment + high engagement |

Keyword hits (e.g. "furious", "heartbreaking", "hilarious") provide a small boost on top.

---

## Project Structure

```
reddit-recommender/
├── backend/
│   ├── app.py            # Flask API
│   ├── reddit_client.py  # PRAW integration
│   ├── recommender.py    # Ranking logic
│   ├── sentiment.py      # VADER scoring + mood mapping
│   └── requirements.txt
├── extension/
│   ├── manifest.json     # Chrome MV3 config
│   ├── popup.html        # UI
│   └── popup.js          # Logic
└── README.md
```

---

## Ideas for v2

- [ ] User history tracking (liked/disliked posts) to improve recommendations
- [ ] Subreddit auto-suggestions based on mood
- [ ] Inject recommendations directly into the Reddit feed via `content.js`
- [ ] Swap VADER for a fine-tuned transformer model
- [ ] Deploy backend to a server (remove localhost dependency)
