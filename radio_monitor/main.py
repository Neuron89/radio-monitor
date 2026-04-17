"""Main entry point — orchestrates the radio monitor pipeline."""
import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

import yaml

from .audio import AudioCapture, MicCapture, FileCapture
from .transcriber import Transcriber
from .matcher import KeywordMatcher
from .alerter import Alerter
from . import web


def setup_logging(config: dict):
    log_dir = Path(config["logging"]["transcript_file"]).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config["logging"]["transcript_file"]),
        ],
    )


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_pipeline(capture, transcriber, matcher, alerter, config):
    """Main processing loop — reads audio segments and processes them."""
    log = logging.getLogger("pipeline")
    log.info("Pipeline running. Waiting for radio traffic...")

    web.push_event("status", {"message": "Listening"})

    while True:
        try:
            audio = capture.audio_queue.get(timeout=1)
        except Exception:
            continue

        text = transcriber.transcribe(audio)
        if not text:
            continue

        log.info(f"[TX] {text}")
        web.push_event("transcript", {"text": text})

        # Log to transcript file
        transcript_file = config["logging"]["transcript_file"]
        with open(transcript_file, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {text}\n")

        matches = matcher.check(text)
        if matches:
            alerter.send(text, matches)
            web.push_event("alert", {"text": text, "matches": matches})


def main():
    parser = argparse.ArgumentParser(description="Radio Monitor — RTL-SDR keyword alerting")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--test-mic", action="store_true", help="Use system microphone instead of RTL-SDR")
    parser.add_argument("--test-file", type=str, help="Process a WAV file instead of live radio")
    parser.add_argument("--no-web", action="store_true", help="Disable web dashboard")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log = logging.getLogger("main")
    log.info("Radio Monitor starting...")
    log.info(f"Keywords: {config['keywords']}")

    # Initialize components
    transcriber = Transcriber(config)
    transcriber.load()

    matcher = KeywordMatcher(config)
    alerter = Alerter(config)

    # Choose audio source
    if args.test_file:
        log.info(f"Test mode: processing file {args.test_file}")
        capture = FileCapture(config, args.test_file)
    elif args.test_mic:
        log.info("Test mode: using system microphone")
        capture = MicCapture(config)
    else:
        log.info(f"Live mode: RTL-SDR @ {config['radio']['frequency'] / 1e6:.4f} MHz")
        capture = AudioCapture(config)

    # Start web dashboard
    if not args.no_web and config["web"]["enabled"]:
        flask_app = web.create_app(config)
        web_thread = threading.Thread(
            target=lambda: flask_app.run(
                host=config["web"]["host"],
                port=config["web"]["port"],
                threaded=True,
                use_reloader=False,
            ),
            daemon=True,
        )
        web_thread.start()
        log.info(f"Web dashboard: http://{config['web']['host']}:{config['web']['port']}")

    # Start audio capture
    capture.start()

    # Run pipeline
    try:
        run_pipeline(capture, transcriber, matcher, alerter, config)
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        capture.stop()


if __name__ == "__main__":
    main()
