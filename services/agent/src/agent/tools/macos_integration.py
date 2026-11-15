"""macOS native implementations for app launching, file search, calendar, and mail."""

from __future__ import annotations

import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.contracts.tools import (
    CalEvent,
    FileMatch,
)

# ============================================================
# App Launcher (macOS)
# ============================================================


class MacOSAppLauncher:
    """Launch macOS apps by display name or bundle ID."""

    def __init__(self) -> None:
        self._bundle_cache: dict[str, str] = {}

    def launch(self, app_name: str) -> tuple[bool, str]:
        # Try direct launch by display name
        result = subprocess.run(
            ["open", "-a", app_name], check=False, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, f"Launched {app_name}"

        # Try bundle ID lookup
        bundle_id = self._resolve_bundle_id(app_name)
        if bundle_id:
            result = subprocess.run(
                ["open", "-b", bundle_id], check=False, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, f"Launched {app_name} ({bundle_id})"

        return False, f"App '{app_name}' not found"

    def _resolve_bundle_id(self, name: str) -> str | None:
        if name in self._bundle_cache:
            return self._bundle_cache[name]

        # Search /Applications and ~/Applications
        for root in ["/Applications", "/System/Applications", str(Path.home() / "Applications")]:
            result = subprocess.run(
                [
                    "mdfind",
                    "-onlyin",
                    root,
                    f"kMDItemDisplayName == '{name}*' && kMDItemContentType == 'com.apple.application-bundle'",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if line and line.endswith(".app"):
                    bundle_id = self._extract_bundle_id(line)
                    if bundle_id:
                        self._bundle_cache[name] = bundle_id
                        return bundle_id
        return None

    def _extract_bundle_id(self, app_path: str) -> str | None:
        try:
            plist_path = Path(app_path) / "Contents" / "Info.plist"
            with plist_path.open("rb") as f:
                data = plistlib.load(f)
                bundle_id = data.get("CFBundleIdentifier")
                return bundle_id if isinstance(bundle_id, str) else None
        except (OSError, plistlib.InvalidFileException):
            return None


# ============================================================
# File Search (Spotlight / mdfind)
# ============================================================


class MacOSFileIndex:
    """File search using Spotlight (mdfind)."""

    def search(self, query: str, max_results: int, include_content: bool) -> list[FileMatch]:
        # Build mdfind query
        # kMDItemDisplayName = filename, kMDItemTextContent = content
        if include_content:
            md_query = f"({query}) || (kMDItemDisplayName == '*{query}*')"
        else:
            md_query = f"kMDItemDisplayName == '*{query}*'"

        cmd = ["mdfind", "-count", str(max_results), md_query]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return []

        paths = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        matches = []
        for path in paths:
            if Path(path).exists():
                stat = Path(path).stat()
                snippet = ""
                if include_content:
                    snippet = self._get_snippet(path, query)
                matches.append(
                    FileMatch(
                        path=path,
                        name=Path(path).name,
                        modified=str(stat.st_mtime),
                        size=stat.st_size,
                        snippet=snippet,
                    )
                )
        return matches

    def _get_snippet(self, path: str, query: str) -> str:
        try:
            # Use mdls to get text content preview
            result = subprocess.run(
                ["mdls", "-name", "kMDItemTextContent", path],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            content = result.stdout
            # Find query in content
            idx = content.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 80)
                end = min(len(content), idx + len(query) + 80)
                return "..." + content[start:end] + "..."
        except (OSError, subprocess.SubprocessError):
            return ""
        return ""


# ============================================================
# Calendar (CalDAV - works with iCloud, Google, Exchange)
# ============================================================


@dataclass
class CalDAVConfig:
    url: str  # e.g., "https://caldav.icloud.com" or "https://dav.messaging.microsoft.com"
    username: str
    password: str  # app-specific password for iCloud


class CalDAVCalendar:
    """CalDAV calendar backend (iCloud, Google, Exchange, etc.)."""

    def __init__(self, config: CalDAVConfig) -> None:
        self.config = config
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import caldav

            self._client = caldav.DAVClient(
                url=self.config.url,
                username=self.config.username,
                password=self.config.password,
            )
        return self._client

    def list_events(self, start: str, end: str) -> list[CalEvent]:
        import datetime as dt

        from icalendar import Calendar as ICal

        client = self._get_client()
        principal = client.principal()
        calendars = principal.calendars()

        events = []
        for cal in calendars:
            # CalDAV date format
            cal_start = dt.datetime.fromisoformat(start)
            cal_end = dt.datetime.fromisoformat(end)

            results = cal.date_search(cal_start, cal_end)
            for event in results:
                ical = ICal.from_ical(event.data)
                for component in ical.walk("VEVENT"):
                    uid = str(component.get("UID", ""))
                    summary = str(component.get("SUMMARY", ""))
                    dtstart = component.get("DTSTART").dt
                    dtend = component.get("DTEND").dt
                    events.append(
                        CalEvent(
                            event_id=uid,
                            title=summary,
                            start=dtstart.isoformat()
                            if hasattr(dtstart, "isoformat")
                            else str(dtstart),
                            end=dtend.isoformat() if hasattr(dtend, "isoformat") else str(dtend),
                            ics_uid=uid,
                        )
                    )
        return events

    def create_event(
        self, title: str, start: str, end: str, description: str | None
    ) -> tuple[str, list[str]]:
        import datetime as dt
        import uuid

        from icalendar import Calendar, Event

        client = self._get_client()
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            raise RuntimeError("No calendars found")

        cal = calendars[0]  # Use first calendar

        ical = Calendar()
        ical.add("prodid", "-//ARIA//Calendar//EN")
        ical.add("version", "2.0")

        event = Event()
        event_id = str(uuid.uuid4())
        event.add("uid", event_id)
        event.add("summary", title)
        event.add("dtstart", dt.datetime.fromisoformat(start))
        event.add("dtend", dt.datetime.fromisoformat(end))
        if description:
            event.add("description", description)
        ical.add_component(event)

        cal.save_event(ical.to_ical().decode())
        return event_id, []  # No conflict detection in basic CalDAV

    def move_event(self, event_id: str, new_start: str, new_end: str) -> tuple[str, list[str]]:
        import datetime as dt

        from icalendar import Calendar as ICal

        client = self._get_client()
        principal = client.principal()
        calendars = principal.calendars()

        for cal in calendars:
            event = cal.get_event(event_id)
            if event:
                ical = ICal.from_ical(event.data)
                for component in ical.walk("VEVENT"):
                    component["DTSTART"] = dt.datetime.fromisoformat(new_start)
                    component["DTEND"] = dt.datetime.fromisoformat(new_end)
                cal.save_event(ical.to_ical().decode())
                return event_id, []
        raise RuntimeError(f"Event {event_id} not found")

    def cancel_event(self, event_id: str) -> bool:

        client = self._get_client()
        principal = client.principal()
        calendars = principal.calendars()

        for cal in calendars:
            try:
                event = cal.get_event(event_id)
                if event:
                    event.delete()
                    return True
            except (ValueError, KeyError, AttributeError):
                # Expected exceptions when event not found or invalid
                continue
        return False


# ============================================================
# Mail (IMAP/SMTP - works with iCloud, Gmail, Exchange, etc.)
# ============================================================


@dataclass
class MailConfig:
    imap_host: str  # e.g., "imap.mail.me.com" (iCloud), "imap.gmail.com"
    smtp_host: str  # e.g., "smtp.mail.me.com", "smtp.gmail.com"
    username: str
    password: str  # app-specific password
    imap_port: int = 993
    smtp_port: int = 587


class IMAPMailStore:
    """IMAP/SMTP mail backend."""

    def __init__(self, config: MailConfig) -> None:
        self.config = config
        self._imap: Any = None
        self._smtp: Any = None

    def _get_imap(self) -> Any:
        if self._imap is None:
            import imaplib

            self._imap = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
            self._imap.login(self.config.username, self.config.password)
        return self._imap

    def _get_smtp(self) -> Any:
        if self._smtp is None:
            import smtplib

            self._smtp = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
            self._smtp.starttls()
            self._smtp.login(self.config.username, self.config.password)
        return self._smtp

    def list_threads(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Search mail and return thread summaries."""
        import email

        imap = self._get_imap()
        imap.select("INBOX")

        # Build search criteria
        criteria = ["ALL"]
        if query:
            criteria = ["OR", "SUBJECT", query, "FROM", query]

        status, messages = imap.search(None, *criteria)
        if status != "OK":
            return []

        msg_ids = messages[0].split()[-max_results:]
        threads = []

        for msg_id in reversed(msg_ids):
            status, data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            subject = self._decode_header(msg["Subject"])
            from_addr = self._decode_header(msg["From"])
            date = msg["Date"]
            msg_id_str = msg["Message-ID"]

            threads.append(
                {
                    "thread_id": msg_id_str or msg_id.decode(),
                    "subject": subject,
                    "from": from_addr,
                    "date": date,
                    "snippet": self._get_snippet(msg),
                }
            )
        return threads

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        import email

        imap = self._get_imap()
        imap.select("INBOX")

        status, data = imap.search(None, f'HEADER Message-ID "{thread_id}"')
        if status != "OK" or not data[0]:
            return None

        msg_id = data[0].split()[0]
        status, data = imap.fetch(msg_id, "(RFC822)")
        if status != "OK":
            return None

        raw = data[0][1]
        msg = email.message_from_bytes(raw)
        return {
            "thread_id": thread_id,
            "subject": self._decode_header(msg["Subject"]),
            "from": self._decode_header(msg["From"]),
            "to": self._decode_header(msg["To"]),
            "date": msg["Date"],
            "body": self._get_body(msg),
            "attachments": self._get_attachments(msg),
        }

    def send_message(
        self, to: list[str], subject: str, body: str, attachments: list[bytes] | None = None
    ) -> str:
        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        smtp = self._get_smtp()

        msg = MIMEMultipart()
        msg["From"] = self.config.username
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if attachments:
            for i, data in enumerate(attachments):
                part = MIMEApplication(data)
                part.add_header("Content-Disposition", "attachment", filename=f"attachment_{i}.bin")
                msg.attach(part)

        smtp.send_message(msg)
        return msg["Message-ID"]

    def _decode_header(self, header: str | None) -> str:
        if not header:
            return ""
        from email.header import decode_header

        parts = decode_header(header)
        result = []
        for part, encoding in parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or "utf-8", errors="ignore"))
            else:
                result.append(part)
        return "".join(result)

    def _get_snippet(self, msg: Any) -> str:
        body = self._get_body(msg)
        return body[:200] + "..." if len(body) > 200 else body

    def _get_body(self, msg: Any) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        return payload.decode(errors="ignore")
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode(errors="ignore")
        return ""

    def _get_attachments(self, msg: Any) -> list[dict[str, Any]]:
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    filename = part.get_filename()
                    if filename:
                        attachments.append(
                            {
                                "filename": filename,
                                "content_type": part.get_content_type(),
                                "size": len(part.get_payload(decode=True) or b""),
                            }
                        )
        return attachments


# ============================================================
# Factory: pick backend based on platform + config
# ============================================================


def get_app_launcher() -> Any:
    """Get platform-appropriate app launcher."""
    import sys

    if sys.platform == "darwin":
        return MacOSAppLauncher()
    from agent.tools.cal_files_apps import _FakeAppLauncher

    return _FakeAppLauncher()


def get_file_index() -> Any:
    """Get platform-appropriate file index."""
    import sys

    if sys.platform == "darwin":
        return MacOSFileIndex()
    from agent.tools.cal_files_apps import _FakeFileIndex

    return _FakeFileIndex()


def get_calendar(config: dict[str, Any] | None = None) -> Any:
    """Get calendar backend."""
    import sys

    if sys.platform == "darwin" and config:
        return CalDAVCalendar(CalDAVConfig(**config))
    from agent.tools.cal_files_apps import _FakeCalendarStore

    return _FakeCalendarStore()


def get_mail_store(config: dict[str, Any] | None = None) -> Any:
    """Get mail backend."""
    import sys

    if sys.platform == "darwin" and config:
        return IMAPMailStore(MailConfig(**config))
    from agent.tools.cal_files_apps import _FakeMailStore

    return _FakeMailStore()
