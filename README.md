# Radio Monitor

Keyword alerting for two-way radio traffic. Radio Monitor demodulates an FM
voice channel with an RTL-SDR dongle, transcribes each transmission with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), and sends a push
notification when a configured name or keyword is heard.

It was built for someone who needs to know when they are being called on a
site's UHF business radios without carrying a handset, and works with any
narrowband FM voice channel `rtl_fm` can tune.

## Features

- **Live capture** from an RTL-SDR via `rtl_fm`, with energy-based voice
  activity detection that splits the stream into individual transmissions.
- **Speech-to-text on CPU** using faster-whisper (model size and compute type
  are configurable).
- **Fuzzy keyword matching** with RapidFuzz, so near-misses in the transcript
  (for example "Morgen" for "Morgan") still trigger.
- **Alerts** through [ntfy](https://ntfy.sh) push notifications, a JSON
  webhook, and/or a local sound, with a 10-second cooldown between alerts.
- **Web dashboard** with a live transcript feed over Server-Sent Events, an
  alert list, a transmission counter, and browser notifications.
- **Test modes** that replace the SDR with a microphone or a WAV file, so the
  pipeline can be exercised without radio hardware.
- **Rolling transcript log** written to disk.

## How it works

```
RTL-SDR --> rtl_fm (FM demod, 16 kHz PCM) --> voice activity detection
                                                      |
                                              voice segments
                                                      v
                                           faster-whisper (STT)
                                                      |
                                                    text
                                                      v
                                              keyword matcher
                                               /            \
                               ntfy / webhook / sound     web dashboard (SSE)
```

| Stage | Module | Notes |
|---|---|---|
| Audio capture | `radio_monitor/audio.py` | Runs `rtl_fm` as a subprocess; RMS threshold VAD on 100 ms frames; a segment ends after `silence_timeout` seconds of silence or at `max_buffer` seconds |
| Transcription | `radio_monitor/transcriber.py` | faster-whisper on CPU with its built-in VAD filter |
| Matching | `radio_monitor/matcher.py` | Case-insensitive substring match first, then fuzzy match per word (and per word pair for two-word keywords) |
| Alerting | `radio_monitor/alerter.py` | ntfy, webhook, local sound (`aplay` / `paplay`) |
| Dashboard | `radio_monitor/web.py` | Flask app: `/` dashboard, `/events` SSE stream, `/history` last 200 entries as JSON |
| Orchestration | `radio_monitor/main.py` | CLI, config loading, pipeline loop |

## Requirements

- RTL-SDR USB dongle (RTL2832U-based) and an antenna suited to the band
- Linux with the `rtl-sdr` package (provides `rtl_fm`)
- Python 3.10 or newer
- `libportaudio2` for the microphone test mode

The frequency of the channel must be known in advance; an SDR receiver
application such as SDR++ or GQRX can be used to find it.

## Installation

The install script targets Debian/Ubuntu. It installs system packages, copies
the application to `/opt/radio-monitor`, creates a virtual environment there,
and installs a systemd unit.

```bash
git clone https://github.com/Neuron89/radio-monitor.git
cd radio-monitor
sudo bash install.sh
```

For a manual or development setup:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m radio_monitor -c config.yaml --test-mic
```

The default `logging.transcript_file` points at `/var/log/radio-monitor/`;
change it to a writable path when running unprivileged.

## Configuration

All settings live in `config.yaml` (installed to `/opt/radio-monitor/config.yaml`).
The file is commented; the settings that usually need changing are:

| Key | Default | Purpose |
|---|---|---|
| `radio.frequency` | `462562500` (example) | Channel frequency in Hz |
| `radio.squelch`, `radio.gain` | `50`, `40` | Passed to `rtl_fm` |
| `radio.device_index` | `0` | Which RTL-SDR to use |
| `whisper.model` | `base` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `whisper.compute_type` | `int8` | faster-whisper compute type |
| `keywords` | sample list | Names or words to alert on |
| `match_threshold` | `70` | Fuzzy score (0-100) required for a match |
| `audio.vad_threshold` | `0.02` | RMS level treated as voice; raise it if static triggers transcription |
| `audio.silence_timeout` | `1.5` | Seconds of silence that end a transmission |
| `alerts.ntfy.server`, `alerts.ntfy.topic` | `https://ntfy.sh`, `radio-monitor-CHANGEME` | Where push alerts are published |
| `alerts.webhook.url` | empty | Endpoint for JSON alerts |
| `alerts.sound.file` | `/opt/radio-monitor/alert.wav` | WAV played on alert |
| `web.host`, `web.port` | `0.0.0.0`, `5555` | Dashboard bind address |
| `logging.transcript_file` | `/var/log/radio-monitor/transcript.log` | Application and transcript log |

Keyword matching notes:

- Exact matching is a substring test, so very short keywords match inside
  other words. Prefer distinctive names and words.
- Lowering `match_threshold` catches more mis-transcriptions at the cost of
  more false alerts.

## Usage

| Mode | Command | Use case |
|---|---|---|
| Live (RTL-SDR) | `python -m radio_monitor -c config.yaml` | Normal operation |
| Microphone | `python -m radio_monitor -c config.yaml --test-mic` | Test without SDR hardware |
| WAV file | `python -m radio_monitor -c config.yaml --test-file recording.wav` | Replay recorded audio (16-bit PCM WAV) |

Additional flags: `--no-web` disables the dashboard, `-v` enables debug logging.

With the installed copy, use the virtual environment's interpreter:

```bash
/opt/radio-monitor/venv/bin/python -m radio_monitor \
  -c /opt/radio-monitor/config.yaml --test-mic
```

Then open `http://<host>:5555` and speak a keyword to confirm an alert fires.

### Running as a service

```bash
sudo systemctl enable --now radio-monitor
journalctl -u radio-monitor -f
```

### Alerts

- **ntfy**: choose a unique topic name, subscribe to it in the ntfy app or web
  UI, and set `alerts.ntfy.topic`. Anyone who knows a topic on the public
  ntfy.sh server can read it, so use an unguessable name or a self-hosted server.
- **Webhook**: set `alerts.webhook.enabled: true` and a `url`. Each alert is a
  POST with JSON fields `title`, `body`, `transcript`, `matches`, `timestamp`.
- **Browser**: the dashboard asks for notification permission and raises a
  desktop notification on each alert while the page is open.
- **Sound**: set `alerts.sound.enabled: true` and point `file` at a WAV.

## Limitations

- Analog FM voice only. Digital modes (DMR, P25, NXDN) and encrypted or
  trunked systems are not decoded.
- One frequency per process.
- Transcription runs on CPU; latency depends on the model size and the host.
- The dashboard has no authentication and binds to all interfaces by default.
  Keep it on a trusted network or set `web.host` to `127.0.0.1`.
- The systemd unit runs the service as root.
- There is no automated test suite; use the microphone and WAV modes to verify
  a setup.

## Legal and responsible use

Monitoring radio communications is regulated, and the rules differ by country
and by service. Only monitor channels you are licensed or otherwise authorised
to receive, such as your own organisation's radio system, and do not record,
disclose, or act on communications where the law prohibits it. Transcripts are
stored in plain text; treat the log file and dashboard accordingly.

## License

MIT. See [LICENSE](LICENSE).
