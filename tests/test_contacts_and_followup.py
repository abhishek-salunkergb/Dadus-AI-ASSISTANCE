"""Unit and integration tests for multi-turn app follow-ups and contact disambiguation."""
import pytest
from unittest.mock import patch

from app.database.database import init_db, get_db_context
from app.database.models import Contact
from app.agent.agent import DadusAgent
from app.agent.router import intent_router
from app.tools.contacts import CallContactTool, AddContactTool, DeleteContactTool, ImportContactsTool, find_matching_contacts

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    with get_db_context() as db:
        # Ensure our target test contacts exist
        for name, phone in [
            ("Abhishek Salunke", "+91 98765 43210"),
            ("Abhishek Chavhan", "+91 98765 43211"),
            ("Abhishek Patil", "+91 98765 43212"),
            ("Rahul Sharma", "+91 98765 43213")
        ]:
            existing = db.query(Contact).filter(Contact.name == name).first()
            if not existing:
                db.add(Contact(name=name, phone=phone))
        db.commit()

def test_find_matching_contacts_multiple():
    matches = find_matching_contacts("Abhishek")
    names = [c.name for c in matches]
    assert len(matches) >= 3
    assert "Abhishek Salunke" in names
    assert "Abhishek Chavhan" in names
    assert "Abhishek Patil" in names

def test_find_matching_contacts_single():
    matches = find_matching_contacts("Rahul")
    assert len(matches) == 1
    assert matches[0].name == "Rahul Sharma"

def test_find_matching_contacts_by_surname():
    matches = find_matching_contacts("Chavhan")
    assert len(matches) == 1
    assert matches[0].name == "Abhishek Chavhan"

@patch("os.startfile")
@patch("webbrowser.open")
def test_open_youtube_direct_launch(mock_web, mock_startfile):
    agent = DadusAgent()
    session = agent.get_or_create_session("yt_session")

    # When user says "open youtube", it just opens it without asking which song to play
    res1 = agent.process_input("open youtube", session_id="yt_session")
    assert res1.status == "DONE"
    assert "opening youtube" in res1.text.lower()
    assert "which song" not in res1.text.lower()
    assert res1.needs_clarification is False
    assert session.pending_clarification is None

@patch("os.startfile")
def test_call_contact_disambiguation_multi_turn(mock_startfile):
    agent = DadusAgent()
    session = agent.get_or_create_session("call_session")

    # Turn 1: User says "call abhishek"
    res1 = agent.process_input("call abhishek", session_id="call_session")
    assert res1.needs_clarification is True
    assert res1.status == "WAITING_CLARIFICATION"
    assert "which abhishek, boss?" in res1.text.lower()
    assert "abhishek salunke" in res1.text.lower()
    assert "abhishek chavhan" in res1.text.lower()
    assert "abhishek patil" in res1.text.lower()
    assert session.pending_clarification is not None
    assert session.pending_clarification.clarification_type == "contact_choice"

    # Turn 2: User specifies "Abhishek Chavhan"
    res2 = agent.process_input("Abhishek Chavhan", session_id="call_session")
    assert res2.status == "DONE"
    assert res2.tool_called == "call_contact"
    assert "Calling Abhishek Chavhan" in res2.text
    assert "+91 98765 43211" in res2.text
    assert session.pending_clarification is None

@patch("os.startfile")
def test_call_contact_disambiguation_by_surname(mock_startfile):
    agent = DadusAgent()
    session = agent.get_or_create_session("call_surname_session")

    # Turn 1: User says "call abhishek"
    agent.process_input("call abhishek", session_id="call_surname_session")

    # Turn 2: User just says the surname "Chavhan"
    res2 = agent.process_input("Chavhan", session_id="call_surname_session")
    assert res2.status == "DONE"
    assert "Calling Abhishek Chavhan" in res2.text

@patch("os.startfile")
def test_call_single_contact_direct(mock_startfile):
    agent = DadusAgent()
    # "call rahul" matches only Rahul Sharma, should call immediately
    res = agent.process_input("call rahul", session_id="direct_call_session")
    assert res.status == "DONE"
    assert res.tool_called == "call_contact"
    assert "Calling Rahul Sharma" in res.text
    assert res.needs_clarification is False

def test_call_contact_not_found():
    agent = DadusAgent()
    res = agent.process_input("call non_existent_person_xyz", session_id="not_found_session")
    assert "couldn't find 'non_existent_person_xyz'" in res.text.lower()
    assert res.needs_clarification is False

def test_clarification_cancellation():
    agent = DadusAgent()
    session = agent.get_or_create_session("cancel_session")

    # Turn 1: User says "call abhishek"
    agent.process_input("call abhishek", session_id="cancel_session")
    assert session.pending_clarification is not None

    # Turn 2: User cancels
    res = agent.process_input("cancel", session_id="cancel_session")
    assert "cancelled" in res.text.lower()
    assert session.pending_clarification is None


def test_delete_contact_tool():
    add_tool = AddContactTool()
    add_tool.execute(name="Test User", phone="+1 555 123 4567")

    del_tool = DeleteContactTool()
    res = del_tool.execute(contact_name_or_id="Test User")
    assert res.success is True
    assert "Deleted Test User" in res.message

    with get_db_context() as db:
        remaining = db.query(Contact).filter(Contact.name == "Test User").first()
        assert remaining is None


def test_import_contacts_vcf(tmp_path):
    vcf_content = (
        "BEGIN:VCARD\n"
        "VERSION:3.0\n"
        "FN:Elon Musk\n"
        "TEL:+1 555 999 8888\n"
        "EMAIL:elon@x.com\n"
        "END:VCARD\n"
        "BEGIN:VCARD\n"
        "VERSION:3.0\n"
        "FN:Satya Nadella\n"
        "TEL:+1 555 777 6666\n"
        "EMAIL:satya@microsoft.com\n"
        "END:VCARD\n"
    )
    vcf_file = tmp_path / "contacts.vcf"
    vcf_file.write_text(vcf_content, encoding="utf-8")

    tool = ImportContactsTool()
    res = tool.execute(file_path=str(vcf_file))
    assert res.success is True
    assert res.data["imported_count"] == 2

    with get_db_context() as db:
        elon = db.query(Contact).filter(Contact.name == "Elon Musk").first()
        satya = db.query(Contact).filter(Contact.name == "Satya Nadella").first()
        assert elon is not None
        assert elon.phone == "+1 555 999 8888"
        assert satya is not None
        assert satya.email == "satya@microsoft.com"

