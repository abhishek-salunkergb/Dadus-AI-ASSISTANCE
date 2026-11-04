"""Contact management, calling, and messaging tools for DADUS."""
import os
import re
import webbrowser
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolResult
from app.security.permissions import PermissionLevel
from app.database.database import get_db_context
from app.database.models import Contact

logger = logging.getLogger("DADUS.Contacts")

class ContactDTO(BaseModel):
    id: Optional[int] = None
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    relationship: Optional[str] = None

    def to_dict(self):
        return self.model_dump()

def _normalize_name(name: str) -> str:
    return re.sub(r"[^\w\s]", "", name.lower()).strip()

def find_matching_contacts(query: str) -> List[ContactDTO]:
    """Finds contacts matching full name, first name, last name, or substring."""
    clean_q = _normalize_name(query)
    if not clean_q:
        return []

    with get_db_context() as db:
        contacts = db.query(Contact).all()
        dtos = [
            ContactDTO(
                id=c.id,
                name=c.name,
                phone=c.phone,
                email=c.email,
                relationship=c.relationship
            )
            for c in contacts
        ]
        exact_matches = []
        partial_matches = []

        for c in dtos:
            c_norm = _normalize_name(c.name)
            # Exact match
            if c_norm == clean_q:
                exact_matches.append(c)
                continue
            
            # Substring match (e.g. "Abhishek" in "Abhishek Chavhan")
            if clean_q in c_norm:
                partial_matches.append(c)
                continue

            # Word match (e.g. query "Chavhan" matches "Abhishek Chavhan")
            words = c_norm.split()
            if any(clean_q == w for w in words):
                partial_matches.append(c)
                continue

        if exact_matches:
            return exact_matches
        return partial_matches


# ==========================================
# Tool: call_contact
# ==========================================
class CallContactInput(BaseModel):
    contact_name: str = Field(description="Name of the person or contact to call, e.g. 'Abhishek', 'Abhishek Chavhan'")

class CallContactTool(BaseTool):
    name = "call_contact"
    description = "Initiates a voice or phone call to a contact. Automatically disambiguates if multiple contacts share the same name."
    permission_level = PermissionLevel.SAFE
    args_schema = CallContactInput

    def execute(self, contact_name: str) -> ToolResult:
        logger.info(f"Executing call_contact for '{contact_name}'")
        matches = find_matching_contacts(contact_name)

        # Case 1: No contact found
        if not matches:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't find '{contact_name}' in your contacts. Would you like me to add them?",
                error="CONTACT_NOT_FOUND"
            )

        # Case 2: Multiple matching contacts (Disambiguation required)
        if len(matches) > 1:
            opt_names = [c.name for c in matches]
            if len(opt_names) == 2:
                opts_text = f"{opt_names[0]} or {opt_names[1]}"
            else:
                opts_text = f"{', '.join(opt_names[:-1])}, or {opt_names[-1]}"

            name_title = contact_name.strip().title()
            msg = f"Which {name_title}, boss? {opts_text}?"
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                needs_clarification=True,
                clarification_type="contact_choice",
                options=opt_names,
                data={"matches": [c.to_dict() for c in matches]}
            )

        # Case 3: Exactly one matching contact
        contact = matches[0]
        phone = contact.phone or ""
        clean_phone = re.sub(r"[^\d+]", "", phone)

        # Trigger Windows system dialer / Phone Link via tel: protocol
        if clean_phone:
            try:
                os.startfile(f"tel:{clean_phone}")
            except Exception as ex:
                logger.warning(f"Could not open tel: protocol for {clean_phone}: {ex}")

        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Calling {contact.name} ({contact.phone}) now, boss.",
            data={"contact": contact.to_dict(), "tel_uri": f"tel:{clean_phone}"}
        )


# ==========================================
# Tool: message_contact
# ==========================================
class MessageContactInput(BaseModel):
    contact_name: str = Field(description="Name of the contact to message, e.g. 'Abhishek', 'Rahul'")
    message_text: Optional[str] = Field(default=None, description="Optional text message to send")

class MessageContactTool(BaseTool):
    name = "message_contact"
    description = "Opens a chat or messaging window with a contact on WhatsApp or default messaging app."
    permission_level = PermissionLevel.SAFE
    args_schema = MessageContactInput

    def execute(self, contact_name: str, message_text: Optional[str] = None) -> ToolResult:
        logger.info(f"Executing message_contact for '{contact_name}'")
        matches = find_matching_contacts(contact_name)

        if not matches:
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, I couldn't find '{contact_name}' in your contacts.",
                error="CONTACT_NOT_FOUND"
            )

        if len(matches) > 1:
            opt_names = [c.name for c in matches]
            if len(opt_names) == 2:
                opts_text = f"{opt_names[0]} or {opt_names[1]}"
            else:
                opts_text = f"{', '.join(opt_names[:-1])}, or {opt_names[-1]}"

            name_title = contact_name.strip().title()
            msg = f"Which {name_title}, boss? {opts_text}?"
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=msg,
                needs_clarification=True,
                clarification_type="contact_choice",
                options=opt_names,
                follow_up_tool=self.name,
                data={"matches": [c.to_dict() for c in matches]}
            )

        contact = matches[0]
        clean_phone = re.sub(r"[^\d]", "", contact.phone or "")
        
        # Open WhatsApp Web or application chat
        wa_url = f"https://wa.me/{clean_phone}" if clean_phone else "https://web.whatsapp.com"
        try:
            webbrowser.open(wa_url)
        except Exception as ex:
            logger.warning(f"Could not open WhatsApp URL {wa_url}: {ex}")

        return ToolResult(
            tool_name=self.name,
            success=True,
            message=f"Opening chat with {contact.name}, boss.",
            data={"contact": contact.to_dict(), "url": wa_url}
        )


# ==========================================
# Tool: list_contacts
# ==========================================
class ListContactsInput(BaseModel):
    pass

class ListContactsTool(BaseTool):
    name = "list_contacts"
    description = "Lists all saved contacts in the user's address book."
    permission_level = PermissionLevel.SAFE
    args_schema = ListContactsInput

    def execute(self) -> ToolResult:
        with get_db_context() as db:
            contacts = db.query(Contact).order_by(Contact.name).all()
            if not contacts:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message="Boss, your contact list is currently empty.",
                    data={"contacts": []}
                )

            summary = ", ".join([f"{c.name} ({c.phone or 'no number'})" for c in contacts])
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, here are your contacts: {summary}.",
                data={"contacts": [c.to_dict() for c in contacts]}
            )


# ==========================================
# Tool: add_contact
# ==========================================
class AddContactInput(BaseModel):
    name: str = Field(description="Full name of the contact")
    phone: str = Field(description="Phone number with country code")
    email: Optional[str] = Field(default=None, description="Optional email address")
    relationship: Optional[str] = Field(default=None, description="Relationship, e.g. friend, colleague, family")

class AddContactTool(BaseTool):
    name = "add_contact"
    description = "Adds a new contact to the address book."
    permission_level = PermissionLevel.SAFE
    args_schema = AddContactInput

    def execute(self, name: str, phone: str, email: Optional[str] = None, relationship: Optional[str] = None) -> ToolResult:
        with get_db_context() as db:
            contact = Contact(
                name=name.strip().title(),
                phone=phone.strip(),
                email=email.strip().lower() if email else None,
                relationship=relationship.strip().lower() if relationship else None
            )
            db.add(contact)
            db.commit()
            db.refresh(contact)
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Added {contact.name} ({contact.phone}) to your contacts, boss.",
                data={"contact": contact.to_dict()}
            )
