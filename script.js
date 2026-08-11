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

// ==========================================================
// DOWNLOAD PROGRESS SYSTEM
// ==========================================================

let activeDownloadJob = null;
let progressTimer = null;


function formatBytes(bytes) {

  if (!bytes || bytes <= 0) {
    return "0 B";
  }

  const units = [
    "B",
    "KB",
    "MB",
    "GB",
    "TB"
  ];

  const index = Math.min(
    Math.floor(
      Math.log(bytes) / Math.log(1024)
    ),
    units.length - 1
  );

  const value =
    bytes / Math.pow(1024, index);

  return `${value.toFixed(
    index === 0 ? 0 : 2
  )} ${units[index]}`;
}


function formatSpeed(bytesPerSecond) {

  if (
    !bytesPerSecond ||
    bytesPerSecond <= 0
  ) {
    return "Speed —";
  }

  return `${formatBytes(
    bytesPerSecond
  )}/s`;
}


function formatEta(seconds) {

  if (
    seconds === null ||
    seconds === undefined ||
    !Number.isFinite(seconds)
  ) {
    return "ETA —";
  }

  seconds = Math.max(
    0,
    Math.round(seconds)
  );

  const hours =
    Math.floor(seconds / 3600);

  const minutes =
    Math.floor(
      (seconds % 3600) / 60
    );

  const secs =
    seconds % 60;

  if (hours > 0) {
    return `ETA ${hours}h ${minutes}m`;
  }

  if (minutes > 0) {
    return `ETA ${minutes}m ${secs}s`;
  }

  return `ETA ${secs}s`;
}


function showDownloadProgress() {

  const box =
    $("#downloadProgress");

  if (box) {
    box.hidden = false;
  }
}


function updateDownloadProgress(job) {

  const title =
    $("#downloadTitle");

  const percent =
    $("#downloadPercent");

  const bar =
    $("#downloadProgressBar");

  const amount =
    $("#downloadAmount");

  const speed =
    $("#downloadSpeed");

  const eta =
    $("#downloadEta");

  const network =
    $("#downloadNetwork");

  const pauseButton =
    $("#pauseDownloadBtn");

  const resumeButton =
    $("#resumeDownloadBtn");

  if (!title) {
    return;
  }

  const safePercent =
    Math.min(
      100,
      Math.max(
        0,
        Number(job.percent || 0)
      )
    );

  title.textContent =
    job.title ||
    "Preparing download...";

  percent.textContent =
    `${safePercent.toFixed(0)}%`;

  bar.style.width =
    `${safePercent}%`;

  const downloaded =
    formatBytes(
      Number(
        job.downloaded_bytes || 0
      )
    );

  const total =
    job.total_bytes
      ? formatBytes(
          Number(
            job.total_bytes
          )
        )
      : "—";

  amount.textContent =
    `${downloaded} / ${total}`;

  speed.textContent =
    formatSpeed(
      Number(job.speed || 0)
    );

  eta.textContent =
    formatEta(job.eta);

  if (
    job.status === "network_error"
  ) {

    network.hidden = false;

    network.textContent =
      "⚠ Network issue — press Resume when connection is back.";

    pauseButton.hidden = true;
    resumeButton.hidden = false;

  } else if (
    job.status === "paused"
  ) {

    network.hidden = false;

    network.textContent =
      "Download paused.";

    pauseButton.hidden = true;
    resumeButton.hidden = false;

  } else {

    network.hidden = true;

    pauseButton.hidden =
      ![
        "starting",
        "preparing",
        "downloading"
      ].includes(job.status);

    resumeButton.hidden = true;
  }

  if (
    job.status === "completed"
  ) {

    title.textContent =
      "Download complete";

    percent.textContent =
      "100%";

    bar.style.width =
      "100%";

    speed.textContent =
      "Complete";

    eta.textContent =
      "Ready";

    network.hidden = true;

    pauseButton.hidden = true;
    resumeButton.hidden = true;
  }
}


async function getDownloadStatus() {

  if (!activeDownloadJob) {
    return null;
  }

  const response =
    await fetch(
      `/api/download/${activeDownloadJob}/status`,
      {
        cache: "no-store"
      }
    );

  const data =
    await response.json();

  if (
    !response.ok ||
    !data.ok
  ) {
    throw new Error(
      data.error ||
      "Could not read download status."
    );
  }

  return data.job;
}


function stopProgressPolling() {

  if (progressTimer) {
    clearTimeout(progressTimer);
    progressTimer = null;
  }
}


async function pollDownloadStatus() {

  stopProgressPolling();

  if (!activeDownloadJob) {
    return;
  }

  try {

    const job =
      await getDownloadStatus();

    updateDownloadProgress(job);

    if (
      job.status === "completed"
    ) {

      stopProgressPolling();

      const link =
        document.createElement("a");

      link.href =
        `/api/download/${activeDownloadJob}/file`;

      link.download = "";

      document.body.appendChild(link);

      link.click();

      link.remove();

      setStatus(
        "Your download is ready.",
        "success"
      );

      const downloadButton =
        $("#downloadBtn");

      if (downloadButton) {

        setButtonLoading(
          downloadButton,
          false,
          "Preparing...",
          `Download ${
            selectedMode === "audio"
              ? "MP3"
              : "MP4"
          } ↗`
        );
      }

      return;
    }

    if (
      job.status === "cancelled"
    ) {

      stopProgressPolling();

      setStatus(
        "Download cancelled.",
        "error"
      );

      return;
    }

    if (
      job.status === "error"
    ) {

      stopProgressPolling();

      setStatus(
        job.error ||
        "Download failed.",
        "error"
      );

      return;
    }

    progressTimer =
      setTimeout(
        pollDownloadStatus,
        700
      );

  } catch (error) {

    progressTimer =
      setTimeout(
        pollDownloadStatus,
        1500
      );
  }
}


async function downloadMedia() {

  if (!currentVideo) {

    setStatus(
      "Fetch the media details before downloading.",
      "error"
    );

    return;
  }

  const downloadButton =
    $("#downloadBtn");

  setButtonLoading(
    downloadButton,
    true,
    "Starting...",
    `Download ${
      selectedMode === "audio"
        ? "MP3"
        : "MP4"
    } ↗`
  );

  showDownloadProgress();

  setStatus(
    "Starting your download..."
  );

  try {

    const response =
      await fetch(
        "/api/download",
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json"
          },

          body: JSON.stringify({
            url: currentVideo.url,
            mode: selectedMode,
            quality: selectedQuality
          })
        }
      );

    const data =
      await response.json();

    if (
      !response.ok ||
      !data.ok
    ) {

      throw new Error(
        data.error ||
        "Could not start download."
      );
    }

    activeDownloadJob =
      data.job_id;

    setStatus(
      "Download started.",
      "success"
    );

    pollDownloadStatus();

  } catch (error) {

    setStatus(
      error.message ||
      "Download failed.",
      "error"
    );

    setButtonLoading(
      downloadButton,
      false,
      "Preparing...",
      `Download ${
        selectedMode === "audio"
          ? "MP3"
          : "MP4"
      } ↗`
    );
  }
}


// ==========================================================
// PAUSE
// ==========================================================

$("#pauseDownloadBtn")?.addEventListener(
  "click",
  async () => {

    if (!activeDownloadJob) {
      return;
    }

    try {

      const response =
        await fetch(
          `/api/download/${activeDownloadJob}/pause`,
          {
            method: "POST"
          }
        );

      const data =
        await response.json();

      if (
        !response.ok ||
        !data.ok
      ) {

        throw new Error(
          data.error ||
          "Could not pause download."
        );
      }

      setStatus(
        "Pausing download..."
      );

    } catch (error) {

      setStatus(
        error.message ||
        "Could not pause download.",
        "error"
      );
    }
  }
);


// ==========================================================
// RESUME
// ==========================================================

$("#resumeDownloadBtn")?.addEventListener(
  "click",
  async () => {

    if (!activeDownloadJob) {
      return;
    }

    try {

      const response =
        await fetch(
          `/api/download/${activeDownloadJob}/resume`,
          {
            method: "POST"
          }
        );

      const data =
        await response.json();

      if (
        !response.ok ||
        !data.ok
      ) {

        throw new Error(
          data.error ||
          "Could not resume download."
        );
      }

      setStatus(
        "Resuming download...",
        "success"
      );

      pollDownloadStatus();

    } catch (error) {

      setStatus(
        error.message ||
        "Could not resume download.",
        "error"
      );
    }
  }
);


// ==========================================================
// CANCEL
// ==========================================================

$("#cancelDownloadBtn")?.addEventListener(
  "click",
  async () => {

    if (!activeDownloadJob) {
      return;
    }

    try {

      const response =
        await fetch(
          `/api/download/${activeDownloadJob}/cancel`,
          {
            method: "POST"
          }
        );

      const data =
        await response.json();

      if (
        !response.ok ||
        !data.ok
      ) {

        throw new Error(
          data.error ||
          "Could not cancel download."
        );
      }

      stopProgressPolling();

      setStatus(
        "Download cancelled.",
        "error"
      );

      const downloadButton =
        $("#downloadBtn");

      if (downloadButton) {

        setButtonLoading(
          downloadButton,
          false,
          "Preparing...",
          `Download ${
            selectedMode === "audio"
              ? "MP3"
              : "MP4"
          } ↗`
        );
      }

    } catch (error) {

      setStatus(
        error.message ||
        "Could not cancel download.",
        "error"
      );
    }
  }
);


// ==========================================================
// NETWORK STATUS
// ==========================================================

window.addEventListener(
  "offline",
  () => {

    if (activeDownloadJob) {

      const network =
        $("#downloadNetwork");

      if (network) {

        network.hidden = false;

        network.textContent =
          "⚠ Internet connection lost.";
      }

      setStatus(
        "Internet connection lost.",
        "error"
      );
    }
  }
);


window.addEventListener(
  "online",
  () => {

    if (activeDownloadJob) {

      const network =
        $("#downloadNetwork");

      if (network) {

        network.hidden = false;

        network.textContent =
          "Connection restored. Checking download...";
      }

      setStatus(
        "Internet connection restored.",
        "success"
      );

      pollDownloadStatus();
    }
  }
);

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