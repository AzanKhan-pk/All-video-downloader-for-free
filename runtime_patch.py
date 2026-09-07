"""Runtime fixes for the VidLoom downloader UI.

Keeps the original Flask/yt-dlp pipeline intact while making progress speed
come from measured downloaded bytes and elapsed time rather than a fabricated
number. The final reported speed is the measured average transfer speed.
"""
import time


def install(core):
    original_progress_hook = core.progress_hook

    def measured_progress_hook(job_id):
        base_hook = original_progress_hook(job_id)
        started = {"t": None, "bytes": 0}

        def hook(data):
            status = data.get("status")

            # Let the original hook handle pause/cancel and byte totals first.
            base_hook(data)

            if status == "downloading":
                now = time.monotonic()
                downloaded = int(data.get("downloaded_bytes") or 0)
                if started["t"] is None:
                    started["t"] = now
                    started["bytes"] = downloaded
                    return

                elapsed = now - started["t"]
                if elapsed > 0.15:
                    measured = max(0.0, (downloaded - started["bytes"]) / elapsed)
                    # This value is calculated from actual bytes received by
                    # yt-dlp and elapsed monotonic time: bytes per second.
                    core.update_job(job_id, speed=measured)

            elif status == "finished":
                job = core.get_job(job_id) or {}
                downloaded = int(
                    data.get("downloaded_bytes")
                    or job.get("downloaded_bytes")
                    or 0
                )
                elapsed = (time.monotonic() - started["t"]) if started["t"] else 0
                average = (downloaded / elapsed) if elapsed > 0 else 0.0
                core.update_job(job_id, average_speed=average, speed=average)

        return hook

    core.progress_hook = measured_progress_hook

    original_run = core.run_download_job

    def measured_run(job_id):
        core.update_job(job_id, transfer_started_at=time.monotonic())
        original_run(job_id)
        job = core.get_job(job_id) or {}
        if job.get("status") == "completed":
            started = float(job.get("transfer_started_at") or 0)
            elapsed = time.monotonic() - started if started else 0
            size = int(job.get("downloaded_bytes") or 0)
            average = (size / elapsed) if elapsed > 0 else 0.0
            core.update_job(job_id, average_speed=average, speed=average)

    core.run_download_job = measured_run
