# Phase D2: open the source behind a citation

Implements the backend source-opening portion of POL-3, with SYSX-3 cancellation.
Uses the existing v1 `source.open {file_path, page}` event. It needs no model,
provider, new public fields or index migration. Real Windows/frontend/staff
acceptance remains separate from backend/stub verification.

## Configure and use

Enable the D1 policy folder/cache in your local-tools TOML. Then explicitly choose
installed Windows applications for the formats you want to open:

```toml
timezone = "Africa/Lagos"
policy_folder = "../library/policies"
policy_database = "../data/aria.db"

[source_viewers.pdf]
executable = "C:/replace-with-your-installed-path/SumatraPDF.exe"
kind = "sumatra"

[source_viewers.docx]
executable = "C:/replace-with-your-installed-path/WINWORD.EXE"
kind = "file"

[source_viewers.txt]
executable = "C:/replace-with-your-installed-path/notepad.exe"
kind = "file"
```

Replace those paths with actual installed `.exe` files. Missing/unknown viewers
fail clearly; the agent does not discover applications, download a viewer, use
shell associations or guess installation paths. These settings are backend TOML
configuration; frontend settings controls remain future work.

Run the existing authenticated `agent.local` service, search with
`text.input: "search policy annual leave"`, then have the frontend send the
selected citation's exact file_path/page in `source.open`. The existing mock
scenario `open_policy_source` documents the full search/open event sequence.
The frontend still owns the actual button and staff acceptance test.

The session routes this request into the registered `files.open` tool through the
executor and killable worker. The UI never opens a file directly. A successful
launch produces activity and a caption; failure produces an explicit missing,
changed, invalid-selection or unavailable-viewer message and no success activity.
There is no undo for opening a viewer. No source file is modified, overwritten or
deleted by the agent.

## Selection and integrity checks

Search outputs now carry internal source receipts containing a snapshot digest.
They remain outside public citations/events and the user-facing CLI output.
The executor remembers only the most recently published policy result's sources,
not arbitrary UI paths. A new search clears the old selection; close/disconnect
clears it. An incomplete/cancelled result publication cannot authorize an open.
Unknown paths, guessed pages and selections from another session are rejected.
Stop cancels pending work; choosing a source again afterward is a new request.

The tool independently checks the configured root, absolute/canonical supported
file path, symlink redirection, current index record and cited page. It compares
current bounded source bytes and explicit manifest metadata with the original
search snapshot, including when another process has since reindexed the file.
Changed/missing sources require a fresh search. This validates source identity,
not the correctness of the document's policy claims. No document text is evaluated
as commands or used to select a viewer/executable.

Windows launch uses only the configured executable and fixed argument arrays,
with shell=False, discarded stdio and an allow-listed environment that omits
ARIA/gateway credentials. The adapter rechecks executable identity and calls the
source validator immediately before launch. Source checks are not an OS file
lock or sandbox: a separate process could modify a file after that last check
and before the external viewer reads it. A successfully launched viewer is not
proof that its window has loaded or that it actually navigated; captions report
that the launch/page request was made.

## Page and section behavior

With `kind="sumatra"`, PDF navigation uses fixed `-restrict -page N <file>`
arguments based on the [official page-opening documentation](https://www.sumatrapdfreader.org/docs/Open-PDF-at-page-from-command-line).
Restricted mode is documented by [SumatraPDF](https://www.sumatrapdfreader.org/docs/Configure-for-restricted-use).
With `kind="file"`, the configured viewer receives only the file path; the caption
explicitly says it cannot jump to the cited PDF page. No arbitrary flags, commands,
URLs or source-controlled viewer arguments are accepted.

DOCX/text citations have no invented page number. Open the file and tell the user
to use the cited section. Automatic Word/text heading navigation is not claimed.
Native source launching is Windows-only, matching the staff-PC target. macOS/Linux
exercise parsing/validation and stubbed launch arguments in CI, without opening apps.

## Cancellation and verification

Source opening uses the existing executor's timeout, policy checks and cancellation.
No action retries are added. If cancellation/timeout interrupts a launch, the
activity log retains the existing uncertainty warning: a viewer already started
cannot be retracted. Completed earlier steps are not rolled back.

`test_source_open.py` covers snapshot/metadata/index changes, missing/outside/
symlink files, wrong pages/digests, exact session selection, clearing/replacement,
cancel-before-launch, failed publication, typed wire pages, fixed Windows arguments,
environment filtering, native failures and real authenticated scenario parity.
All unit sockets stay blocked, and all viewer launches are stubs. The separate
real-worker smoke verifies valid and stale source receipts against encrypted
fictional policy data; it never starts a viewer or reads native vault credentials.
Windows/macOS/Linux CI verifies these paths. A real staff PC must still verify
its selected viewer and page navigation before the pilot.
