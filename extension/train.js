const API_BASE = "http://localhost:5000";

const cardStack = document.getElementById("cardStack");
const actions = document.getElementById("actions");
const upBtn = document.getElementById("upBtn");
const downBtn = document.getElementById("downBtn");
const clearBtn = document.getElementById("clearBtn");
const upCountEl = document.getElementById("upCount");
const downCountEl = document.getElementById("downCount");
const totalCountEl = document.getElementById("totalCount");

let queue = [];
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
  cardStack.innerHTML = `<div class="empty">Loading posts and comments...<br><span style="font-size:12px">(fetching comments can take a few seconds)</span></div>`;
  actions.style.display = "none";
  try {
    const res = await fetch(`${API_BASE}/training-batch?size=20`);
    const data = await res.json();
    if (data.error) throw new Error(data.error);
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
      <br><button id="loadMoreBtn">Load More</button>
    </div>`;
  document.getElementById("loadMoreBtn").addEventListener("click", loadBatch);
  actions.style.display = "none";
}

function showNext() {
  if (queue.length === 0) {
    loadBatch();
    return;
  }
  currentPost = queue.shift();
  renderCard(currentPost);
  actions.style.display = "flex";
}

function renderCard(post) {
  const emotions = post.emotions || {};
  const sorted = EMOTION_LABELS
    .map((e) => [e, emotions[e] || 0])
    .sort((a, b) => b[1] - a[1]);
  const strongSet = new Set(sorted.slice(0, 2).map((x) => x[0]));

  const chips = EMOTION_LABELS.map((emo) => {
    const val = emotions[emo] || 0;
    const cls = strongSet.has(emo) && val > 0.15 ? "emotion-chip strong" : "emotion-chip";
    return `<span class="${cls}">${EMOTION_EMOJI[emo]} ${emo} ${(val * 100).toFixed(0)}%</span>`;
  }).join("");

  // Render media based on what the backend extracted.
  const mediaHtml = renderMedia(post.media);

  // Comments block.
  let commentsHtml = "";
  const comments = post.comments || [];
  if (comments.length > 0) {
    const items = comments.map((c) => `
      <div class="comment">
        <div class="comment-meta">u/${escapeHtml(c.author)} · ⬆ ${formatNum(c.score)}</div>
        ${escapeHtml(c.body)}
      </div>`).join("");
    commentsHtml = `
      <div class="comments-header">💬 Top comments (${comments.length})</div>
      <div class="comments">${items}</div>`;
  } else {
    commentsHtml = `<div class="no-comments">No comments available for this post.</div>`;
  }

  const bodyText = post.body_full || post.body || "";

  cardStack.innerHTML = `
    <div class="card" id="currentCard">
      <div class="card-subreddit">r/${escapeHtml(post.subreddit)}</div>
      <div class="card-title">${escapeHtml(post.title)}</div>
      ${bodyText ? `<div class="card-body">${escapeHtml(bodyText)}</div>` : ""}
      ${mediaHtml}
      <div class="card-emotions">${chips}</div>
      <div class="card-stats">
        <span>⬆ ${formatNum(post.score)}</span>
        <span>💬 ${formatNum(post.num_comments)}</span>
        <a class="card-link" href="${escapeAttr(post.url)}" target="_blank" rel="noopener noreferrer">View on Reddit ↗</a>
      </div>
      ${commentsHtml}
    </div>`;
}

function renderMedia(media) {
  if (!media || media.type === "none") return "";

  if (media.type === "image" && media.image_url) {
    return `<img class="card-image" src="${escapeAttr(media.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'" />`;
  }

  if (media.type === "video" && media.video_url) {
    const poster = media.poster ? `poster="${escapeAttr(media.poster)}"` : "";
    return `
      <video class="card-image" controls preload="metadata" ${poster}>
        <source src="${escapeAttr(media.video_url)}" type="video/mp4" />
      </video>`;
  }

  if (media.type === "gallery" && Array.isArray(media.images)) {
    return `<div class="gallery">` + media.images.map((u) =>
      `<img class="card-image gallery-img" src="${escapeAttr(u)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'" />`
    ).join("") + `</div>`;
  }

  if (media.type === "link" && media.link_url) {
    return `<a class="media-link" href="${escapeAttr(media.link_url)}" target="_blank" rel="noopener noreferrer">🔗 ${escapeHtml(media.link_url)}</a>`;
  }

  return "";
}

async function submitFeedback(label) {
  if (isAnimating || !currentPost) return;
  isAnimating = true;

  const card = document.getElementById("currentCard");
  if (card) card.classList.add(label === 1 ? "swiping-up" : "swiping-down");

  fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_id: currentPost.id, label }),
  }).then(() => refreshStats()).catch((err) => console.error(err));

  setTimeout(() => {
    isAnimating = false;
    showNext();
  }, 220);
}

upBtn.addEventListener("click", () => submitFeedback(1));
downBtn.addEventListener("click", () => submitFeedback(0));

clearBtn.addEventListener("click", async () => {
  if (!confirm("Delete ALL your labels? This can't be undone.\n\n(Posts stay cached so you can re-label them.)")) {
    return;
  }
  try {
    await fetch(`${API_BASE}/clear-feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wipe_posts: false }),
    });
    await refreshStats();
    loadBatch();
  } catch (err) {
    alert("Failed to clear: " + err.message);
  }
});

document.addEventListener("keydown", (e) => {
  // Don't hijack arrows when the user is scrolling a comments box with focus.
  if (e.key === "ArrowRight") submitFeedback(1);
  if (e.key === "ArrowLeft") submitFeedback(0);
});

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function escapeAttr(str) { return escapeHtml(str); }
function formatNum(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return n;
}

refreshStats();
loadBatch();