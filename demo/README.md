# Sensitive Data Protection demo

This package creates a repeatable three-to-four-minute customer demo of the deployed Sensitive Data Protection app. It uses only the approved synthetic fixtures in `..\samples\input`, automates the deployed UI with local Playwright, generates Australian-English narration with Azure AI Speech, and produces a captioned MP4 plus reusable screenshots.

## Prerequisites

- Windows PowerShell 7 or Windows PowerShell 5.1
- The repository `.venv` created from the project dependencies
- Node.js and npm
- FFmpeg and `ffprobe` available on `PATH`, or the project-local npm packages installed with `npm ci`
- The existing `rai-private` azd environment under `..\infra\private`
- Azure CLI sign-in and Entra permissions to synthesize speech with the Speech resource
- A local Playwright Chromium installation

Install the project-scoped browser dependency and browser from this directory:

```powershell
npm ci
npx playwright install chromium
```

The project-local `ffmpeg-static` and `ffprobe-static` dependencies provide FFmpeg without system-wide installation.

No Azure keys, connection strings, shared credentials, or custom voice models are used. Speech requests use `DefaultAzureCredential` and the `https://cognitiveservices.azure.com/.default` scope.

## Speech configuration

The infrastructure provisions Azure AI Speech alongside Azure AI Language and exports its non-secret `AZURE_SPEECH_ENDPOINT` and `AZURE_SPEECH_RESOURCE_ID` outputs to the selected azd environment during `azd up`. Azure AI Language is used for PII detection; it cannot synthesize narration. The endpoint must be reachable from the machine running the demo, and the signed-in identity must have the Azure AI Speech User role on the Speech resource. If needed, use the resource ID to scope that role assignment. If the endpoint is absent, the narration command stops and names that missing configuration setting; it does not use another provider.

The application URL is resolved from `AZURE_REDACTION_CHAT_URL` in the same azd environment. The scripts read only those selected variables into memory; environment values are never printed or saved. The application must return `{"status":"healthy"}` at `/healthz`.

## Run the complete demo

From the repository root:

```powershell
.\demo\scripts\generate-demo.ps1
```

Use a one-run URL override without persisting it:

```powershell
.\demo\scripts\generate-demo.ps1 -AppUrl "https://your-app.example.test"
```

Reuse already-generated, script-matched narration clips:

```powershell
.\demo\scripts\generate-demo.ps1 -SkipNarration
```

The full run checks application health before synthesis or recording, waits for the UI's service-ready state, validates successful redaction and privacy checks, then composes and inspects the final media.

## Run individual stages

Generate narration only:

```powershell
.\demo\scripts\generate-demo.ps1 -NarrationOnly
```

This refreshes the voice segments and transcript. The final VTT timing is regenerated after a browser recording, when actual scene start times are known.

Record only the browser experience using previously generated narration:

```powershell
.\demo\scripts\generate-demo.ps1 -RecordOnly
```

Compose existing browser and narration assets:

```powershell
.\demo\scripts\generate-demo.ps1 -ComposeOnly -SkipNarration
```

`-RecordOnly` still resolves and health-checks the app URL. `-ComposeOnly` does not contact Azure or the deployed app. Existing speech assets are accepted only if their manifest matches the committed script and all seven WAV clips pass format and duration checks.

## Outputs

Generated files are placed under `output\`:

- `sensitive-data-protection-demo.mp4` — H.264/AAC presentation-ready video
- `sensitive-data-protection-demo.webm` — original Playwright browser recording
- `sensitive-data-protection-demo.vtt` — WebVTT subtitles aligned to the recorded narration
- `transcript.txt` — exact narration wording from `narration\script.txt`
- `screenshots\` — landing, capability, text, document, image, ecosystem, and responsible-use screenshots
- Local speech segments, the final WAV track, and timing manifests used to reproduce the output

Use `narration\script.txt` as the single source of narration wording. Change the seven paragraphs there to change the spoken script. VTT cues are rebuilt from the measured speech durations and browser scene-start times on every composition; do not edit generated timing files by hand.

## Privacy and responsible use

- Every input is an allow-listed synthetic fixture from `..\samples\input`; the text walkthrough combines the repository's synthetic contact and secrets samples in memory.
- The text field is covered in the recording while the fixture is submitted. The browser never saves Playwright traces or request logs.
- Text output is checked in memory against candidate personal-information and credential patterns from the fixture. If a candidate remains visible, the run fails without saving the recording.
- Documents and images are processed through the UI, but their download buttons are not activated and downloaded content is never opened.
- Only detection counts, review reminders, and available download controls are shown. No original request text, credentials, tokens, or endpoint values are written to logs, screenshots, narration, or metadata.
- The demo does not claim universal detection or compliance. Always review redacted copies before use or sharing.
- Generated media, audio, timing manifests, screenshots, and temporary recordings are ignored by Git.

## Troubleshooting

- **Missing `AZURE_REDACTION_CHAT_URL`:** select the `rai-private` environment in `infra\private`, or pass a temporary `-AppUrl`.
- **Application health check fails:** confirm the deployed app is available and its `/healthz` endpoint returns healthy. The workflow stops before recording.
- **Missing `AZURE_SPEECH_ENDPOINT`:** run `azd up` with the updated infrastructure and select the same azd environment when running the demo. The demo does not discover arbitrary resources or use a third-party speech service.
- **Entra authentication or authorization fails:** sign in with Azure CLI and grant the identity Speech access. No key-based fallback is supported.
- **Chromium is missing:** run `npx playwright install chromium` from this directory.
- **FFmpeg validation fails:** run `npm ci` in `demo`, or install a local FFmpeg build with `ffmpeg` and `ffprobe` on `PATH`; the final file must have one 1920×1080 video stream, one audio stream, and a duration from 195 to 240 seconds.
- **A redaction or privacy check fails:** no final video is composed. Review application availability and the synthetic fixture workflow; do not bypass the check or substitute real content.

## Use in presentation tools

Import `output\sensitive-data-protection-demo.mp4` into Clipchamp or PowerPoint. Keep `output\sensitive-data-protection-demo.vtt` alongside the video for subtitle import or caption workflows supported by the presentation tool. Teams meeting and channel policies vary; share the MP4 and VTT using the organisation's approved file-sharing process.
