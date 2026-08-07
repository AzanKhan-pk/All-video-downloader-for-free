const $ = (selector) => document.querySelector(selector);

const urlInput = $("#url");
const fetchButton = $("#fetchBtn");
const statusBox = $("#status");
const resultBox = $("#result");

let selectedMode = "video";
let selectedQuality = "720p";
let currentVideo = null;

function setStatus(message, type = "") {
  statusBox.textContent = message;
  statusBox.className = `status ${type}`.trim();
}

function setButtonLoading(button, loading, loadingText, normalText) {
  button.disabled = loading;
  button.textContent = loading ? loadingText : normalText;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;"
    };

    return entities[character];
  });
}

function updateQualityLabel() {
  const qualityLabel = $("#qualityLabel");

  if (selectedMode === "audio") {
    qualityLabel.textContent = "192 kbps high quality";
    return;
  }

  qualityLabel.textContent =
    selectedQuality === "720p"
      ? "720p recommended"
      : selectedQuality;
}

function renderVideoResult(video) {
  const thumbnail = video.thumbnail
    ? `<img src="${escapeHtml(video.thumbnail)}" alt="Video thumbnail">`
    : `<div class="result-placeholder">AVD</div>`;

  resultBox.innerHTML = `
    ${thumbnail}
    <div>
      <h3>${escapeHtml(video.title)}</h3>
      <p>
        ${escapeHtml(video.creator)}
        · ${escapeHtml(video.duration)}
        · ${escapeHtml(video.views)} views
      </p>
      <p>${escapeHtml(video.platform)}</p>
      <button id="downloadBtn" type="button">
        Download ${selectedMode === "audio" ? "MP3" : "MP4"} ↗
      </button>
    </div>
  `;

  resultBox.hidden = false;

  const downloadButton = $("#downloadBtn");

  if (downloadButton) {
    downloadButton.addEventListener("click", downloadMedia);
  }
}

document.querySelectorAll(".mode").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".mode").forEach((item) => {
      item.classList.remove("active");
    });

    button.classList.add("active");
    selectedMode = button.dataset.mode;
    updateQualityLabel();

    if (currentVideo && !resultBox.hidden) {
      renderVideoResult(currentVideo);
    }
  });
});

document.querySelectorAll(".quality-grid button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".quality-grid button").forEach((item) => {
      item.classList.remove("selected");
    });

    button.classList.add("selected");
    selectedQuality = button.dataset.quality;
    updateQualityLabel();
  });
});

fetchButton.addEventListener("click", async () => {
  const url = urlInput.value.trim();

  if (!url) {
    setStatus("Paste a public video URL first.", "error");
    urlInput.focus();
    return;
  }

  setButtonLoading(
    fetchButton,
    true,
    "Reading...",
    "Fetch media ↗"
  );

  setStatus("Reading public media details...");
  resultBox.hidden = true;
  currentVideo = null;

  try {
    const response = await fetch("/api/info", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ url })
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(
        data.error || "Could not read this link."
      );
    }

    currentVideo = data.video;
    renderVideoResult(currentVideo);

    setStatus(
      `${currentVideo.platform} media found.`,
      "success"
    );
  } catch (error) {
    resultBox.hidden = true;
    setStatus(
      error.message || "Something went wrong.",
      "error"
    );
  } finally {
    setButtonLoading(
      fetchButton,
      false,
      "Reading...",
      "Fetch media ↗"
    );
  }
});

async function downloadMedia() {
  if (!currentVideo) {
    setStatus("Fetch the media details before downloading.", "error");
    return;
  }

  const downloadButton = $("#downloadBtn");

  setButtonLoading(
    downloadButton,
    true,
    "Preparing...",
    `Download ${selectedMode === "audio" ? "MP3" : "MP4"} ↗`
  );

  setStatus("Preparing your file...");

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        url: currentVideo.url,
        mode: selectedMode,
        quality: selectedQuality
      })
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(
        data.error || "Download failed."
      );
    }

    const fileBlob = await response.blob();
    const temporaryUrl = URL.createObjectURL(fileBlob);
    const downloadLink = document.createElement("a");

    const safeFileName = currentVideo.title
      .replace(/[^\w\s.-]/g, "")
      .trim()
      .slice(0, 90) || "video";

    const fileExtension =
      selectedMode === "audio" ? "mp3" : "mp4";

    downloadLink.href = temporaryUrl;
    downloadLink.download = `${safeFileName}.${fileExtension}`;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    downloadLink.remove();

    URL.revokeObjectURL(temporaryUrl);

    setStatus("Your download is ready.", "success");
  } catch (error) {
    setStatus(
      error.message || "Download failed.",
      "error"
    );
  } finally {
    setButtonLoading(
      downloadButton,
      false,
      "Preparing...",
      `Download ${selectedMode === "audio" ? "MP3" : "MP4"} ↗`
    );
  }
}

$("#commentForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const form = event.currentTarget;
  const submitButton = form.querySelector("button");
  const commentStatus = $("#commentStatus");

  const name = $("#name").value.trim();
  const comment = $("#comment").value.trim();

  if (!name || !comment) {
    commentStatus.textContent = "Please complete both fields.";
    commentStatus.className = "status error";
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "Saving...";

  commentStatus.textContent = "Saving your note...";
  commentStatus.className = "status";

  try {
    const response = await fetch("/api/comments", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name,
        comment
      })
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      throw new Error(
        data.error || "Could not save your feedback."
      );
    }

    commentStatus.textContent =
      data.message || "Thanks, your feedback is saved.";
    commentStatus.className = "status success";

    form.reset();
  } catch (error) {
    commentStatus.textContent =
      error.message || "Could not save your feedback.";
    commentStatus.className = "status error";
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = "Send feedback <span>↗</span>";
  }
});

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  {
    threshold: 0.12
  }
);

document.querySelectorAll(".reveal").forEach((element, index) => {
  element.style.transitionDelay =
    `${Math.min(index * 45, 260)}ms`;

  revealObserver.observe(element);
});

urlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    fetchButton.click();
  }
});