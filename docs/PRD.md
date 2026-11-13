# Product Requirements Document

Voice-powered office assistant, MVP

## 1. Scope

We are building a voice assistant that runs on each staff member's Windows PC. The user speaks, and the assistant drafts memos and reports, replies to emails, summarises documents, searches the policy library, opens apps and files, and manages the calendar. Nothing irreversible happens without the user's confirmation.

### In scope

- Voice in and voice out, with push-to-talk and an on-screen transcript
- Memos and short reports as Word files
- Email replies with read-back and confirmation before sending
- Summaries of documents and email threads
- Policy search with cited answers, or an honest "not found"
- Opening apps, finding files, reading and creating calendar events
- An email outbox that works offline and sends when the internet returns
- Speaker recognition for 2 to 3 users

### Out of scope for the MVP

- Replacing Word or Outlook; we drive them, we do not rebuild them
- Languages other than English (Nigerian-accented English only)
- Meeting transcription, call handling and always-on room audio
- Phone app or phone browser client, online web research, OCR, admin console
- The Local profile (on-device language model); it is the later target

## 2. Architecture

There is no dedicated server PC. The product has two parts.

**Desktop app**, installed on each staff PC. It handles the wake word, push-to-talk, voice activity detection, speech-to-text, speaker ID, keyword commands, file search, app launching, the calendar, the policy index, the email outbox and the local database. Audio and files never leave this machine.

**Cloud gateway**, one small hosted service with no GPU. It holds the API key, calls the language model over an API, enforces a spending cap per user and logs usage. It receives only the request text and the few passages or draft excerpts a task needs, and only after the user approves. It never receives audio, the whole library or credentials.

The desktop app talks to Outlook or Gmail and the calendar directly through their APIs using OAuth, so email never passes through the gateway.

### Language model

The model is Gemma 4, called through an API. We do not host or download it for the MVP.

- **Default (Hosted profile):** Gemma 4 26B A4B through the gateway. It is the cheapest and fastest of the large models, and it supports function calling and system prompts natively.
- **Quality step-up:** Gemma 4 31B, if tests show 26B A4B is not accurate enough on summaries or drafts. Same API, one setting.
- **Local profile (later):** Gemma 4 E4B on 16 GB PCs, or E2B on 8 GB PCs, run on the machine with no internet. These RAM figures are estimates and must be tested.
- **Reasoning mode:** off for short commands, on only where a task needs it, to keep replies fast.
- **Provider:** call Google's API or another host of Gemma 4. Compare price, speed and data terms on the same 30 tasks. Choose a provider whose terms exclude training on our data, check the free tier terms separately, and record the choice in DECISIONS.md.

### Profiles

Hosted is the default: the language model runs in the cloud through the gateway and everything else runs on the PC. Local is the later target for offices with weak internet or strict data rules: a small Gemma 4 model runs on the PC and nothing goes to the cloud. The active profile is always visible, and switching is a setting, not a code change.

### What works with no internet

Keyword commands, file search, opening apps, the calendar, policy retrieval (passages are shown without a written answer) and the outbox. Drafting, replies and summaries need the cloud model in the Hosted profile.

### When the gateway is down

The app retries once, then after 8 seconds falls back to keyword commands and retrieved passages, tells the user so, and never waits in silence.

## 3. Functional requirements

Every requirement below ships in the MVP. IDs are for tickets and tests.

### Voice

- **VOX-1** Wake word "HeyAria" runs locally. No audio is stored or sent before the wake word; fewer than 1 false accept per hour in a quiet office.
- **VOX-2** Speech-to-text runs on the PC with no internet. The transcript is on screen within 1.5 seconds of the user finishing.
- **VOX-3** Spoken replies run on the PC. They start within 500 ms and the user can say "stop".
- **VOX-4** Push-to-talk (hotkey and on-screen mic) works when the wake word is unreliable.

### Identity

- **ID-1** Voice enrollment takes about 30 seconds. The speaker embedding is stored locally and encrypted.
- **ID-2** The speaker is identified on every request. A low-confidence match asks "Is this Amina?" before acting.
- **ID-3** Each user has their own settings: documents folder, email signature, default sender, tone.
- **ID-4** Deleting a profile removes its embeddings, history and queued items.
- **ID-5** Voice alone never approves an external send or a delete. The user must see a confirmation.

### Documents, reports and summaries

- **DOC-1** Draft a memo from a spoken brief into a Word file, using a template with letterhead and consistent styles.
- **DOC-2** Save to the user's documents folder with the topic and date in the file name.
- **RPT-1** For a report, propose an outline first. The user approves or edits it by voice.
- **RPT-2** Write the report section by section. The user can redo one section.
- **SUM-1** Summarise a .docx, .pdf or .txt in three modes: one line, five bullets, one page.
- **SUM-2** Summarise an email thread: who asked for what, deadlines and decisions.
- **SUM-3** Summaries contain no fact that is absent from the source. Names, dates and figures match, and sections are cited by page or heading.

### Policy search

- **POL-1** The admin points the app at a policy folder (.docx, .pdf, .txt). Changed files re-index automatically and index status is visible.
- **POL-2** Questions are asked in plain language. Answers are two to four sentences, using only retrieved passages.
- **POL-3** Every answer cites the document, page and date. The passage is shown, and "show me" opens the file at that page.
- **POL-4** When retrieval confidence is low, the app says it found nothing reliable and lists the closest documents.
- **POL-5** Find a document by topic, number or year, with a short list sorted by date.

### Email

- **MAIL-1** Compose by voice. The app reads back recipient, subject and attachments before sending.
- **MAIL-2** Attach files by description. If more than one file fits, ask which.
- **MAIL-3** Offline outbox: messages queue, send automatically on reconnect, and the user is told.
- **REPLY-1** Find a thread by description and confirm sender and subject before going on.
- **REPLY-2** Draft a reply from a spoken instruction, using the thread, the user's tone and signature. Show it and read it back.
- **REPLY-3** Never send automatically. Send only after an explicit yes. Reply-all and external recipients are called out.

### Calendar, files and system

- **CAL-1** "What is on my calendar today?" is answered by voice and on screen from the local calendar.
- **CAL-2** Create, move and cancel events. Conflicts are flagged before saving; cancels need confirmation.
- **SYS-1** Open apps by name or by purpose ("I need to write a letter").
- **SYS-2** Find files by description using filename, recency and a local content index.
- **SYS-3** Safe system actions only: volume, window focus, print. No deleting, installing or changing settings.
- **SYSX-1** An always-visible status shows listening, thinking, working, offline or online.
- **SYSX-2** A plain-language activity log the user can read, with undo where possible.
- **SYSX-3** The user can say "cancel" at any time. Nothing partial is sent or saved without the user knowing.

### Install and deployment

- **DEP-1** A signed installer puts the app and the speech and search models on the PC. Nothing is downloaded at run time and the app starts with the network off.
- **DEP-2** Models load once at start and a test prompt runs before the first request. Ready within 90 seconds of launch.
- **DEP-3** Two profiles, Hosted and Local, chosen by a setting, with the active one always visible.
- **DEP-4** The gateway holds the API key. The key is never in the desktop app.

### Later (P1)

Voice corrections and edits, PDF export, long documents, tone options, OCR, superseded circulars, calendar sync, the Local profile on Gemma 4 E4B or E2B, a phone browser client, up to 10 users, an admin console.

## 4. Planner, router and search rules

The language model never touches the computer directly. It returns a plan, the app validates it against a schema, and only registered tools can run. Invalid output is retried once, then the app asks the user to rephrase. If confidence is below 0.6, the app asks instead of acting. Names, dates and amounts are never guessed; they come from the transcript, contacts or calendar, or the app asks. Anything missing becomes one spoken question at a time.

Each tool has an input schema, an output schema, a risk level (none, local write, external send, destructive), a network need, a timeout and a dry-run mode. The dry-run text is what the app reads back before asking for confirmation. Anything above "none" needs confirmation.

Text from emails, documents and web pages is data, never instructions. It is passed to the model in a marked data block, and nothing inside it can add tools, change recipients or skip confirmation.

The router runs local tasks immediately. For a cloud task it shows exactly what will be sent and waits for approval. If the network is down it tells the user once and queues anything that sends.

The outbox is written to SQLite before any action, so a crash loses nothing. Every item has an idempotency key so a retry never sends the same email twice. States are queued, sending, sent, retrying and failed. Connectivity is checked by reaching a real endpoint, not by reading the OS network flag.

For policy search, documents are split into chunks of 300 to 500 tokens with page and date kept, indexed with keyword and vector search, and the best 5 to 8 passages go to the model. The model answers only from them, cites document and page, says so when they do not answer the question, and flags conflicts between two passages.

## 5. Tech stack

Suggested choices; swap any if testing says otherwise.

- **Desktop app:** Tauri shell around a React or Svelte interface, with a Python 3.11+ service (FastAPI, asyncio, Pydantic) running beside it. Alternative: Electron.
- **Cloud gateway:** Python FastAPI on a small hosted VM or container, with per-install authentication, rate limits and a spending cap. Alternative: a serverless function.
- **Language model:** Gemma 4 26B A4B through an API, behind one adapter interface so the model or provider can change without touching the rest. Local later: Gemma 4 E4B or E2B through Ollama or llama.cpp.
- **Wake word and VAD:** openWakeWord with a custom "HeyAria" model; Silero VAD.
- **Speech-to-text:** faster-whisper, tiny.en or base.en at 8-bit, with a custom vocabulary of staff names and office terms. Gemma 4 E2B and E4B accept audio input; test it, but keep Whisper until a test says otherwise.
- **Speaker ID:** SpeechBrain ECAPA-TDNN embeddings with cosine similarity. Alternatives: pyannote, Resemblyzer.
- **Keyword path and speech output:** rapidfuzz rules for open, find, calendar and cancel, so common commands never wait for a model. Piper for text-to-speech with one English voice.
- **Search:** bge-small or MiniLM embeddings run locally; SQLite FTS5 plus sqlite-vec for hybrid search.
- **Documents:** python-docx with .docx templates; pypdf or pdfplumber for reading PDFs.
- **Email and calendar:** Microsoft Graph and Gmail API with OAuth, a test inbox for development, a local ICS calendar. Fallback: SMTP and IMAP.
- **OS automation:** pywinauto and Windows COM; subprocess launching. Prefer APIs and files over clicking through screens.
- **Storage and queue:** SQLite with SQLCipher for profiles, settings, outbox, logs and indexes; a background worker with exponential backoff for the outbox.
- **Testing:** pytest, recorded audio fixtures, a fake network layer, Playwright.

## 6. Non-functional requirements

**Hardware.** Each staff PC needs Windows 10 or 11, a 4-core CPU (Core i3 8th generation or Ryzen 3), 8 GB of RAM, 10 GB of free disk and no GPU. SSD and 16 GB are recommended. Machines with 2 GB or 4 GB are not supported in the MVP. The Hosted profile uses about 3.5 to 4 GB of RAM including Windows. The gateway needs no GPU.

**Speed.** Models loaded and warmed within 90 seconds of launch. A keyword command answers in under 1 second. A short cloud reply shows its first words in under 3 seconds. A cited policy answer takes under 6 seconds, a two-page summary under 10 seconds, and a 300-word memo shows first text in under 5 seconds and then streams. Idle CPU stays under 5%. The app survives sleep, wake and network drops, and the outbox and drafts survive crashes.

**Accessibility.** Large text, high contrast, keyboard shortcuts, captions for every spoken reply, headset support, and tolerance for slow or hesitant speech. UI strings are kept separate so other languages can be added later.

## 7. Security and privacy

- Raw audio is held in memory only and discarded after transcription. It never leaves the PC.
- The cloud receives only request text and the excerpts a task needs. The user sees what will be sent and approves it. An admin can switch cloud use off.
- External sends, deletes and overwrites are read back and need a yes. High-risk actions also need a click or keypress, because a voice can be spoofed.
- Only registered tools and allow-listed apps can run. Email and calendar tokens use the narrowest scopes and sit in the OS credential vault. The model API key stays on the gateway, never in the app.
- A visible microphone indicator and mute toggle are always present. Transcripts are kept 30 days and the activity log 90 days. The database and voice embeddings are encrypted. Installers and model files are signed and checksummed.
- Voice data falls under the Nigeria Data Protection Act 2023. Get written consent for voice enrollment, show a privacy notice in the app, support deletion on request, and have legal review before any pilot.

## 8. Success metrics

- Task success with no help (5 or more non-technical users): 85% or higher
- Warm reply to a short command: under 3 seconds
- Speech word error rate on a Nigerian-accented test set: under 15%
- Speaker identification with up to 10 enrolled users: 95% or higher
- Policy answers correct and cited on a 30-question set, including correct "not found": 90% or higher
- Summaries free of invented facts: 9 of 10 reviewed; email drafts accepted with minor edits: 70% or higher
- Memo drafted and sent at least 50% faster than manual; IT requests on covered tasks down at least 40% over a 4-week pilot
- Offline tests passing with the internet off: 100%

## 9. Risks

- **Staff PCs are slow or short of RAM.** Mitigation: 8 GB minimum, Hosted profile, models loaded once and warmed, hardware check at install.
- **Poor recognition of Nigerian accents and names.** Mitigation: an accent test set, custom vocabulary, push-to-talk with a headset.
- **The gateway or the internet fails.** Mitigation: keyword path and outbox work offline, automatic fallback.
- **Wrong, uncited or invented answers.** Mitigation: answer only from passages, honest "not found", show the source, confirm every send. Step up from 26B A4B to 31B if tests show a quality gap.
- **Real documents reach a cloud provider.** Mitigation: sample documents in testing, recorded provider terms and consent, Local profile for confidential offices.
- **API cost or rate limits surprise us.** Mitigation: per-user spending cap on the gateway, cache repeated answers, check current provider pricing.
- **Scope creep.** Mitigation: stay inside section 1 and the requirements in section 3.

## 10. Open questions

- Where do we host the gateway, and in which region?
- Which Gemma 4 API provider do we use, and what is the spending cap?
- Do the target offices have many 2 GB PCs? If so, we would add an opt-in thin-client mode where audio goes to the gateway, with a clear notice. If only a few, we set 8 GB as the minimum and stop there.
- Which public circulars and policies make up the sample library, and which test email account do we use?
- Who is the legal reviewer for consent and data-protection obligations?
- What is the commercial model: per seat, per office, or government rollout?
