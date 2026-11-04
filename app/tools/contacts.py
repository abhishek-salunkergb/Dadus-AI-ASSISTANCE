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


# ==========================================
# Tool: delete_contact
# ==========================================
class DeleteContactInput(BaseModel):
    contact_name_or_id: str = Field(description="Name or ID of the contact to delete")

class DeleteContactTool(BaseTool):
    name = "delete_contact"
    description = "Removes a contact from the address book."
    permission_level = PermissionLevel.SAFE
    args_schema = DeleteContactInput

    def execute(self, contact_name_or_id: str) -> ToolResult:
        with get_db_context() as db:
            query = contact_name_or_id.strip()
            target = None
            if query.isdigit():
                target = db.query(Contact).filter(Contact.id == int(query)).first()
            if not target:
                matches = find_matching_contacts(query)
                if matches:
                    target = db.query(Contact).filter(Contact.id == matches[0].id).first()

            if not target:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    message=f"Boss, I couldn't find '{contact_name_or_id}' in your contacts to delete.",
                    error="CONTACT_NOT_FOUND"
                )

            name = target.name
            db.delete(target)
            db.commit()
            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Deleted {name} from your contacts, boss.",
                data={"deleted_contact": name}
            )


# ==========================================
# Tool: import_contacts
# ==========================================
class ImportContactsInput(BaseModel):
    file_path: Optional[str] = Field(default=None, description="Path to a .vcf (vCard) or .csv contacts file to import.")

class ImportContactsTool(BaseTool):
    name = "import_contacts"
    description = "Imports real contacts from a vCard (.vcf) or CSV file from your computer."
    permission_level = PermissionLevel.SAFE
    args_schema = ImportContactsInput

    def execute(self, file_path: Optional[str] = None) -> ToolResult:
        import csv
        from pathlib import Path

        candidate_paths = []
        if file_path:
            candidate_paths.append(Path(file_path))
        else:
            # Search common user directories for contact files
            search_roots = [
                Path.home() / "Downloads",
                Path.home() / "Documents",
                Path.home() / "Desktop",
                Path.cwd()
            ]
            for root in search_roots:
                if root.exists():
                    for pattern in ["*.vcf", "*contacts*.csv"]:
                        candidate_paths.extend(root.glob(pattern))

        if not candidate_paths or not candidate_paths[0].exists():
            return ToolResult(
                tool_name=self.name,
                success=False,
                message="Boss, I couldn't find a contacts file (.vcf or .csv) to import. Please place your exported contacts in Downloads or Documents.",
                error="FILE_NOT_FOUND"
            )

        target_file = candidate_paths[0]
        imported_contacts = []

        try:
            if target_file.suffix.lower() == ".vcf":
                content = target_file.read_text(encoding="utf-8", errors="ignore")
                cards = content.split("BEGIN:VCARD")
                for card in cards:
                    if not card.strip():
                        continue
                    name = ""
                    phone = ""
                    email = ""
                    for line in card.splitlines():
                        line = line.strip()
                        if line.startswith("FN:") or line.startswith("FN;"):
                            name = line.split(":", 1)[1].strip()
                        elif (line.startswith("TEL:") or line.startswith("TEL;")) and not phone:
                            phone = line.split(":", 1)[1].strip()
                        elif (line.startswith("EMAIL:") or line.startswith("EMAIL;")) and not email:
                            email = line.split(":", 1)[1].strip()
                    if name and phone:
                        imported_contacts.append({"name": name, "phone": phone, "email": email or None})
            elif target_file.suffix.lower() == ".csv":
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get("Name") or row.get("Full Name") or (row.get("First Name", "") + " " + row.get("Last Name", ""))
                        phone = row.get("Phone") or row.get("Phone Number") or row.get("Mobile") or row.get("Phone 1 - Value")
                        email = row.get("Email") or row.get("E-mail Address") or row.get("E-mail 1 - Value")
                        if name and phone:
                            imported_contacts.append({"name": name.strip(), "phone": phone.strip(), "email": (email or "").strip() or None})

            if not imported_contacts:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    message=f"Boss, '{target_file.name}' was found but contained no valid contact entries.",
                    data={"imported_count": 0}
                )

            with get_db_context() as db:
                added_count = 0
                for c in imported_contacts:
                    existing = db.query(Contact).filter(Contact.name == c["name"]).first()
                    if not existing:
                        db.add(Contact(name=c["name"], phone=c["phone"], email=c["email"]))
                        added_count += 1
                db.commit()

            return ToolResult(
                tool_name=self.name,
                success=True,
                message=f"Boss, successfully imported {added_count} contacts from '{target_file.name}'.",
                data={"imported_count": added_count, "file": str(target_file)}
            )
        except Exception as exc:
            logger.error(f"Error importing contacts from {target_file}: {exc}")
            return ToolResult(
                tool_name=self.name,
                success=False,
                message=f"Boss, an error occurred importing contacts: {str(exc)}",
                error=str(exc)
            )
