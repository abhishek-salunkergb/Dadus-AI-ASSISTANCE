"""Tests for Phase 5 Intelligent Gmail Integration & Recruiter Thread Analysis.
Verifies data integrity, zero fabrication, official API handling, and semantic classification.
"""
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


def test_find_recruiter_emails_unauthenticated_honesty():
    """Verify that when unauthenticated, DADUS returns an honest error without fabricating emails."""
    with patch.object(GmailClient, "is_connected", return_value=False):
        tool = FindRecruiterEmailsTool()
        res = tool.execute()

        assert res.success is False
        assert res.error == "GMAIL_AUTH_REQUIRED"
        assert "not authenticated" in res.message.lower()
        assert res.data.get("results") == []


def test_find_recruiter_emails_empty_inbox_honesty():
    """Verify that when Gmail returns zero matching emails, DADUS returns an honest empty result."""
    with patch.object(GmailClient, "is_connected", return_value=True), \
         patch.object(GmailClient, "fetch_recruiter_threads", return_value=([], None)):
        tool = FindRecruiterEmailsTool()
        res = tool.execute()

        assert res.success is True
        assert res.data["count"] == 0
        assert res.data["results"] == []
        assert "found no recruiter or job-related emails" in res.message.lower()


def test_find_recruiter_emails_auth_expired():
    """Verify that expired credentials return an honest auth expired message."""
    with patch.object(GmailClient, "is_connected", return_value=True), \
         patch.object(GmailClient, "fetch_recruiter_threads", return_value=([], "GMAIL_AUTH_EXPIRED")):
        tool = FindRecruiterEmailsTool()
        res = tool.execute()

        assert res.success is False
        assert res.error == "GMAIL_AUTH_EXPIRED"
        assert "expired" in res.message.lower()


def test_find_recruiter_emails_real_retrieval_and_classification():
    """Verify processing of real Gmail API thread structures without fabrication."""
    real_gmail_threads = [
        {
            "id": "1894a7bc012",
            "messages": [
                {
                    "threadId": "1894a7bc012",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "Jane Doe <jane.recruiter@stripe.com>"},
                            {"name": "Subject", "value": "Stripe: Interview Invitation for Senior Backend Engineer"},
                            {"name": "Date", "value": "Wed, 04 Nov 2026 10:15:00 +0000"}
                        ]
                    },
                    "snippet": "We were very impressed by your background and would love to schedule a technical screen call."
                }
            ]
        },
        {
            "id": "1894a7bc099",
            "messages": [
                {
                    "threadId": "1894a7bc099",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "no-reply@greenhouse.io"},
                            {"name": "Subject", "value": "Thank you for applying to Databricks"},
                            {"name": "Date", "value": "Tue, 03 Nov 2026 14:00:00 +0000"}
                        ]
                    },
                    "snippet": "We have received your application for the Software Engineer role and are reviewing it."
                }
            ]
        }
    ]

    with patch.object(GmailClient, "is_connected", return_value=True), \
         patch.object(GmailClient, "fetch_recruiter_threads", return_value=(real_gmail_threads, None)):
        tool = FindRecruiterEmailsTool()
        res = tool.execute()

        assert res.success is True
        assert res.data["count"] == 2
        results = res.data["results"]

        # Item 1: Stripe interview
        stripe_res = results[0]
        assert stripe_res["thread_id"] == "1894a7bc012"
        assert stripe_res["company_name"] == "Stripe"
        assert stripe_res["recruiter_name"] == "Jane Doe"
        assert stripe_res["sender_email"] == "jane.recruiter@stripe.com"
        assert stripe_res["status"] == "Interview opportunity"
        assert "1894a7bc012" in stripe_res["gmail_link"]

        # Item 2: Automated acknowledgment
        auto_res = results[1]
        assert auto_res["thread_id"] == "1894a7bc099"
        assert auto_res["status"] == "Automated acknowledgment"


def test_semantic_classification_categories():
    """Verify threads are correctly categorized based on sender, length, and content."""
    # 1. Interview invitation
    interview_thread = {
        "id": "t1",
        "messages": [
            {
                "payload": {"headers": [{"name": "From", "value": "recruiter@openai.com"}, {"name": "Subject", "value": "Technical Screen"}]},
                "snippet": "We would like to invite you for a 45-min technical interview."
            }
        ]
    }
    insight1 = GmailClient.analyze_thread(interview_thread)
    assert insight1["status"] == "Interview opportunity"
    assert insight1["company_name"] == "Openai"

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


def test_incomplete_body_graceful_handling():
    """Verify handling when email has missing headers or empty snippet."""
    sparse_thread = {
        "id": "sparse_123",
        "messages": [
            {
                "payload": {"headers": []},
                "snippet": ""
            }
        ]
    }
    insight = GmailClient.analyze_thread(sparse_thread)
    assert insight["thread_id"] == "sparse_123"
    assert insight["subject"] == "No Subject"
    assert insight["status"] == "Uncertain classification"
    assert insight["gmail_link"] == "https://mail.google.com/mail/u/0/#inbox/sparse_123"


@patch("app.tools.gmail.launch_browser_url")
def test_open_email_thread_with_id(mock_launch):
    """Verify opening a specific thread ID in browser."""
    tool = OpenEmailThreadTool()
    res = tool.execute(thread_id="1894a7bc012")
    assert res.success is True
    assert "1894a7bc012" in res.data["url"]
    mock_launch.assert_called_once_with("https://mail.google.com/mail/u/0/#inbox/1894a7bc012")


def test_open_email_thread_unauthenticated():
    """Verify error when thread_id omitted and unauthenticated."""
    with patch.object(GmailClient, "is_connected", return_value=False):
        tool = OpenEmailThreadTool()
        res = tool.execute()
        assert res.success is False
        assert res.error == "THREAD_NOT_SPECIFIED"
