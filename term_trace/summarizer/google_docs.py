#!/usr/bin/env python3
from __future__ import annotations
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

Entry = Dict[str, Any]


class GoogleDocsLogger:
    """
    Single Google Doc logger for term-trace sessions:
    - Title
    - Summary section
    - Full Log section (new page)
    """

    SCOPES: list[str] = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]

    def __init__(
        self,
        client_secret_path: str,
        doc_title: str = "term-trace Session",
        workspace: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> None:
        self.client_secret_path = Path(client_secret_path)
        if not self.client_secret_path.exists():
            raise FileNotFoundError(
                f"Client secret file not found: {client_secret_path}")

        self.doc_title = doc_title
        self.workspace = workspace or "default"

        print("Authorizing with Google...")
        self.creds = self._authorize_user()
        self.docs_service = build("docs", "v1", credentials=self.creds)
        self.drive_service = build("drive", "v3", credentials=self.creds)

        self.doc_id = self._open_or_create_doc(
            f"{doc_title} - {self.workspace}", folder_id)
        self.doc_url = f"https://docs.google.com/document/d/{self.doc_id}/edit"

        # Only initialize (which clears and writes the skeleton) when the
        # document does not already have the expected sections. This prevents
        # overwriting existing logs/summaries when opening an already-initialized doc.
        try:
            if not self._has_expected_sections():
                self._init_doc_structure()
            else:
                print(
                    "Document already has expected sections; leaving existing content intact.")
        except Exception:
            # If anything goes wrong while inspecting the doc, fall back to
            # initializing to ensure a valid structure.
            print("Unable to verify document structure; initializing document.")
            self._init_doc_structure()

    # --------------------------- Authorization ---------------------------
    def _authorize_user(self):
        from term_trace.config import Config
        token_path = Config.GOOGLE_TOKEN_PATH
        token_path.parent.mkdir(parents=True, exist_ok=True)
        creds = None

        if token_path.exists():
            with token_path.open("rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_path), self.SCOPES)
                creds = flow.run_local_server(port=0)

            with token_path.open("wb") as token:
                pickle.dump(creds, token)

        return creds

    # --------------------------- Document Creation ---------------------------
    def _open_or_create_doc(self, name: str, folder_id: Optional[str] = None) -> str:
        """Find or create a Google Doc, folder-aware."""
        try:
            query = f"name='{name}' and mimeType='application/vnd.google-apps.document'"
            if folder_id:
                query += f" and '{folder_id}' in parents"

            result = (
                self.drive_service.files()
                .list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True)
                .execute()
            )
            items = result.get("files", [])
            if items:
                print(f"Found existing document: {name}")
                return items[0]["id"]

            # Verify folder
            if folder_id:
                try:
                    self.drive_service.files().get(fileId=folder_id, supportsAllDrives=True).execute()
                except Exception as e:
                    print(
                        f"Warning: Folder {folder_id} not accessible. Creating doc in root. ({e})")
                    folder_id = None

            body = {"name": name,
                    "mimeType": "application/vnd.google-apps.document"}
            if folder_id:
                body["parents"] = [folder_id]

            doc = self.drive_service.files().create(
                body=body, fields="id", supportsAllDrives=True).execute()
            print(f"Created document '{name}' (ID: {doc['id']})")
            return doc["id"]

        except Exception as e:
            print(f"Error creating/accessing document '{name}': {e}")
            raise

    # --------------------------- Document Layout ---------------------------

    def _init_doc_structure(self) -> None:
        """Initialize document layout: TOC, Summary, Full Log with page break."""
        # Step 1: clear existing content (if any) and insert a single block of text
        doc = self.docs_service.documents().get(documentId=self.doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        requests: List[Dict[str, Any]] = []
        if content:
            last_elem = content[-1]
            end_index = last_elem.get("endIndex", 1)
            if end_index > 2:
                requests.append({
                    "deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}
                })

    # Build a simple initial document text. We'll apply styles
    # in a follow-up batch once we can read real indices.
        parts = [
            f"{self.doc_title} ({self.workspace})\n",
            "\n",
            "Summary\n",
            "Session summary will appear here.\n",
            "\n",
            "Full Log\n",
            "Session logs will appear here.\n",
        ]

        full_text = "".join(parts)
        requests.append(
            {"insertText": {"location": {"index": 1}, "text": full_text}})

        # Execute the insert, then fetch the doc to locate paragraph indices
        if requests:
            self.docs_service.documents().batchUpdate(documentId=self.doc_id,
                                                      body={"requests": requests}).execute()

        # Step 2: read the document to find paragraph indices and apply styles + TOC
        doc = self.docs_service.documents().get(documentId=self.doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        # Helper to find paragraph by text prefix
        def find_paragraph_prefix(prefix: str):
            for item in content:
                para = item.get("paragraph", {})
                elements = para.get("elements", [])
                text = "".join(e.get("textRun", {}).get("content", "")
                               for e in elements)
                if text.strip().startswith(prefix):
                    return item.get("startIndex", 1), item.get("endIndex", 1)
            return None, None

        title_start, title_end = find_paragraph_prefix(self.doc_title)
        summary_start, summary_end = find_paragraph_prefix("Summary")
        fulllog_start, fulllog_end = find_paragraph_prefix("Full Log")

        followups: List[Dict[str, Any]] = []

        if title_start and title_end:
            followups.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": title_start, "endIndex": title_end},
                    "paragraphStyle": {"namedStyleType": "TITLE"},
                    "fields": "namedStyleType",
                }
            })

        if summary_start and summary_end:
            followups.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": summary_start, "endIndex": summary_end},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            })

        if fulllog_start and fulllog_end:
            # Insert a page break before the Full Log heading
            followups.append(
                {"insertPageBreak": {"location": {"index": fulllog_start}}})
            followups.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": fulllog_start, "endIndex": fulllog_end},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            })

        if followups:
            try:
                self.docs_service.documents().batchUpdate(documentId=self.doc_id,
                                                          body={"requests": followups}).execute()
            except Exception as e:
                print(
                    f"Warning: failed to apply final layout changes (styles/page break): {e}")

    # --------------------------- Section Updates ---------------------------
    def _replace_section_content(self, heading: str, new_text: str):
        """Replace section content, create heading if missing. Handles empty docs safely."""
        doc = self.docs_service.documents().get(documentId=self.doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        start_index = None
        end_index = None

        for i, item in enumerate(content):
            para = item.get("paragraph", {})
            style = para.get("paragraphStyle", {})
            elements = para.get("elements", [])

            if style.get("namedStyleType") == "HEADING_1" and elements:
                text_run = "".join(elem.get("textRun", {}).get(
                    "content", "") for elem in elements).strip()
                if heading.lower() in text_run.lower():
                    start_index = item.get("endIndex", 1)
                    for next_item in content[i + 1:]:
                        next_para = next_item.get("paragraph", {})
                        next_style = next_para.get("paragraphStyle", {})
                        if next_style.get("namedStyleType") == "HEADING_1":
                            end_index = next_item.get("startIndex", 1) - 1
                            break
                    if end_index is None:
                        end_index = content[-1].get("endIndex", 1) - 1
                    break

        requests = []
        if start_index is not None:
            requests.append({"deleteContentRange": {
                            "range": {"startIndex": start_index, "endIndex": end_index}}})
            insert_index = start_index
        else:
            print(f"Warning: Section '{heading}' not found. Appending at end.")
            insert_index = 1 if not content else max(
                1, content[-1].get("endIndex", 1) - 1)
            # Insert heading
            requests.append(
                {"insertText": {"location": {"index": insert_index}, "text": f"\n{heading}\n"}})
            requests.append({"updateParagraphStyle": {"range": {"startIndex": insert_index, "endIndex": insert_index + len(heading) + 1},
                                                      "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                                      "fields": "namedStyleType"}})
            insert_index += len(heading) + 2

        # Insert new content
        requests.append({"insertText": {"location": {
                        "index": insert_index}, "text": "\n" + new_text + "\n"}})
        self.docs_service.documents().batchUpdate(documentId=self.doc_id,
                                                  body={"requests": requests}).execute()

    def _has_expected_sections(self) -> bool:
        """Return True if the document contains both Summary and Full Log headings (HEADING_1).

        This is the heuristic used to decide whether to append to sections or
        reset the document structure and start fresh.
        """
        doc = self.docs_service.documents().get(documentId=self.doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        found_summary = False
        found_full = False
        for item in content:
            para = item.get("paragraph", {})
            style = para.get("paragraphStyle", {})
            elements = para.get("elements", [])
            if style.get("namedStyleType") == "HEADING_1" and elements:
                text_run = "".join(e.get("textRun", {}).get(
                    "content", "") for e in elements).strip()
                if text_run.lower().startswith("summary"):
                    found_summary = True
                if text_run.lower().startswith("full log"):
                    found_full = True
        return found_summary and found_full

    def _append_section_content(self, heading: str, new_text: str) -> bool:
        """Append new_text to the named section (HEADING_1 'heading').

        Returns True on success; False if heading not found.
        Inserts a timestamped separator before the appended text.
        """
        doc = self.docs_service.documents().get(documentId=self.doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        # Locate the heading paragraph
        heading_index = None
        section_end = None
        for i, item in enumerate(content):
            para = item.get("paragraph", {})
            style = para.get("paragraphStyle", {})
            elements = para.get("elements", [])
            if style.get("namedStyleType") == "HEADING_1" and elements:
                text_run = "".join(e.get("textRun", {}).get(
                    "content", "") for e in elements).strip()
                if heading.lower() in text_run.lower():
                    # start of section is immediately after this paragraph
                    heading_index = i
                    # find next HEADING_1 to determine end, otherwise end of doc
                    for next_item in content[i + 1:]:
                        next_para = next_item.get("paragraph", {})
                        next_style = next_para.get("paragraphStyle", {})
                        if next_style.get("namedStyleType") == "HEADING_1":
                            section_end = next_item.get("startIndex", 1) - 1
                            break
                    if section_end is None:
                        section_end = content[-1].get("endIndex", 1) - 1
                    break

        if heading_index is None:
            return False

        # Insert timestamped separator and new text at section_end
        ts = datetime.utcnow().isoformat() + "Z"
        separator = f"\n──── {ts} ────\n"
        body_text = separator + new_text + "\n"

        requests = [
            {"insertText": {"location": {"index": section_end}, "text": body_text}}
        ]

        try:
            self.docs_service.documents().batchUpdate(documentId=self.doc_id,
                                                      body={"requests": requests}).execute()
            return True
        except Exception as e:
            print(f"Error appending to section '{heading}': {e}")
            return False

    # --------------------------- Public Methods ---------------------------
    def write_summary(self, summary_text: str) -> None:
        # If document doesn't contain expected headings, reinitialize it
        if not self._has_expected_sections():
            print("Document missing expected sections; reinitializing structure.")
            self._init_doc_structure()

        appended = self._append_section_content("Summary", summary_text)
        if not appended:
            # Fallback to replacing the section if append failed
            self._replace_section_content("Summary", summary_text)

    def get_doc_url(self) -> str:
        """Get the URL to the Google Doc."""
        return self.doc_url

    def _format_timestamp(self, ts_str: str) -> str:
        """Convert ISO timestamp to local timezone with nice formatting."""
        try:
            # Parse ISO format timestamp (assumed to be UTC)
            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            # Convert to local timezone
            local_dt = dt.astimezone()
            # Format as: Nov 28, 16:45:30
            return local_dt.strftime("%b %d, %H:%M:%S")
        except Exception:
            return ts_str

    def write_entries(self, entries: List[Entry]) -> None:
        """Format entries in terminal-style with colors and monospace font."""
        if not self._has_expected_sections():
            print("Document missing expected sections; reinitializing structure.")
            self._init_doc_structure()

        # Build the content with styled text requests
        doc = self.docs_service.documents().get(documentId=self.doc_id).execute()
        content = doc.get("body", {}).get("content", [])

        # Find the Full Log section end index
        section_end = None
        for i, item in enumerate(content):
            para = item.get("paragraph", {})
            style = para.get("paragraphStyle", {})
            elements = para.get("elements", [])
            if style.get("namedStyleType") == "HEADING_1" and elements:
                text_run = "".join(e.get("textRun", {}).get(
                    "content", "") for e in elements).strip()
                if "full log" in text_run.lower():
                    # Find next heading or end of doc
                    for next_item in content[i + 1:]:
                        next_para = next_item.get("paragraph", {})
                        next_style = next_para.get("paragraphStyle", {})
                        if next_style.get("namedStyleType") == "HEADING_1":
                            section_end = next_item.get("startIndex", 1) - 1
                            break
                    if section_end is None:
                        section_end = content[-1].get("endIndex", 1) - 1
                    break

        if section_end is None:
            print("Warning: Full Log section not found")
            return

        requests = []
        insert_index = section_end

        for e in entries:
            ts_original = e.get('timestamp', '')
            ts_formatted = self._format_timestamp(ts_original)

            if e.get("type") == "note":
                # Format: [timestamp] NOTE: text
                note_text = f"[{ts_formatted}] NOTE: {e['text']}\n\n"

                requests.append(
                    {"insertText": {"location": {"index": insert_index}, "text": note_text}})

                # Style timestamp in gray
                ts_end = insert_index + len(f"[{ts_formatted}]")
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": insert_index, "endIndex": ts_end},
                        "textStyle": {
                            "foregroundColor": {"color": {"rgbColor": {"red": 0.45, "green": 0.45, "blue": 0.45}}},
                            "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                            "fontSize": {"magnitude": 10, "unit": "PT"}
                        },
                        "fields": "foregroundColor,weightedFontFamily,fontSize"
                    }
                })

                # Style NOTE: in orange
                note_start = ts_end + 1
                note_end = note_start + 5  # "NOTE:"
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": note_start, "endIndex": note_end},
                        "textStyle": {
                            "foregroundColor": {"color": {"rgbColor": {"red": 0.8, "green": 0.5, "blue": 0.0}}},
                            "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                            "fontSize": {"magnitude": 10, "unit": "PT"},
                            "bold": True
                        },
                        "fields": "foregroundColor,weightedFontFamily,fontSize,bold"
                    }
                })

                # Style rest of note text in default monospace
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": note_end, "endIndex": insert_index + len(note_text) - 2},
                        "textStyle": {
                            "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                            "fontSize": {"magnitude": 10, "unit": "PT"}
                        },
                        "fields": "weightedFontFamily,fontSize"
                    }
                })

                insert_index += len(note_text)
            else:
                # Format command entry
                cmd = e.get('command', '')
                output = e.get('output', '').rstrip()
                exit_code = e.get('exit_code', '')

                # Build command line: [timestamp] $ command
                cmd_line = f"[{ts_formatted}] $ {cmd}\n"
                cmd_start = insert_index
                requests.append(
                    {"insertText": {"location": {"index": insert_index}, "text": cmd_line}})

                # Style timestamp in gray
                ts_end = insert_index + len(f"[{ts_formatted}]")
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": insert_index, "endIndex": ts_end},
                        "textStyle": {
                            "foregroundColor": {"color": {"rgbColor": {"red": 0.45, "green": 0.45, "blue": 0.45}}},
                            "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                            "fontSize": {"magnitude": 10, "unit": "PT"}
                        },
                        "fields": "foregroundColor,weightedFontFamily,fontSize"
                    }
                })

                # Style $ in green
                dollar_start = ts_end + 1
                dollar_end = dollar_start + 1
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": dollar_start, "endIndex": dollar_end},
                        "textStyle": {
                            "foregroundColor": {"color": {"rgbColor": {"red": 0.13, "green": 0.59, "blue": 0.13}}},
                            "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                            "fontSize": {"magnitude": 11, "unit": "PT"},
                            "bold": True
                        },
                        "fields": "foregroundColor,weightedFontFamily,fontSize,bold"
                    }
                })

                # Style command text in blue
                cmd_text_start = dollar_end + 1
                cmd_text_end = insert_index + len(cmd_line) - 1
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": cmd_text_start, "endIndex": cmd_text_end},
                        "textStyle": {
                            "foregroundColor": {"color": {"rgbColor": {"red": 0.0, "green": 0.4, "blue": 0.8}}},
                            "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                            "fontSize": {"magnitude": 10, "unit": "PT"}
                        },
                        "fields": "foregroundColor,weightedFontFamily,fontSize"
                    }
                })

                insert_index += len(cmd_line)

                # Add output
                if output:
                    output_lines = output.split('\n')
                    indented_output = '\n'.join(
                        '    ' + line for line in output_lines) + '\n'
                    requests.append(
                        {"insertText": {"location": {"index": insert_index}, "text": indented_output}})

                    # Style output in darker gray monospace
                    requests.append({
                        "updateTextStyle": {
                            "range": {"startIndex": insert_index, "endIndex": insert_index + len(indented_output) - 1},
                            "textStyle": {
                                "foregroundColor": {"color": {"rgbColor": {"red": 0.35, "green": 0.35, "blue": 0.35}}},
                                "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                                "fontSize": {"magnitude": 9, "unit": "PT"}
                            },
                            "fields": "foregroundColor,weightedFontFamily,fontSize"
                        }
                    })

                    insert_index += len(indented_output)

                # Add exit code if non-zero (red)
                if exit_code != 0:
                    exit_text = f"    [Exit code: {exit_code}]\n"
                    requests.append(
                        {"insertText": {"location": {"index": insert_index}, "text": exit_text}})

                    requests.append({
                        "updateTextStyle": {
                            "range": {"startIndex": insert_index, "endIndex": insert_index + len(exit_text) - 1},
                            "textStyle": {
                                "foregroundColor": {"color": {"rgbColor": {"red": 0.8, "green": 0.0, "blue": 0.0}}},
                                "weightedFontFamily": {"fontFamily": "Roboto Mono"},
                                "fontSize": {"magnitude": 9, "unit": "PT"},
                                "bold": True
                            },
                            "fields": "foregroundColor,weightedFontFamily,fontSize,bold"
                        }
                    })

                    insert_index += len(exit_text)

                # Add blank line separator
                requests.append(
                    {"insertText": {"location": {"index": insert_index}, "text": "\n"}})
                insert_index += 1

        # Execute all styling requests in one batch
        if requests:
            self.docs_service.documents().batchUpdate(
                documentId=self.doc_id,
                body={"requests": requests}
            ).execute()
