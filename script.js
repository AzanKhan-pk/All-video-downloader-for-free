const $ = (selector) => document.querySelector(selector);

const urlInput = $("#url");
const fetchButton = $("#fetchBtn");
const statusBox = $("#status");
const resultBox = $("#result");

let selectedMode = "video";
let selectedQuality = "720p";
let currentVideo = null;

let activeDownloadJob = null;
let progressTimer = null;


// ==========================================================
// BASIC UI
// ==========================================================

function setStatus(message, type = "") {
  if (!statusBox) return;

  statusBox.textContent = message;
  statusBox.className = `status ${type}`.trim();
}


function setButtonLoading(button, loading, loadingText, normalText) {
  if (!button) return;

  button.disabled = loading;
  button.textContent = loading ? loadingText : normalText;
}


function escapeHtml(value) {
  return String(value).replace(
    /[&<>'"]/g,
    (character) => {
      const entities = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;"
      };

      return entities[character];
    }
  );
}


// ==========================================================
// IOS DETECTION
// ==========================================================

function isIOSDevice() {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (
      navigator.platform === "MacIntel" &&
      navigator.maxTouchPoints > 1
    )
  );
}


// ==========================================================
// DOWNLOAD FILE
// ==========================================================

async function downloadFileForAllDevices(url, filename) {
  try {
    /*
     * iPhone/iPad Safari has different download behaviour.
     *
     * We let Safari handle the generated file directly.
     * This avoids relying on the HTML download attribute,
     * which Safari does not always handle like desktop browsers.
     */

    if (isIOSDevice()) {
      setStatus(
        "Your file is ready. Safari is opening the download...",
        "success"
      );

      window.location.href = url;
      return;
    }


    /*
     * Desktop / Android browsers:
     * Try normal browser download first.
     */

    const link = document.createElement("a");

    link.href = url;
    link.download = filename;
    link.rel = "noopener";
    link.style.display = "none";

    document.body.appendChild(link);

    link.click();

    link.remove();

  } catch (error) {

    console.error(
      "File download error:",
      error
    );

    /*
     * Final fallback:
     * Open the file directly.
     */

    window.location.href = url;
  }
}


// ==========================================================
// QUALITY LABEL
// ==========================================================

function updateQualityLabel() {
  const qualityLabel = $("#qualityLabel");

  if (!qualityLabel) return;

  if (selectedMode === "audio") {
    qualityLabel.textContent =
      "192 kbps high quality";

    return;
  }

  qualityLabel.textContent =
    selectedQuality === "720p"
      ? "720p recommended"
      : selectedQuality;
}


// ==========================================================
// VIDEO RESULT
// ==========================================================

function renderVideoResult(video) {

  if (!resultBox) return;

  const thumbnail = video.thumbnail
    ? `
      <img
        src="${escapeHtml(video.thumbnail)}"
        alt="Video thumbnail"
      >
    `
    : `
      <div class="result-placeholder">
        AVD
      </div>
    `;

  resultBox.innerHTML = `
    ${thumbnail}

    <div>
      <h3>
        ${escapeHtml(video.title || "Video")}
      </h3>

      <p>
        ${escapeHtml(video.creator || "Unknown")}
        ·
        ${escapeHtml(video.duration || "Unknown")}
        ·
        ${escapeHtml(video.views || "0")} views
      </p>

      <p>
        ${escapeHtml(video.platform || "Unknown")}
      </p>

      <button
        id="downloadBtn"
        type="button"
      >
        Download ${
          selectedMode === "audio"
            ? "MP3"
            : "MP4"
        } ↗
      </button>
    </div>
  `;

  resultBox.hidden = false;

  const downloadButton =
    $("#downloadBtn");

  if (downloadButton) {
    downloadButton.addEventListener(
      "click",
      downloadMedia
    );
  }
}


// ==========================================================
// MODE BUTTONS
// ==========================================================

document
  .querySelectorAll(".mode")
  .forEach((button) => {

    button.addEventListener(
      "click",
      () => {

        document
          .querySelectorAll(".mode")
          .forEach((item) => {
            item.classList.remove("active");
          });

        button.classList.add("active");

        selectedMode =
          button.dataset.mode || "video";

        updateQualityLabel();

        if (
          currentVideo &&
          resultBox &&
          !resultBox.hidden
        ) {
          renderVideoResult(currentVideo);
        }
      }
    );
  });


// ==========================================================
// QUALITY BUTTONS
// ==========================================================

document
  .querySelectorAll(".quality-grid button")
  .forEach((button) => {

    button.addEventListener(
      "click",
      () => {

        document
          .querySelectorAll(
            ".quality-grid button"
          )
          .forEach((item) => {
            item.classList.remove("selected");
          });

        button.classList.add("selected");

        selectedQuality =
          button.dataset.quality || "720p";

        updateQualityLabel();
      }
    );
  });


// ==========================================================
// FETCH MEDIA INFO
// ==========================================================

if (fetchButton) {

  fetchButton.addEventListener(
    "click",
    async () => {

      const url =
        urlInput
          ? urlInput.value.trim()
          : "";

      if (!url) {

        setStatus(
          "Paste a public video URL first.",
          "error"
        );

        if (urlInput) {
          urlInput.focus();
        }

        return;
      }

      setButtonLoading(
        fetchButton,
        true,
        "Reading...",
        "Fetch media ↗"
      );

      setStatus(
        "Reading public media details..."
      );

      if (resultBox) {
        resultBox.hidden = true;
      }

      currentVideo = null;

      try {

        const response =
          await fetch(
            "/api/info",
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body: JSON.stringify({
                url
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
            "Could not read this link."
          );
        }

        currentVideo =
          data.video;

        renderVideoResult(
          currentVideo
        );

        setStatus(
          `${
            currentVideo.platform ||
            "Media"
          } media found.`,
          "success"
        );

      } catch (error) {

        console.error(
          "Fetch media error:",
          error
        );

        if (resultBox) {
          resultBox.hidden = true;
        }

        setStatus(
          error.message ||
          "Something went wrong.",
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
    }
  );
}


// ==========================================================
// FORMAT BYTES
// ==========================================================

function formatBytes(bytes) {

  bytes = Number(bytes || 0);

  if (
    !Number.isFinite(bytes) ||
    bytes <= 0
  ) {
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
      Math.log(bytes) /
      Math.log(1024)
    ),
    units.length - 1
  );

  const value =
    bytes /
    Math.pow(1024, index);

  return `${value.toFixed(
    index === 0 ? 0 : 2
  )} ${units[index]}`;
}


// ==========================================================
// FORMAT SPEED
// ==========================================================

function formatSpeed(bytesPerSecond) {

  bytesPerSecond =
    Number(bytesPerSecond || 0);

  if (
    !Number.isFinite(
      bytesPerSecond
    ) ||
    bytesPerSecond <= 0
  ) {
    return "Speed —";
  }

  return `${formatBytes(
    bytesPerSecond
  )}/s`;
}


// ==========================================================
// FORMAT ETA
// ==========================================================

function formatEta(seconds) {

  if (
    seconds === null ||
    seconds === undefined
  ) {
    return "ETA —";
  }

  seconds = Number(seconds);

  if (
    !Number.isFinite(seconds) ||
    seconds < 0
  ) {
    return "ETA —";
  }

  seconds =
    Math.round(seconds);

  const hours =
    Math.floor(
      seconds / 3600
    );

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


// ==========================================================
// SHOW DOWNLOAD PANEL
// ==========================================================

function showDownloadProgress() {

  const box =
    $("#downloadProgress");

  if (box) {
    box.hidden = false;
  }
}


// ==========================================================
// UPDATE DOWNLOAD PROGRESS
// ==========================================================

function updateDownloadProgress(job) {

  if (!job) return;

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

  const cancelButton =
    $("#cancelDownloadBtn");

  if (!title) {
    return;
  }

  let safePercent =
    Number(job.percent || 0);

  if (
    !Number.isFinite(
      safePercent
    )
  ) {
    safePercent = 0;
  }

  safePercent =
    Math.min(
      100,
      Math.max(
        0,
        safePercent
      )
    );

  title.textContent =
    job.title ||
    "Preparing download...";

  if (percent) {
    percent.textContent =
      `${safePercent.toFixed(0)}%`;
  }

  if (bar) {

    bar.style.width =
      `${safePercent}%`;

    bar.style.transition =
      "width 0.7s ease";
  }

  const downloaded =
    formatBytes(
      job.downloaded_bytes || 0
    );

  const total =
    job.total_bytes
      ? formatBytes(
          job.total_bytes
        )
      : "—";

  if (amount) {
    amount.textContent =
      `${downloaded} / ${total}`;
  }

  if (speed) {
    speed.textContent =
      formatSpeed(
        job.speed || 0
      );
  }

  if (eta) {
    eta.textContent =
      formatEta(job.eta);
  }


  // ========================================================
  // NETWORK ERROR
  // ========================================================

  if (
    job.status ===
    "network_error"
  ) {

    if (network) {

      network.hidden = false;

      network.textContent =
        job.error ||
        "⚠ Network issue — press Resume when connection is back.";
    }

    if (pauseButton) {
      pauseButton.hidden = true;
    }

    if (resumeButton) {
      resumeButton.hidden = false;
    }

    if (cancelButton) {
      cancelButton.hidden = false;
    }

    return;
  }


  // ========================================================
  // PAUSED
  // ========================================================

  if (
    job.status === "paused"
  ) {

    if (network) {

      network.hidden = false;

      network.textContent =
        "Download paused.";
    }

    if (pauseButton) {
      pauseButton.hidden = true;
    }

    if (resumeButton) {
      resumeButton.hidden = false;
    }

    if (cancelButton) {
      cancelButton.hidden = false;
    }

    return;
  }


  // ========================================================
  // NORMAL DOWNLOADING
  // ========================================================

  if (network) {
    network.hidden = true;
  }

  if (pauseButton) {

    pauseButton.hidden =
      ![
        "starting",
        "preparing",
        "downloading",
        "processing"
      ].includes(
        job.status
      );
  }

  if (resumeButton) {
    resumeButton.hidden = true;
  }

  if (cancelButton) {

    cancelButton.hidden =
      ![
        "starting",
        "preparing",
        "downloading",
        "processing",
        "paused",
        "network_error"
      ].includes(
        job.status
      );
  }


  // ========================================================
  // COMPLETED
  // ========================================================

  if (
    job.status === "completed"
  ) {

    title.textContent =
      "Download complete";

    if (percent) {
      percent.textContent =
        "100%";
    }

    if (bar) {
      bar.style.width =
        "100%";
    }

    if (speed) {
      speed.textContent =
        "Complete";
    }

    if (eta) {
      eta.textContent =
        "Ready";
    }

    if (network) {
      network.hidden = true;
    }

    if (pauseButton) {
      pauseButton.hidden = true;
    }

    if (resumeButton) {
      resumeButton.hidden = true;
    }

    if (cancelButton) {
      cancelButton.hidden = true;
    }
  }
}


// ==========================================================
// GET DOWNLOAD STATUS
// ==========================================================

async function getDownloadStatus() {

  if (!activeDownloadJob) {
    return null;
  }

  const response =
    await fetch(
      `/api/download/${activeDownloadJob}/status`,
      {
        method: "GET",
        cache: "no-store",
        credentials: "same-origin"
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


// ==========================================================
// STOP POLLING
// ==========================================================

function stopProgressPolling() {

  if (progressTimer) {

    clearTimeout(
      progressTimer
    );

    progressTimer = null;
  }
}


// ==========================================================
// DOWNLOAD STATUS POLLING
// ==========================================================

async function pollDownloadStatus() {

  stopProgressPolling();

  if (!activeDownloadJob) {
    return;
  }

  try {

    const job =
      await getDownloadStatus();

    if (!job) {
      return;
    }

    updateDownloadProgress(job);


    // ======================================================
    // COMPLETED
    // ======================================================

    if (
      job.status ===
      "completed"
    ) {

      stopProgressPolling();

      const fileUrl =
        `/api/download/${activeDownloadJob}/file`;

      const filename =
        selectedMode === "audio"
          ? "vidloom-audio.mp3"
          : "vidloom-video.mp4";


      /*
       * iPhone / iPad
       *
       * Safari handles the generated file directly.
       * The server must return it with Content-Disposition:
       * attachment.
       */

      if (isIOSDevice()) {

        setStatus(
          "Your file is ready. Opening Safari download...",
          "success"
        );

        window.location.href =
          fileUrl;

      } else {

        /*
         * Android / Windows / macOS
         */

        const link =
          document.createElement("a");

        link.href =
          fileUrl;

        link.download =
          filename;

        link.rel =
          "noopener";

        link.style.display =
          "none";

        document.body.appendChild(
          link
        );

        link.click();

        link.remove();

        setStatus(
          "Your download is ready.",
          "success"
        );
      }


      // Reset download button

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


    // ======================================================
    // CANCELLED
    // ======================================================

    if (
      job.status ===
      "cancelled"
    ) {

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

      activeDownloadJob =
        null;

      return;
    }


    // ======================================================
    // ERROR
    // ======================================================

    if (
      job.status === "error"
    ) {

      stopProgressPolling();

      setStatus(
        job.error ||
        "Download failed.",
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

      return;
    }


    // ======================================================
    // KEEP POLLING
    // ======================================================

    progressTimer =
      setTimeout(
        pollDownloadStatus,
        700
      );

  } catch (error) {

    console.error(
      "Download status error:",
      error
    );

    progressTimer =
      setTimeout(
        pollDownloadStatus,
        1500
      );
  }
}


// ==========================================================
// START DOWNLOAD
// ==========================================================

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
            url:
              currentVideo.url ||
              (urlInput
                ? urlInput.value.trim()
                : ""),

            mode:
              selectedMode,

            quality:
              selectedQuality
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

    console.error(
      "Download error:",
      error
    );

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

const pauseDownloadButton =
  $("#pauseDownloadBtn");

if (pauseDownloadButton) {

  pauseDownloadButton.addEventListener(
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

        console.error(
          "Pause error:",
          error
        );

        setStatus(
          error.message ||
          "Could not pause download.",
          "error"
        );
      }
    }
  );
}


// ==========================================================
// RESUME
// ==========================================================

const resumeDownloadButton =
  $("#resumeDownloadBtn");

if (resumeDownloadButton) {

  resumeDownloadButton.addEventListener(
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

        console.error(
          "Resume error:",
          error
        );

        setStatus(
          error.message ||
          "Could not resume download.",
          "error"
        );
      }
    }
  );
}


// ==========================================================
// CANCEL
// ==========================================================

const cancelDownloadButton =
  $("#cancelDownloadBtn");

if (cancelDownloadButton) {

  cancelDownloadButton.addEventListener(
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

        activeDownloadJob =
          null;

      } catch (error) {

        console.error(
          "Cancel error:",
          error
        );

        setStatus(
          error.message ||
          "Could not cancel download.",
          "error"
        );
      }
    }
  );
}


// ==========================================================
// NETWORK STATUS
// ==========================================================

window.addEventListener(
  "offline",
  () => {

    if (!activeDownloadJob) {
      return;
    }

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
);


window.addEventListener(
  "online",
  () => {

    if (!activeDownloadJob) {
      return;
    }

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
);


// ==========================================================
// COMMENTS
// ==========================================================

const commentForm =
  $("#commentForm");

if (commentForm) {

  commentForm.addEventListener(
    "submit",
    async (event) => {

      event.preventDefault();

      const form =
        event.currentTarget;

      const submitButton =
        form.querySelector("button");

      const commentStatus =
        $("#commentStatus");

      const nameInput =
        $("#name");

      const commentInput =
        $("#comment");

      const name =
        nameInput
          ? nameInput.value.trim()
          : "";

      const comment =
        commentInput
          ? commentInput.value.trim()
          : "";

      if (!name || !comment) {

        if (commentStatus) {

          commentStatus.textContent =
            "Please complete both fields.";

          commentStatus.className =
            "status error";
        }

        return;
      }

      if (submitButton) {

        submitButton.disabled = true;

        submitButton.textContent =
          "Saving...";
      }

      if (commentStatus) {

        commentStatus.textContent =
          "Saving your note...";

        commentStatus.className =
          "status";
      }

      try {

        const response =
          await fetch(
            "/api/comments",
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              body: JSON.stringify({
                name,
                comment
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
            "Could not save your feedback."
          );
        }

        if (commentStatus) {

          commentStatus.textContent =
            data.message ||
            "Thanks, your feedback is saved.";

          commentStatus.className =
            "status success";
        }

        form.reset();

      } catch (error) {

        if (commentStatus) {

          commentStatus.textContent =
            error.message ||
            "Could not save your feedback.";

          commentStatus.className =
            "status error";
        }

      } finally {

        if (submitButton) {

          submitButton.disabled = false;

          submitButton.innerHTML =
            "Send feedback <span>↗</span>";
        }
      }
    }
  );
}


// ==========================================================
// REVEAL ANIMATION
// ==========================================================

if (
  "IntersectionObserver" in window
) {

  const revealObserver =
    new IntersectionObserver(
      (entries) => {

        entries.forEach(
          (entry) => {

            if (
              entry.isIntersecting
            ) {

              entry.target.classList.add(
                "visible"
              );

              revealObserver.unobserve(
                entry.target
              );
            }
          }
        );
      },
      {
        threshold: 0.12
      }
    );

  document
    .querySelectorAll(".reveal")
    .forEach(
      (element, index) => {

        element.style.transitionDelay =
          `${Math.min(
            index * 45,
            260
          )}ms`;

        revealObserver.observe(
          element
        );
      }
    );
}


// ==========================================================
// ENTER KEY
// ==========================================================

if (urlInput && fetchButton) {

  urlInput.addEventListener(
    "keydown",
    (event) => {

      if (event.key === "Enter") {

        event.preventDefault();

        fetchButton.click();
      }
    }
  );
}


// ==========================================================
// INITIAL STATE
// ==========================================================

updateQualityLabel();
