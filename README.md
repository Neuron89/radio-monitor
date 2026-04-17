# Radio Monitor

RTL-SDR based radio traffic monitor with real-time speech-to-text and keyword alerting. Listens to UHF/VHF radio traffic, transcribes it using Whisper, and alerts you when your name or configured keywords are detected.

Built for monitoring Motorola RMU2040 UHF business radios, but works with any FM radio frequency.

## How It Works

```
RTL-SDR → rtl_fm (demodulate) → Voice Activity Detection → Whisper (speech-to-text) → Keyword Match → Alert
```

- Continuously monitors a configured radio frequency
- Detects when someone is transmitting (voice activity detection)
- Transcribes speech in real-time using faster-whisper
- Fuzzy-matches against configured keywords (handles Whisper mishearing names)
- Sends alerts via ntfy push notifications
- Web dashboard shows live transcript feed

## Features

- **Real-time transcription** — ~1-3 second latency from radio TX to text
- **Fuzzy keyword matching** — catches "Gunter" → "Hunter", "Hester" → "Nester"
- **ntfy notifications** — push alerts to any device (phone, desktop, browser)
- **Web dashboard** — live transcript, alert history, transmission counter
- **Browser notifications** — desktop pop-ups from the web UI
- **Test modes** — test with microphone or WAV files (no SDR needed)
- **Configurable** — frequency, keywords, sensitivity, alert methods all in YAML

## Requirements

- **Hardware**: RTL-SDR USB dongle (RTL2832U based)
- **Software**: Python 3.10+, rtl-sdr drivers
- **Optional**: HackRF or SDR++ for frequency identification

## Quick Start

### Install

```bash
git clone https://github.com/Neuron89/radio-monitor.git
cd radio-monitor
sudo bash install.sh
```

### Configure

```bash
nano /opt/radio-monitor/config.yaml
```

Key settings:
- `radio.frequency` — your radio frequency in Hz (find with HackRF)
- `keywords` — names/words to alert on
- `alerts.ntfy.topic` — unique ntfy topic name

### Test with Microphone

```bash
/opt/radio-monitor/venv/bin/python -m radio_monitor \
  -c /opt/radio-monitor/config.yaml --test-mic
```

Open `http://localhost:5555` to see the web dashboard. Say your keywords into the mic to test alerts.

### Run with RTL-SDR

```bash
/opt/radio-monitor/venv/bin/python -m radio_monitor \
  -c /opt/radio-monitor/config.yaml
```

### Run as Service

```bash
sudo systemctl enable --now radio-monitor
```

## Test Modes

| Mode | Command | Use Case |
|------|---------|----------|
| RTL-SDR (live) | `python -m radio_monitor` | Production use |
| Microphone | `python -m radio_monitor --test-mic` | Test without SDR hardware |
| WAV file | `python -m radio_monitor --test-file recording.wav` | Test with recorded audio |

## Alerts

### ntfy (Recommended)

1. Go to [ntfy.sh](https://ntfy.sh) (or self-host)
2. Subscribe to your topic on your phone/desktop
3. Set the topic in `config.yaml`
4. Alerts appear as push notifications

### Browser Notifications

The web dashboard at `http://HOST:5555` requests notification permission. When a keyword is detected, you get a browser notification even if the tab is in the background.

### Webhook

Configure `alerts.webhook.url` in config.yaml to POST JSON alerts to any endpoint (Home Assistant, Slack, Discord, etc.).

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│  RTL-SDR    │────▶│  rtl_fm  │────▶│  Audio VAD  │
│  (antenna)  │     │  (NFM)   │     │  (energy)   │
└─────────────┘     └──────────┘     └──────┬──────┘
                                            │ voice segments
                                     ┌──────▼──────┐
                                     │   Whisper   │
                                     │  (STT)      │
                                     └──────┬──────┘
                                            │ text
                                     ┌──────▼──────┐
                              ┌──────│  Keyword    │──────┐
                              │      │  Matcher    │      │
                              │      └─────────────┘      │
                        ┌─────▼─────┐              ┌──────▼──────┐
                        │   ntfy    │              │  Web UI     │
                        │  (alert)  │              │  (dashboard)│
                        └───────────┘              └─────────────┘
```

## Configuration Reference

See `config.yaml` for all options with comments.

## License

MIT
