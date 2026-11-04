"""Tests for Phase 5 Intelligent Gmail Integration & Recruiter Thread Analysis."""
import pytest
from unittest.mock import patch, MagicMock

from app.agent.agent import DadusAgent
from app.tools.gmail import (
    OpenGmailTool,
    FindRecruiterEmailsTool,
    OpenEmailThreadTool,
    GmailClient,
    CATEGORIES
)

@patch("app.tools.gmail.launch_browser_url")
def test_open_gmail_tool(mock_launch):
    """Verify open_gmail opens the web interface and checks authentication."""
    tool = OpenGmailTool()
    res = tool.execute()
    assert res.success is True
    assert "Opening Gmail" in res.message
    assert "mail.google.com" in res.data["url"]
    mock_launch.assert_called_once_with("https://mail.google.com")

def test_find_recruiter_emails_thread_analysis():
    """Verify semantic classification and structure of recruiter email threads."""
    tool = FindRecruiterEmailsTool()
    res = tool.execute()

    assert res.success is True
    assert "results" in res.data
    results = res.data["results"]
    assert len(results) >= 3

    # Check structure of the generated cards
    for item in results:
        assert "thread_id" in item
        assert "recruiter_name" in item
        assert "company_name" in item
        assert "subject" in item
        assert "status" in item
        assert item["status"] in CATEGORIES
        assert "suggested_next_action" in item
        assert "gmail_link" in item
        assert "mail.google.com/mail" in item["gmail_link"]

def test_semantic_classification_categories():
    """Verify threads are correctly categorized based on sender, length, and content."""
    # 1. Interview invitation
    interview_thread = {
        "id": "t1",
        "messages": [
            {
                "payload": {"headers": [{"name": "From", "value": "recruiter@deepmind.com"}, {"name": "Subject", "value": "Technical Screen"}]},
                "snippet": "We would like to invite you for a 45-min technical interview."
            }
        ]
    }
    insight1 = GmailClient.analyze_thread(interview_thread)
    assert insight1["status"] == "Interview opportunity"
    assert insight1["company_name"] == "Deepmind"

    # 2. Automated acknowledgment from no-reply
    auto_thread = {
        "id": "t2",
        "messages": [
            {
                "payload": {"headers": [{"name": "From", "value": "no-reply@company.com"}, {"name": "Subject", "value": "Application Received"}]},
                "snippet": "Thank you for applying. We have received your application."
            }
        ]
    }
    insight2 = GmailClient.analyze_thread(auto_thread)
    assert insight2["status"] == "Automated acknowledgment"

    # 3. Recruiter replied on multi-message thread
    reply_thread = {
        "id": "t3",
        "messages": [
            {"payload": {"headers": [{"name": "Subject", "value": "Staff Engineer"}]}, "snippet": "Applied"},
            {
                "payload": {"headers": [{"name": "From", "value": "Alex <alex@startup.io>"}, {"name": "Date", "value": "Nov 03, 2026"}]},
                "snippet": "Following up with feedback from our team regarding your application."
            }
        ]
    }
    insight3 = GmailClient.analyze_thread(reply_thread)
    assert insight3["status"] == "Recruiter replied"

@patch("app.tools.gmail.launch_browser_url")
def test_agent_contextual_email_sequence(mock_launch):
    """Verify multi-turn flow: 'Find recruiter responses' -> 'Open that conversation'."""
    agent = DadusAgent()
    sid = "gmail_sequence_session"

    # Turn 1: Find recruiter emails
    res1 = agent.process_input("Find recruiter responses in my Gmail.", session_id=sid)
    assert res1.status == "DONE"
    assert res1.tool_called == "find_recruiter_emails"
    assert "threads" in res1.text.lower() or "recruiter" in res1.text.lower()

    # Turn 2: Contextual reference to open that conversation
    res2 = agent.process_input("Open that conversation.", session_id=sid)
    assert res2.status == "DONE"
    assert res2.tool_called == "open_email_thread"
    mock_launch.assert_called_once()
    assert "mail.google.com/mail" in mock_launch.call_args[0][0]
