const API_BASE = "http://localhost:5000";

const cardStack = document.getElementById("cardStack");
const actions = document.getElementById("actions");
const upBtn = document.getElementById("upBtn");
const downBtn = document.getElementById("downBtn");
const upCountEl = document.getElementById("upCount");
const downCountEl = document.getElementById("downCount");
const totalCountEl = document.getElementById("totalCount");

let queue = [];      // posts waiting to be swiped
let currentPost = null;
let isAnimating = false;

const EMOTION_LABELS = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"];
const EMOTION_EMOJI = {
  anger: "😠", disgust: "🤢", fear: "😨", joy: "😊",
  neutral: "😐", sadness: "😢", surprise: "😲",
};

async function refreshStats() {
  try {
    const res = await fetch(`${API_BASE}/stats`);
    const stats = await res.json();
    upCountEl.textContent = stats.thumbs_up;
    downCountEl.textContent = stats.thumbs_down;
    totalCountEl.textContent = stats.labeled;
  } catch (err) {
    console.error("Failed to fetch stats:", err);
  }
}

async function loadBatch() {
  try {
    const res = await fetch(`${API_BASE}/training-batch?size=20`);
    const data = await res.json();
    queue = data.posts || [];
    if (queue.length === 0) {
      showEmpty();
    } else {
      showNext();
    }
  } catch (err) {
    cardStack.innerHTML = `<div class="empty">Error: ${err.message}<br><br>Is the backend running?</div>`;
  }
}

function showEmpty() {
  cardStack.innerHTML = `
    <div class="empty">
      No more posts to label. Pull some fresh ones?
      <br>
      <button onclick="loadBatch()">Load More</button>
    </div>`;
  actions.style.display = "none";
}

function showNext() {
  if (queue.length === 0) {
    // Out of cards — try to refill before giving up.
    loadBatch();
    return;
  }

  currentPost = queue.shift();
  renderCard(currentPost);
  actions.style.display = "flex";
}

function renderCard(post) {
  const emotions = post.emotions || {};
  // Find the top 2 emotions to highlight as "strong".
  const sorted = EMOTION_LABELS
    .map((e) => [e, emotions[e] || 0])
    .sort((a, b) => b[1] - a[1]);
  const strongSet = new Set(sorted.slice(0, 2).map((x) => x[0]));

  const chips = EMOTION_LABELS.map((emo) => {
    const val = emotions[emo] || 0;
    const cls = strongSet.has(emo) && val > 0.15 ? "emotion-chip strong" : "emotion-chip";
    return `<span class="${cls}">${EMOTION_EMOJI[emo]} ${emo} ${(val * 100).toFixed(0)}%</span>`;
  }).join("");

  cardStack.innerHTML = `
    <div class="card" id="currentCard">
      <div class="card-subreddit">r/${escapeHtml(post.subreddit)}</div>
      <div class="card-title">${escapeHtml(post.title)}</div>
      ${post.body ? `<div class="card-body">${escapeHtml(post.body)}</div>` : ""}
      <div class="card-emotions">${chips}</div>
      <div class="card-stats">
        <span>⬆ ${formatNum(post.score)}</span>
        <span>💬 ${formatNum(post.num_comments)}</span>
        <a class="card-link" href="${post.url}" target="_blank" rel="noopener noreferrer">View on Reddit ↗</a>
      </div>
    </div>`;
}

async function submitFeedback(label) {
  if (isAnimating || !currentPost) return;
  isAnimating = true;

  const card = document.getElementById("currentCard");
  if (card) {
    card.classList.add(label === 1 ? "swiping-up" : "swiping-down");
  }

  // Fire and forget — we don't want to block the UI on the network call.
  fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_id: currentPost.id, label }),
  }).then(() => refreshStats()).catch((err) => console.error(err));

  // Wait for the swipe animation, then show the next card.
  setTimeout(() => {
    isAnimating = false;
    showNext();
  }, 250);
}

upBtn.addEventListener("click", () => submitFeedback(1));
downBtn.addEventListener("click", () => submitFeedback(0));

document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight") submitFeedback(1);
  if (e.key === "ArrowLeft") submitFeedback(0);
});

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatNum(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return n;
}

// Boot.
refreshStats();
loadBatch();
