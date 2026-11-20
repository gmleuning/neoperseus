import re
from pathlib import Path

def split_plays(input_filepath: str, output_dir: str = "split_plays"):
    text = Path(input_filepath).read_text(encoding="utf-8")
    
    # Normalize line endings
    text = text.replace("\r\n", "\n")

    # 1. Isolate the major top-level sections: # contents, #plays, and Textual Notes
    # Matches "# contents", "#plays" (or "# plays"), and "# Textual Notes" (or "## Textual Notes")
    contents_match = re.search(r"(?im)^#\s*contents\s*\n(.*?)(?=\n#\s*plays)", text, re.DOTALL)
    plays_match = re.search(r"(?im)^#\s*plays\s*\n(.*?)(?=\n#{1,2}\s*textual\s+notes)", text, re.DOTALL)
    notes_match = re.search(r"(?im)^#{1,2}\s*textual\s+notes\s*\n(.*)$", text, re.DOTALL)

    if not (contents_match and plays_match):
        raise ValueError("Could not locate '# contents' or '#plays' headers in the file.")

    contents_block = contents_match.group(1)
    plays_block = plays_match.group(1)
    notes_block = notes_match.group(1) if notes_match else ""

    # 2. Parse metadata (Author, Title, Translator) from # contents
    # Pattern looks for: "AUTHOR: Play Title" followed by "Translated by Translator"
    meta_pattern = re.compile(
        r"^([A-Z\s]+?):\s*(.+?)\n+Translated by\s+(.+?)$",
        re.MULTILINE
    )
    
    plays_metadata = []
    for match in meta_pattern.finditer(contents_block):
        author = match.group(1).strip().title()
        title = match.group(2).strip()
        translator = match.group(3).strip()
        plays_metadata.append({
            "author": author,
            "title": title,
            "translator": translator,
            "norm_title": title.upper()
        })

    # 3. Split the #plays block by level-2 headers (## PLAY TITLE)
    raw_play_sections = re.split(r"(?m)^##\s+", plays_block.strip())
    play_texts = {}
    
    for section in raw_play_sections:
        if not section.strip():
            continue
        lines = section.split("\n", 1)
        header_title = lines[0].strip().upper()
        # Re-attach the '## ' header to preserve original markdown hierarchy
        body = f"## {section.strip()}"
        play_texts[header_title] = body

    # 4. Split the Textual Notes section by play subheadings (## or ### PLAY TITLE)
    notes_by_play = {}
    if notes_block:
        # Adjust regex here if notes are separated by bold text instead of ## or ###
        notes_split_pattern = r"(?m)^#{2,3}\s+"
        raw_note_sections = re.split(notes_split_pattern, notes_block.strip())
        
        for section in raw_note_sections:
            if not section.strip():
                continue
            lines = section.split("\n", 1)
            note_header = lines[0].strip().upper()
            note_body = lines[1].strip() if len(lines) > 1 else ""
            
            # Match note header to one of the known play titles
            for meta in plays_metadata:
                if meta["norm_title"] in note_header:
                    notes_by_play[meta["norm_title"]] = f"## Textual Notes\n\n{note_body}"
                    break

    # 5. Write each play + its corresponding notes to its own .md file
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    for meta in plays_metadata:
        norm_title = meta["norm_title"]
        
        if norm_title not in play_texts:
            print(f"Warning: Could not find play text for '{meta['title']}'")
            continue

        play_content = play_texts[norm_title]
        note_content = notes_by_play.get(norm_title, "")

        # Combine play and notes
        full_document = play_content
        if note_content:
            full_document += f"\n\n---\n\n{note_content}\n"
        else:
            print(f"Notice: No textual notes matched for '{meta['title']}'")

        # Construct filename: "Author. Play (Tr. Translator).md"
        filename = f"{meta['author']}. {meta['title']} (Tr. {meta['translator']}).md"
        # Sanitize filename just in case of illegal path characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)

        file_path = out_path / filename
        file_path.write_text(full_document, encoding="utf-8")
        print(f"Created: {file_path}")

if __name__ == "__main__":
    split_plays("Greek Tragedies, Volume 1.md")