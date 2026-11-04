"""Official Gmail integration and Recruiter Thread Analysis for DADUS.
Supports OAuth 2.0 authorization, official Gmail REST API querying, real thread
semantic classification, and context-aware conversation navigation.
Strictly adheres to data integrity: zero synthetic or fabricated email records.
"""
import os
import re
import json
import logging
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import requests
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.tools.browser import launch_browser_url
from app.config.settings import settings, BASE_DIR

logger = logging.getLogger("DADUS.Gmail")

# 9 Standard Recruiter Conversation Categories
CATEGORIES = [
    "Recruiter replied",
    "Recruiter contacted me",
    "Interview opportunity",
    "Shortlisted / next round",
    "Application update",
    "Rejection",
    "Awaiting recruiter response",
    "Automated acknowledgment",
    "Uncertain classification"
]

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GmailClient:
    """Manages OAuth 2.0 credentials and official Gmail REST API calls."""

    TOKEN_PATHS = [
        settings.DATA_DIR / "credentials" / "gmail_token.json",
        BASE_DIR / "gmail_token.json",
        BASE_DIR / "credentials.json",
    ]
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    @classmethod
    def _find_token_file(cls) -> Optional[Path]:
        """Locates the active OAuth token or credentials file if present."""
        for p in cls.TOKEN_PATHS:
            if p.exists():
                return p
        return None

    @classmethod
    def is_connected(cls) -> bool:
        """Checks if a valid OAuth access token or refreshable credential exists."""
        token = cls.get_token()
        return bool(token)

    @classmethod
    def disconnect(cls) -> bool:
        """Safely purge OAuth tokens."""
        success = True
        for p in cls.TOKEN_PATHS:
            if p.exists() and "token" in p.name:
                try:
                    os.remove(p)
                    logger.info(f"Purged Gmail OAuth token: {p}")
                except Exception as ex:
                    logger.error(f"Error purging {p}: {ex}")
                    success = False
        return success

    @classmethod
    def get_token(cls) -> Optional[str]:
        """
        Retrieves an active access token.
        If an expired token with a refresh token is present, automatically refreshes it.
        """
        # 1. Environment variable override
        env_token = os.environ.get("GMAIL_ACCESS_TOKEN", "").strip()
        if env_token:
            return env_token

        # 2. File-based token storage
        token_path = cls._find_token_file()
        if not token_path:
            return None

        try:
            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Direct access token
            access_token = data.get("access_token") or data.get("token")
            expiry = data.get("expiry") or data.get("expires_at")
            refresh_token = data.get("refresh_token")
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")

            # Check expiration if timestamp is present
            is_expired = False
            if expiry:
                try:
                    exp_dt = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                    if exp_dt <= datetime.now(timezone.utc):
                        is_expired = True
                except Exception:
                    pass

            if access_token and not is_expired:
                return access_token

            # Attempt refresh if expired and refresh_token is available
            if refresh_token and client_id and client_secret:
                refreshed = cls._refresh_token(token_path, refresh_token, client_id, client_secret)
                if refreshed:
                    return refreshed

            return access_token if access_token else None
        except Exception as ex:
            logger.debug(f"Could not read Gmail token from {token_path}: {ex}")
            return None

    @classmethod
    def _refresh_token(cls, token_path: Path, refresh_token: str, client_id: str, client_secret: str) -> Optional[str]:
        """Refreshes expired OAuth 2.0 token using Google's token endpoint."""
        try:
            resp = requests.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                },
                timeout=10
            )
            if resp.status_code == 200:
                payload = resp.json()
                new_token = payload.get("access_token")
                if new_token:
                    # Update local file with new token
                    try:
                        with open(token_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        data["access_token"] = new_token
                        with open(token_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                    except Exception:
                        pass
                    return new_token
        except Exception as ex:
            logger.warning(f"Failed to refresh Gmail OAuth token: {ex}")
        return None

    @classmethod
    def fetch_recruiter_threads(cls, query_filter: Optional[str] = None, max_results: int = 15) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Executes official Gmail REST API calls to retrieve real recruiter and job emails.
        Returns (list_of_raw_threads, error_message).
        Strictly never fabricates fake records.
        """
        token = cls.get_token()
        if not token:
            return [], "GMAIL_AUTH_REQUIRED"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        # Build official Gmail search query for career & recruitment communication
        # Excludes automated spam and marketing promotions
        search_terms = (
            '(subject:(interview OR recruiter OR offer OR application OR hiring OR shortlisted OR "next round" '
            'OR "technical screen" OR "careers" OR "position" OR "invitation") '
            'OR "interview" OR "shortlisted" OR "hiring manager") '
            '-category:promotions -category:spam'
        )
        if query_filter:
            search_terms = f"{search_terms} {query_filter}"

        params = {
            "q": search_terms,
            "maxResults": max_results
        }

        try:
            # 1. Query messages matching recruitment search
            resp = requests.get(f"{GMAIL_API_BASE}/messages", headers=headers, params=params, timeout=12)
            if resp.status_code == 401:
                logger.warning("Gmail API returned 401 Unauthorized.")
                return [], "GMAIL_AUTH_EXPIRED"
            if resp.status_code != 200:
                logger.error(f"Gmail API error {resp.status_code}: {resp.text}")
                return [], f"GMAIL_API_ERROR_{resp.status_code}"

            data = resp.json()
            messages_list = data.get("messages", [])
            if not messages_list:
                return [], None

            # 2. Group messages by thread_id to avoid duplicate calls
            seen_threads = set()
            thread_ids = []
            for m in messages_list:
                t_id = m.get("threadId") or m.get("id")
                if t_id and t_id not in seen_threads:
                    seen_threads.add(t_id)
                    thread_ids.append(t_id)

            # 3. Retrieve real thread details from Gmail API
            raw_threads = []
            for tid in thread_ids[:max_results]:
                t_resp = requests.get(
                    f"{GMAIL_API_BASE}/threads/{tid}",
                    headers=headers,
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                    timeout=10
                )
                if t_resp.status_code == 200:
                    raw_threads.append(t_resp.json())

            return raw_threads, None

        except requests.exceptions.RequestException as req_err:
            logger.error(f"Network error communicating with Gmail API: {req_err}")
            return [], "GMAIL_NETWORK_ERROR"
        except Exception as exc:
            logger.error(f"Unexpected error retrieving Gmail messages: {exc}")
            return [], f"GMAIL_ERROR: {str(exc)}"

    @classmethod
    def analyze_thread(cls, thread_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes authentic Gmail conversation thread metadata and snippets.
        Extracts real sender, subject, date, thread ID, and applies semantic classification.
        Guarantees that every property is traced directly to the retrieved Gmail source.
        """
        messages = thread_data.get("messages", [])
        if not messages:
            return cls._empty_insight(thread_data.get("id", ""))

        thread_id = thread_data.get("id", "")
        if not thread_id and messages:
            thread_id = messages[0].get("threadId", "")

        # Extract headers from first and latest messages
        first_headers = {
            h.get("name", "").lower(): h.get("value", "")
            for h in messages[0].get("payload", {}).get("headers", [])
        }
        subject = first_headers.get("subject", "No Subject")

        latest_msg = messages[-1]
        latest_headers = {
            h.get("name", "").lower(): h.get("value", "")
            for h in latest_msg.get("payload", {}).get("headers", [])
        }
        from_raw = latest_headers.get("from", "") or first_headers.get("from", "")
        date_str = latest_headers.get("date", "") or first_headers.get("date", "")

        # Parse sender name and email from RFC 2822 From header
        name_match = re.match(r"^\"?([^\"<]+)\"?\s*<([^>]+)>", from_raw)
        if name_match:
            sender_name = name_match.group(1).strip()
            sender_email = name_match.group(2).strip()
        else:
            sender_name = from_raw.strip()
            sender_email = from_raw.strip()

        # Extract snippet provided by Gmail API
        snippet = latest_msg.get("snippet", "") or messages[0].get("snippet", "")

        # Extract company name from subject or sender domain
        company_name = cls._extract_company(subject, sender_email, sender_name)

        # Classification logic based on thread structure and actual content
        category, next_action = cls._classify_interaction(
            messages_count=len(messages),
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            snippet=snippet
        )

        return {
            "thread_id": thread_id,
            "recruiter_name": sender_name,
            "sender_email": sender_email,
            "company_name": company_name,
            "subject": subject,
            "date": date_str or datetime.now(timezone.utc).strftime("%b %d, %Y"),
            "latest_message_summary": snippet or subject,
            "status": category,
            "relevant_recruiter_response": snippet[:140] + ("..." if len(snippet) > 140 else ""),
            "suggested_next_action": next_action,
            "gmail_link": f"https://mail.google.com/mail/u/0/#inbox/{thread_id}" if thread_id else "https://mail.google.com"
        }

    @classmethod
    def _extract_company(cls, subject: str, sender_email: str, sender_name: str) -> str:
        """Infer company name from email domain or subject."""
        # 1. From domain
        if "@" in sender_email:
            domain = sender_email.split("@")[1].lower()
            main_domain = domain.split(".")[0]
            if main_domain not in ["gmail", "yahoo", "outlook", "hotmail", "icloud", "mail", "proton", "zoho"]:
                return main_domain.capitalize()

        # 2. From subject "Role at Company" or "Company: Status"
        comp_match = re.search(r"\b(?:at|with|from|@)\s+([A-Za-z0-9_\-\.\s]{2,20})", subject, re.IGNORECASE)
        if comp_match:
            cand = comp_match.group(1).strip(" .?!,")
            if cand.lower() not in ["the", "your", "my", "our", "a", "an"]:
                return cand.title()

        return sender_name or "Unknown Company"

    @classmethod
    def _classify_interaction(
        cls,
        messages_count: int,
        sender_email: str,
        sender_name: str,
        subject: str,
        snippet: str
    ) -> Tuple[str, str]:
        """
        Content-based semantic classifier for recruiter threads.
        Distinguishes recruiter replies, outreach, interview invitations, shortlisting,
        and rejections from automated system acknowledgments.
        """
        text = f"{subject} {snippet}".lower()
        sender_lower = f"{sender_name} {sender_email}".lower()

        # Automated confirmation / do-not-reply / system notifications
        if any(w in sender_lower for w in ["no-reply", "noreply", "notifications", "alerts", "mailer-daemon", "system"]):
            if any(w in text for w in ["received your application", "thank you for applying", "confirmation", "applied"]):
                return "Automated acknowledgment", "No immediate action required. Application logged."

        # Interview invitations
        if any(w in text for w in [
            "interview", "invitation", "schedule a time", "screen call", "technical round",
            "availability for a chat", "calendar invite", "zoom", "google meet", "hiring manager chat"
        ]):
            return "Interview opportunity", "Schedule interview slot / confirm availability."

        # Shortlisting / Next round
        if any(w in text for w in [
            "shortlisted", "next stage", "moving forward", "passed the assessment",
            "congratulations", "next step", "final round"
        ]):
            return "Shortlisted / next round", "Review next round requirements and prepare portfolio/code."

        # Rejection
        if any(w in text for w in [
            "not moving forward", "other candidates", "unfortunately", "pursue other",
            "regret to inform", "not selected", "decided not to proceed"
        ]):
            return "Rejection", "Archive application and focus on active pipelines."

        # Direct Recruiter Outreach / Contacted me
        if messages_count == 1:
            if any(w in text for w in [
                "profile", "came across", "exciting opportunity", "reach out",
                "are you open", "hiring for", "role at", "opportunity at"
            ]):
                return "Recruiter contacted me", "Review job description and respond with resume/interest."

        # Recruiter replied to existing thread
        if messages_count > 1:
            if any(w in text for w in ["feedback", "update", "spoke with the team", "following up", "status of"]):
                return "Recruiter replied", "Read full message and respond promptly."
            return "Application update", "Check details and reply if required."

        if any(w in text for w in ["applied", "submitted", "application"]):
            return "Awaiting recruiter response", "Follow up if more than 7 days have passed."

        return "Uncertain classification", "Manually review conversation in Gmail."

    @classmethod
    def _empty_insight(cls, thread_id: str) -> Dict[str, Any]:
        return {
            "thread_id": thread_id,
            "recruiter_name": "Unknown Sender",
            "sender_email": "",
            "company_name": "Unknown",
            "subject": "No Subject",
            "date": datetime.now(timezone.utc).strftime("%b %d, %Y"),
            "latest_message_summary": "No content",
            "status": "Uncertain classification",
            "relevant_recruiter_response": "",
            "suggested_next_action": "Check thread in Gmail.",
            "gmail_link": f"https://mail.google.com/mail/u/0/#inbox/{thread_id}" if thread_id else "https://mail.google.com"
        }


# ==========================================
# Tool 1: open_gmail
# ==========================================
class OpenGmailInput(BaseModel):
    account: Optional[str] = Field(default=None, description="Specific email address or profile, if multiple exist.")

class OpenGmailTool(BaseTool):
    name = "open_gmail"
    description = "Opens Gmail in the web browser and verifies authentication status."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenGmailInput

    def execute(self, account: Optional[str] = None) -> ToolResult:
        logger.info("Opening Gmail in browser...")
        url = "https://mail.google.com"
        launch_browser_url(url)

        connected = GmailClient.is_connected()
        auth_note = " (OAuth connected)" if connected else " (Awaiting OAuth sign-in)"
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Opening Gmail in your browser, Boss{auth_note}.",
            data={"url": url, "authenticated": connected}
        )


# ==========================================
# Tool 2: find_recruiter_emails
# ==========================================
class FindRecruiterEmailsInput(BaseModel):
    query: Optional[str] = Field(default=None, description="Optional filter keyword or company name.")
    category_filter: Optional[str] = Field(default=None, description="Filter by status, e.g. 'Interview opportunity'.")

class FindRecruiterEmailsTool(BaseTool):
    name = "find_recruiter_emails"
    description = "Searches Gmail for recruiter responses, job updates, and interview invitations with semantic thread analysis."
    permission_level = PermissionLevel.SAFE
    args_schema = FindRecruiterEmailsInput

    def execute(self, query: Optional[str] = None, category_filter: Optional[str] = None) -> ToolResult:
        logger.info(f"Finding recruiter emails (query='{query}', category='{category_filter}')...")

        # 1. Verify official Gmail authentication
        if not GmailClient.is_connected():
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=(
                    "Boss, Gmail access is not authenticated. Please provide Google OAuth credentials "
                    "(credentials.json or a valid OAuth token in data/credentials/gmail_token.json) "
                    "to allow DADUS to securely search your inbox."
                ),
                error="GMAIL_AUTH_REQUIRED",
                data={"results": [], "authenticated": False}
            )

        # 2. Retrieve genuine threads via official Gmail API
        raw_threads, err = GmailClient.fetch_recruiter_threads(query_filter=query)
        if err:
            if err == "GMAIL_AUTH_EXPIRED" or err == "GMAIL_AUTH_REQUIRED":
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message="Boss, your Gmail authentication has expired. Please re-authorize Gmail access.",
                    error=err,
                    data={"results": [], "authenticated": False}
                )
            logger.warning(f"Gmail search returned error code: {err}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I encountered an issue querying your Gmail: {err}.",
                error=err,
                data={"results": []}
            )

        # 3. Handle empty results honestly
        if not raw_threads:
            return ToolResult(
                tool_name=self.name,
                success=True,
                message="Boss, I searched your Gmail inbox and found no recruiter or job-related emails.",
                data={"results": [], "count": 0, "active_responses": 0}
            )

        # 4. Analyze actual retrieved threads
        analyzed_results = []
        for t in raw_threads:
            insight = GmailClient.analyze_thread(t)

            # Apply query filters if requested
            if query:
                q_lower = query.lower()
                matches = (
                    q_lower in insight["company_name"].lower()
                    or q_lower in insight["recruiter_name"].lower()
                    or q_lower in insight["subject"].lower()
                    or q_lower in insight["latest_message_summary"].lower()
                )
                if not matches:
                    continue

            if category_filter and category_filter.lower() not in insight["status"].lower():
                continue

            analyzed_results.append(insight)

        # Sort by most recent
        analyzed_results.sort(key=lambda x: x.get("date", ""), reverse=True)

        if not analyzed_results:
            msg = "Boss, I searched your Gmail inbox but none of the retrieved messages matched your specific filters."
            return ToolResult(tool_name=self.name, success=True, message=msg, data={"results": [], "count": 0})

        recruiter_replies = [
            r for r in analyzed_results
            if r["status"] in ["Recruiter replied", "Interview opportunity", "Shortlisted / next round", "Recruiter contacted me"]
        ]
        reply_count = len(recruiter_replies)

        summary_lines = []
        for r in analyzed_results[:4]:
            summary_lines.append(f"• {r['company_name']} ({r['status']}): {r['recruiter_name']} - '{r['subject']}'")

        formatted_msg = (
            f"Boss, I found {len(analyzed_results)} job-related threads in your Gmail ({reply_count} active recruiter responses):\n"
            + "\n".join(summary_lines)
            + "\n\nI have organized the full conversation links and details in your dashboard."
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            message=formatted_msg,
            data={
                "results": analyzed_results,
                "count": len(analyzed_results),
                "active_responses": reply_count,
                "latest_thread": analyzed_results[0] if analyzed_results else None
            }
        )


# ==========================================
# Tool 3: open_email_thread
# ==========================================
class OpenEmailThreadInput(BaseModel):
    thread_id: Optional[str] = Field(default=None, description="Gmail thread ID to open in the browser.")

class OpenEmailThreadTool(BaseTool):
    name = "open_email_thread"
    description = "Opens a specific Gmail conversation thread in the web browser."
    permission_level = PermissionLevel.SAFE
    args_schema = OpenEmailThreadInput

    def execute(self, thread_id: Optional[str] = None) -> ToolResult:
        if not thread_id:
            # If no thread_id given, check if Gmail is connected
            if not GmailClient.is_connected():
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message="Boss, please provide a specific Gmail thread ID or connect your Gmail account.",
                    error="THREAD_NOT_SPECIFIED"
                )
            # Try fetching latest thread
            raw_threads, _ = GmailClient.fetch_recruiter_threads(max_results=1)
            if raw_threads and raw_threads[0].get("id"):
                thread_id = raw_threads[0]["id"]
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message="Boss, no active recruiter conversation was found in your Gmail to open.",
                    error="NO_THREADS_FOUND"
                )

        url = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"
        launch_browser_url(url)
        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Opening that conversation in Gmail, Boss.",
            data={"thread_id": thread_id, "url": url}
        )


# ==========================================
# Tool 4: read_latest_email
# ==========================================
class ReadLatestEmailInput(BaseModel):
    pass

class ReadLatestEmailTool(BaseTool):
    name = "read_latest_email"
    description = "Fetches and summarizes the most recent email from your connected Gmail inbox."
    permission_level = PermissionLevel.SAFE
    args_schema = ReadLatestEmailInput

    def execute(self) -> ToolResult:
        if not GmailClient.is_connected():
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, Gmail is not connected. Please provide Google OAuth credentials to read your emails.",
                error="GMAIL_AUTH_REQUIRED",
                data={"authenticated": False}
            )

        token = GmailClient.get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        try:
            resp = requests.get(
                f"{GMAIL_API_BASE}/messages",
                headers=headers,
                params={"maxResults": 1, "q": "in:inbox"},
                timeout=10
            )
            if resp.status_code == 401:
                return ToolResult(tool_name=self.name, success=False, message="Boss, your Gmail authorization has expired.", error="GMAIL_AUTH_EXPIRED")
            if resp.status_code != 200:
                return ToolResult(tool_name=self.name, success=False, message=f"Gmail API error: {resp.status_code}", error=f"API_{resp.status_code}")

            data = resp.json()
            messages = data.get("messages", [])
            if not messages:
                return ToolResult(tool_name=self.name, success=True, message="Boss, your Gmail inbox is currently empty.", data={"count": 0})

            mid = messages[0]["id"]
            m_resp = requests.get(
                f"{GMAIL_API_BASE}/messages/{mid}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                timeout=10
            )
            if m_resp.status_code != 200:
                return ToolResult(tool_name=self.name, success=False, message="Could not retrieve email details.", error="MESSAGE_FETCH_FAILED")

            m_data = m_resp.json()
            headers_dict = {h.get("name", "").lower(): h.get("value", "") for h in m_data.get("payload", {}).get("headers", [])}
            sender = headers_dict.get("from", "Unknown Sender")
            subject = headers_dict.get("subject", "(No Subject)")
            date_str = headers_dict.get("date", "")
            snippet = m_data.get("snippet", "")
            thread_id = m_data.get("threadId", mid)
            link = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

            msg = (
                f"Boss, your latest email is from {sender}:\n"
                f"Subject: '{subject}'\n"
                f"Date: {date_str}\n\n"
                f"Summary: {snippet}"
            )

            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                data={
                    "sender": sender,
                    "subject": subject,
                    "date": date_str,
                    "snippet": snippet,
                    "thread_id": thread_id,
                    "gmail_link": link
                }
            )
        except Exception as ex:
            logger.error(f"Error reading latest email: {ex}")
            return ToolResult(tool_name=self.name, success=False, message=f"Failed to read latest email: {str(ex)}", error=str(ex))


# ==========================================
# Tool 5: draft_email
# ==========================================
class DraftEmailInput(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Subject line of the email")
    body: str = Field(description="Body text content of the email")

class DraftEmailTool(BaseTool):
    name = "draft_email"
    description = "Prepares an email draft in Gmail without sending it."
    permission_level = PermissionLevel.SAFE
    args_schema = DraftEmailInput

    def execute(self, to: str, subject: str, body: str) -> ToolResult:
        if not GmailClient.is_connected():
            # Fallback to mailto draft in client
            import urllib.parse
            encoded_subj = urllib.parse.quote(subject)
            encoded_body = urllib.parse.quote(body)
            mailto_url = f"mailto:{to}?subject={encoded_subj}&body={encoded_body}"
            launch_browser_url(mailto_url)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, Gmail API is not connected. I opened a new draft to {to} in your default email client.",
                data={"to": to, "subject": subject, "client": "os_default"}
            )

        token = GmailClient.get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Construct RFC 2822 message
        import base64
        from email.mime.text import MIMEText
        mime_msg = MIMEText(body)
        mime_msg["to"] = to
        mime_msg["subject"] = subject
        raw_b64 = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()

        try:
            resp = requests.post(
                f"{GMAIL_API_BASE}/drafts",
                headers=headers,
                json={"message": {"raw": raw_b64}},
                timeout=10
            )
            if resp.status_code in [200, 201]:
                draft_data = resp.json()
                draft_id = draft_data.get("id")
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message=f"Boss, I've created an email draft to {to} with subject '{subject}'. It is ready in your Gmail drafts folder.",
                    data={"draft_id": draft_id, "to": to, "subject": subject}
                )
            else:
                return ToolResult(tool_name=self.name, success=False, message=f"Could not create draft (HTTP {resp.status_code})", error=resp.text)
        except Exception as ex:
            return ToolResult(tool_name=self.name, success=False, message=f"Failed to create email draft: {str(ex)}", error=str(ex))


# ==========================================
# Tool 6: send_email
# ==========================================
class SendEmailInput(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Subject line of the email")
    body: str = Field(description="Body text content of the email")

class SendEmailTool(BaseTool):
    name = "send_email"
    description = "Sends an email to a recipient via official Gmail API. Strictly requires confirmation."
    permission_level = PermissionLevel.CONFIRMATION_REQUIRED
    args_schema = SendEmailInput

    def execute(self, to: str, subject: str, body: str) -> ToolResult:
        if not GmailClient.is_connected():
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, Gmail is not connected. Sending email requires an authenticated Gmail OAuth connection.",
                error="GMAIL_AUTH_REQUIRED"
            )

        token = GmailClient.get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        import base64
        from email.mime.text import MIMEText
        mime_msg = MIMEText(body)
        mime_msg["to"] = to
        mime_msg["subject"] = subject
        raw_b64 = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()

        try:
            resp = requests.post(
                f"{GMAIL_API_BASE}/messages/send",
                headers=headers,
                json={"raw": raw_b64},
                timeout=12
            )
            if resp.status_code in [200, 201]:
                sent_data = resp.json()
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message=f"Email sent successfully to {to}, Boss.",
                    data={"sent_id": sent_data.get("id"), "to": to, "subject": subject}
                )
            else:
                return ToolResult(tool_name=self.name, success=False, message=f"Failed to send email: HTTP {resp.status_code}", error=resp.text)
        except Exception as ex:
            return ToolResult(tool_name=self.name, success=False, message=f"Error sending email: {str(ex)}", error=str(ex))
