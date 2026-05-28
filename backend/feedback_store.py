"""
SQLite store for user feedback (thumbs up/down on posts).

Two tables:
  - posts: cached snapshot of post metadata + emotion features, keyed by post_id.
           we save these because Reddit posts can disappear, and we need stable
           features at training time.
  - feedback: post_id -> label (1 = thumbs up, 0 = thumbs down), with timestamp.

Designed for a single-user POC. Multi-user would add a user_id column.
"""

import sqlite3
import json
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "feedback.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            body TEXT,
            body_full TEXT,
            url TEXT,
            permalink TEXT,
            subreddit TEXT,
            score INTEGER,
            num_comments INTEGER,
            thumbnail TEXT,
            media_json TEXT,     -- JSON dict describing post media
            emotions_json TEXT,  -- JSON dict of emotion -> prob
            first_seen REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            post_id TEXT PRIMARY KEY,
            label INTEGER NOT NULL,  -- 1 = up, 0 = down
            created_at REAL NOT NULL,
            FOREIGN KEY (post_id) REFERENCES posts(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_label ON feedback(label)")

    # Migration: add columns to pre-existing DBs that were created before these
    # fields existed. SQLite has no "ADD COLUMN IF NOT EXISTS", so we check first.
    cur.execute("PRAGMA table_info(posts)")
    existing_cols = {row["name"] for row in cur.fetchall()}
    if "media_json" not in existing_cols:
        cur.execute("ALTER TABLE posts ADD COLUMN media_json TEXT")
    if "body_full" not in existing_cols:
        cur.execute("ALTER TABLE posts ADD COLUMN body_full TEXT")

    conn.commit()
    conn.close()


def save_post(post):
    """
    Upsert a post snapshot. Expects an enriched post dict from sentiment.score_posts
    (i.e. one that has the `emotions` field). Falls back gracefully if emotions missing.
    """
    conn = _connect()
    cur = conn.cursor()

    emotions = post.get("emotions") or post.get("base_emotions") or {}
    media = post.get("media") or {"type": "none"}

    cur.execute("""
        INSERT INTO posts (id, title, body, body_full, url, permalink, subreddit,
                           score, num_comments, thumbnail, media_json, emotions_json, first_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            score = excluded.score,
            num_comments = excluded.num_comments,
            emotions_json = excluded.emotions_json,
            media_json = excluded.media_json,
            body_full = excluded.body_full
    """, (
        post["id"],
        post["title"],
        post.get("body", ""),
        post.get("body_full", post.get("body", "")),
        post.get("url"),
        post.get("permalink"),
        post.get("subreddit"),
        post.get("score", 0),
        post.get("num_comments", 0),
        post.get("thumbnail"),
        json.dumps(media),
        json.dumps(emotions),
        time.time(),
    ))
    conn.commit()
    conn.close()


def save_posts(posts):
    """Batch version of save_post."""
    for p in posts:
        save_post(p)


def save_feedback(post_id, label):
    """Save a thumbs up (1) or down (0) for a post. Overwrites any prior label."""
    if label not in (0, 1):
        raise ValueError("label must be 0 or 1")
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO feedback (post_id, label, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(post_id) DO UPDATE SET
            label = excluded.label,
            created_at = excluded.created_at
    """, (post_id, label, time.time()))
    conn.commit()
    conn.close()


def get_unlabeled_posts(limit=20):
    """Return up to `limit` posts that don't yet have a feedback label."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.* FROM posts p
        LEFT JOIN feedback f ON p.id = f.post_id
        WHERE f.post_id IS NULL
        ORDER BY RANDOM()
        LIMIT ?
    """, (limit,))
    rows = [_row_to_post(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_labeled_posts():
    """Return all posts that have feedback, joined with their labels."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, f.label, f.created_at as labeled_at
        FROM posts p
        INNER JOIN feedback f ON p.id = f.post_id
        ORDER BY f.created_at DESC
    """)
    rows = []
    for r in cur.fetchall():
        post = _row_to_post(r)
        post["label"] = r["label"]
        post["labeled_at"] = r["labeled_at"]
        rows.append(post)
    conn.close()
    return rows


def clear_feedback(wipe_posts=False):
    """
    Delete all feedback labels. If wipe_posts is True, also clear the post pool
    (so you start completely fresh). Otherwise posts stay cached and become
    available to label again.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM feedback")
    if wipe_posts:
        cur.execute("DELETE FROM posts")
    conn.commit()
    conn.close()


def get_stats():
    """Return label counts and total post pool size."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as n FROM posts")
    n_posts = cur.fetchone()["n"]
    cur.execute("SELECT label, COUNT(*) as n FROM feedback GROUP BY label")
    label_counts = {0: 0, 1: 0}
    for row in cur.fetchall():
        label_counts[row["label"]] = row["n"]
    conn.close()
    return {
        "total_posts": n_posts,
        "labeled": label_counts[0] + label_counts[1],
        "thumbs_up": label_counts[1],
        "thumbs_down": label_counts[0],
        "unlabeled": n_posts - (label_counts[0] + label_counts[1]),
    }


def _row_to_post(row):
    try:
        emotions = json.loads(row["emotions_json"]) if row["emotions_json"] else {}
    except (json.JSONDecodeError, TypeError):
        emotions = {}
    # media_json / body_full may be absent on very old rows — guard with try/except.
    try:
        media = json.loads(row["media_json"]) if row["media_json"] else {"type": "none"}
    except (json.JSONDecodeError, TypeError, IndexError):
        media = {"type": "none"}
    try:
        body_full = row["body_full"] or ""
    except (IndexError, KeyError):
        body_full = ""
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"] or "",
        "body_full": body_full,
        "url": row["url"],
        "permalink": row["permalink"],
        "subreddit": row["subreddit"],
        "score": row["score"],
        "num_comments": row["num_comments"],
        "thumbnail": row["thumbnail"],
        "media": media,
        "emotions": emotions,
    }