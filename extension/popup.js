const API_BASE = "http://localhost:5001";

const fetchBtn = document.getElementById("fetchBtn");
const moodSelect = document.getElementById("moodSelect");
const subredditInput = document.getElementById("subredditInput");
const sortSelect = document.getElementById("sortSelect");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const trainLink = document.getElementById("trainLink");

const MOOD_EMOJI = {
  angry: "😤", sad: "😢", happy: "😊", outraged: "🤬", amused: "😂",
};

trainLink.addEventListener("click", (e) => {
  e.preventDefault();
  // Open the training screen in a new tab — the popup is too cramped for swiping.
  chrome.tabs.create({ url: chrome.runtime.getURL("train.html") });
});

fetchBtn.addEventListener("click", async () => {
  const mood = moodSelect.value;
  const subreddit = subredditInput.value.trim() || "all";
  const sort = sortSelect.value;

  fetchBtn.disabled = true;
  fetchBtn.textContent = "Fetching...";
  statusEl.textContent = "Scoring posts, hang tight...";
  resultsEl.innerHTML = "";

  try {
    const res = await fetch(`${API_BASE}/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mood, subreddit, sort, limit: 100, top_n: 10 }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Server error");
    }

    const data = await res.json();
    renderResults(data.results, data.mood);
    statusEl.textContent = `Top ${data.results.length} posts for "${mood}" mood`;
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    fetchBtn.disabled = false;
    fetchBtn.textContent = "Find Posts";
  }
});

function renderResults(posts, mood) {
  if (!posts.length) {
    resultsEl.innerHTML = `<div id="status">No posts found. Try a different subreddit.</div>`;
    return;
  }

  resultsEl.innerHTML = posts.map((post) => `
    <a class="post-card" href="${post.url}" target="_blank" rel="noopener noreferrer">
      <div class="post-meta">
        <span>r/${escapeHtml(post.subreddit)}</span>
        <span class="mood-badge">${MOOD_EMOJI[mood] || ""} ${(post.mood_score * 100).toFixed(0)}% match</span>
      </div>
      <div class="post-title">${escapeHtml(post.title)}</div>
      <div class="post-stats">
        <span>⬆ ${formatNum(post.score)}</span>
        <span>💬 ${formatNum(post.num_comments)}</span>
      </div>
    </a>
  `).join("");
}

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
