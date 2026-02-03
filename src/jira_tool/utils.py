"""Utility functions for JIRA tool."""


def normalize_priority(priority: str | None) -> str | None:
    """Normalize priority to short form (P1, P2, P3, etc.)."""
    if not priority:
        return None
    # Extract Pn prefix if present (e.g., "P1: High" -> "P1")
    if priority.startswith("P") and len(priority) >= 2 and priority[1].isdigit():
        return priority.split(":")[0].split()[0]  # Get just "Pn" part
    return priority


def filter_custom_fields(data: dict) -> dict:
    """Recursively remove customfield_* keys from a dictionary."""
    if not isinstance(data, dict):
        return data
    
    result = {}
    for key, value in data.items():
        if key.startswith("customfield_"):
            continue
        if isinstance(value, dict):
            result[key] = filter_custom_fields(value)
        elif isinstance(value, list):
            result[key] = [
                filter_custom_fields(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def extract_text_from_adf(adf: dict | None, use_rich_markup: bool = True) -> str | None:
    """Extract text from Atlassian Document Format, optionally with Rich markup.
    
    Args:
        adf: The ADF document dict from JIRA API
        use_rich_markup: If True, return Rich-formatted markup. If False, return plain text.
    
    Returns:
        Formatted string or None if no content
    """
    if not adf or not isinstance(adf, dict):
        return None
    
    def escape_rich(text: str) -> str:
        """Escape Rich markup characters in text."""
        # Escape brackets which Rich interprets as markup
        return text.replace("[", "\\[").replace("]", "\\]")
    
    def apply_marks(text: str, marks: list[dict]) -> str:
        """Apply ADF marks (formatting) to text, converting to Rich markup."""
        if not use_rich_markup or not marks:
            return escape_rich(text) if use_rich_markup else text
        
        escaped = escape_rich(text)
        
        for mark in marks:
            mark_type = mark.get("type", "")
            
            if mark_type == "strong":
                escaped = f"[bold]{escaped}[/bold]"
            elif mark_type == "em":
                escaped = f"[italic]{escaped}[/italic]"
            elif mark_type == "strike":
                escaped = f"[strike]{escaped}[/strike]"
            elif mark_type == "code":
                escaped = f"[cyan]{escaped}[/cyan]"
            elif mark_type == "underline":
                escaped = f"[underline]{escaped}[/underline]"
            elif mark_type == "link":
                href = mark.get("attrs", {}).get("href", "")
                # Rich supports clickable links with [link=URL]text[/link]
                escaped = f"[link={href}]{escaped}[/link] [dim]({href})[/dim]"
            elif mark_type == "textColor":
                color = mark.get("attrs", {}).get("color", "")
                if color:
                    escaped = f"[{color}]{escaped}[/{color}]"
            elif mark_type == "subsup":
                # Superscript/subscript - just render as-is, Rich doesn't support these
                pass
        
        return escaped
    
    def extract_content(node: dict, list_depth: int = 0, list_type: str | None = None, item_index: int = 0) -> str:
        """Recursively extract content from ADF nodes."""
        node_type = node.get("type", "")
        content = node.get("content", [])
        attrs = node.get("attrs", {})
        
        # Text node with optional marks
        if node_type == "text":
            text = node.get("text", "")
            marks = node.get("marks", [])
            return apply_marks(text, marks)
        
        # Hard break
        if node_type == "hardBreak":
            return "\n"
        
        # Process children
        parts = []
        child_item_index = 0
        for child in content:
            if isinstance(child, dict):
                # Track list item indices for ordered lists
                if child.get("type") == "listItem":
                    parts.append(extract_content(child, list_depth, list_type, child_item_index))
                    child_item_index += 1
                else:
                    parts.append(extract_content(child, list_depth, list_type, item_index))
        
        joined = "".join(parts)
        
        # Block-level formatting
        if node_type == "paragraph":
            return joined + "\n"
        
        elif node_type == "heading":
            level = attrs.get("level", 1)
            if use_rich_markup:
                # Use bold and different colors for heading levels
                if level == 1:
                    return f"[bold cyan]{joined}[/bold cyan]\n"
                elif level == 2:
                    return f"[bold blue]{joined}[/bold blue]\n"
                elif level == 3:
                    return f"[bold]{joined}[/bold]\n"
                else:
                    return f"[bold dim]{joined}[/bold dim]\n"
            else:
                return joined + "\n"
        
        elif node_type == "bulletList":
            result = []
            for i, child in enumerate(content):
                if isinstance(child, dict):
                    result.append(extract_content(child, list_depth + 1, "bullet", i))
            return "".join(result)
        
        elif node_type == "orderedList":
            result = []
            for i, child in enumerate(content):
                if isinstance(child, dict):
                    result.append(extract_content(child, list_depth + 1, "ordered", i))
            return "".join(result)
        
        elif node_type == "listItem":
            indent = "  " * list_depth
            if list_type == "ordered":
                prefix = f"{item_index + 1}."
            else:
                prefix = "•"
            # listItem contains paragraphs, strip their trailing newlines for cleaner output
            item_content = joined.rstrip("\n")
            return f"{indent}{prefix} {item_content}\n"
        
        elif node_type == "codeBlock":
            language = attrs.get("language", "")
            if use_rich_markup:
                # Use dim background style for code blocks
                lines = joined.rstrip("\n").split("\n")
                formatted_lines = [f"[on grey23] {line} [/on grey23]" for line in lines]
                lang_header = f"[dim]{language}[/dim]\n" if language else ""
                return lang_header + "\n".join(formatted_lines) + "\n"
            else:
                return joined + "\n"
        
        elif node_type == "blockquote":
            if use_rich_markup:
                lines = joined.rstrip("\n").split("\n")
                quoted = "\n".join(f"[dim]│[/dim] [italic]{line}[/italic]" for line in lines)
                return quoted + "\n"
            else:
                lines = joined.rstrip("\n").split("\n")
                return "\n".join(f"> {line}" for line in lines) + "\n"
        
        elif node_type == "rule":
            if use_rich_markup:
                return "[dim]────────────────────────────────[/dim]\n"
            else:
                return "---\n"
        
        elif node_type == "table":
            # Tables are complex - render as simple text representation
            return joined + "\n"
        
        elif node_type == "tableRow":
            return joined
        
        elif node_type == "tableHeader":
            if use_rich_markup:
                return f"[bold]{joined}[/bold] | "
            else:
                return joined + " | "
        
        elif node_type == "tableCell":
            return joined + " | "
        
        elif node_type == "mediaSingle" or node_type == "media":
            # Media attachments - show placeholder
            media_type = attrs.get("type", "file")
            media_id = attrs.get("id", "")
            if use_rich_markup:
                return f"[dim]\\[{media_type}: {media_id}][/dim]"
            else:
                return f"[{media_type}: {media_id}]"
        
        elif node_type == "emoji":
            # Try to render emoji by shortName or fallback
            short_name = attrs.get("shortName", "")
            text = attrs.get("text", short_name)
            return text
        
        elif node_type == "mention":
            # User/team mentions
            mention_text = attrs.get("text", "@unknown")
            if use_rich_markup:
                return f"[cyan]{mention_text}[/cyan]"
            else:
                return mention_text
        
        elif node_type == "inlineCard" or node_type == "blockCard":
            # Smart links/cards
            url = attrs.get("url", "")
            if use_rich_markup:
                return f"[link={url}]{url}[/link]"
            else:
                return url
        
        elif node_type == "panel":
            panel_type = attrs.get("panelType", "info")
            # Panel types: info, note, warning, error, success
            color_map = {
                "info": "blue",
                "note": "cyan", 
                "warning": "yellow",
                "error": "red",
                "success": "green",
            }
            color = color_map.get(panel_type, "white")
            if use_rich_markup:
                return f"[{color}]┃[/{color}] {joined}"
            else:
                return f"[{panel_type.upper()}] {joined}"
        
        elif node_type == "expand":
            title = attrs.get("title", "Details")
            if use_rich_markup:
                return f"[bold]▶ {title}[/bold]\n{joined}"
            else:
                return f"[{title}]\n{joined}"
        
        elif node_type == "status":
            text = attrs.get("text", "")
            status_color = attrs.get("color", "neutral")
            color_map = {
                "neutral": "white",
                "purple": "magenta",
                "blue": "blue",
                "green": "green",
                "yellow": "yellow",
                "red": "red",
            }
            color = color_map.get(status_color, "white")
            if use_rich_markup:
                return f"[{color}]⦿ {text}[/{color}]"
            else:
                return f"[{text}]"
        
        elif node_type == "date":
            timestamp = attrs.get("timestamp", "")
            # Timestamp is in milliseconds
            if timestamp:
                try:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(int(timestamp) / 1000)
                    return dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    return timestamp
            return ""
        
        # Default: just return joined content
        return joined
    
    result = extract_content(adf).strip()
    return result or None


def simplify_issue(
    issue: dict,
    comments: list[dict] | None = None,
    children: list[dict] | None = None,
    use_rich_markup: bool = True,
) -> dict:
    """Convert raw JIRA API issue to a simplified format.
    
    Args:
        issue: Raw JIRA API issue dict
        comments: Optional list of comment dicts
        children: Optional list of child issue dicts
        use_rich_markup: If True, format description/comments with Rich markup
    """
    fields = issue.get("fields", {})
    
    simplified = {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "summary": (fields.get("summary") or "").strip(),
        "description": extract_text_from_adf(fields.get("description"), use_rich_markup=use_rich_markup),
        "status": fields.get("status", {}).get("name"),
        "type": fields.get("issuetype", {}).get("name"),
        "priority": normalize_priority(fields.get("priority", {}).get("name")),
        "resolution": fields.get("resolution", {}).get("name") if fields.get("resolution") else None,
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "due_date": fields.get("duedate"),
        "labels": fields.get("labels", []),
        "components": [c.get("name") for c in fields.get("components", [])],
        "fix_versions": [v.get("name") for v in fields.get("fixVersions", [])],
        "project": {
            "key": fields.get("project", {}).get("key"),
            "name": fields.get("project", {}).get("name"),
        },
    }
    
    # Add parent/epic link if present
    parent = fields.get("parent")
    if parent:
        simplified["parent"] = {
            "key": parent.get("key"),
            "summary": parent.get("fields", {}).get("summary"),
        }
    
    # Add time tracking if present
    time_tracking = fields.get("timetracking", {})
    if time_tracking:
        simplified["time_tracking"] = {
            "original_estimate": time_tracking.get("originalEstimate"),
            "remaining_estimate": time_tracking.get("remainingEstimate"),
            "time_spent": time_tracking.get("timeSpent"),
        }
    
    # Add subtasks if present
    subtasks = fields.get("subtasks", [])
    if subtasks:
        simplified["subtasks"] = [
            {
                "key": st.get("key"),
                "summary": st.get("fields", {}).get("summary"),
                "status": st.get("fields", {}).get("status", {}).get("name"),
            }
            for st in subtasks
        ]
    
    # Add links if present
    links = fields.get("issuelinks", [])
    if links:
        simplified["links"] = []
        for link in links:
            link_type = link.get("type", {}).get("name")
            if "outwardIssue" in link:
                simplified["links"].append({
                    "type": link_type,
                    "direction": "outward",
                    "key": link["outwardIssue"].get("key"),
                    "summary": link["outwardIssue"].get("fields", {}).get("summary"),
                })
            if "inwardIssue" in link:
                simplified["links"].append({
                    "type": link_type,
                    "direction": "inward",
                    "key": link["inwardIssue"].get("key"),
                    "summary": link["inwardIssue"].get("fields", {}).get("summary"),
                })
    
    # Add children if provided
    if children:
        simplified["children"] = [
            {
                "key": c.get("key"),
                "summary": c.get("fields", {}).get("summary"),
                "status": c.get("fields", {}).get("status", {}).get("name"),
                "type": c.get("fields", {}).get("issuetype", {}).get("name"),
            }
            for c in children
        ]
    
    # Add comments if provided
    if comments:
        simplified["comments"] = [
            {
                "author": c.get("author", {}).get("displayName", "Unknown"),
                "created": c.get("created"),
                "body": extract_text_from_adf(c.get("body"), use_rich_markup=use_rich_markup),
            }
            for c in comments
        ]
    
    return simplified


# All available fields that can be selected
AVAILABLE_FIELDS = {
    "key", "id", "summary", "description", "status", "type", "priority",
    "resolution", "assignee", "reporter", "created", "updated", "due_date",
    "labels", "components", "fix_versions", "project", "parent",
    "time_tracking", "subtasks", "links", "children", "comments",
}

# Default fields for different contexts
DEFAULT_FIELDS_GET = {
    "key", "summary", "description", "status", "type", "priority",
    "assignee", "reporter", "created", "updated", "due_date",
    "labels", "components", "fix_versions", "project", "parent",
    "subtasks", "links", "children", "comments",
}

DEFAULT_FIELDS_SEARCH = {
    "key", "summary", "status", "type", "priority", "assignee", "components",
}


def filter_fields(issue: dict, fields: set[str]) -> dict:
    """Filter a simplified issue to only include the specified fields.
    
    Args:
        issue: A simplified issue dict from simplify_issue()
        fields: Set of field names to include
        
    Returns:
        Dict containing only the requested fields (that have values)
    """
    result = {}
    for field in fields:
        if field in issue:
            value = issue[field]
            # Skip empty/None values to keep output clean
            if value is not None and value != [] and value != {}:
                result[field] = value
    return result


def parse_fields_option(fields_str: str | None, default_fields: set[str]) -> set[str]:
    """Parse a comma-separated fields string into a set of field names.
    
    Supports:
    - Comma-separated field names: "key,summary,status"
    - Adding to defaults with +: "+labels,description" 
    - Removing from defaults with -: "-components,-created"
    - Mix of add/remove: "+labels,-components"
    - "all" to include all available fields
    
    Args:
        fields_str: The --fields option value, or None for defaults
        default_fields: The default set of fields for this context
        
    Returns:
        Set of field names to include
    """
    if not fields_str:
        return default_fields
    
    fields_str = fields_str.strip()
    
    # Special case: "all" returns all fields
    if fields_str.lower() == "all":
        return AVAILABLE_FIELDS.copy()
    
    # Check if using +/- modifiers
    parts = [p.strip() for p in fields_str.split(",")]
    has_modifiers = any(p.startswith("+") or p.startswith("-") for p in parts)
    
    if has_modifiers:
        # Start with defaults, then apply modifiers
        result = default_fields.copy()
        for part in parts:
            if part.startswith("+"):
                field = part[1:]
                if field in AVAILABLE_FIELDS:
                    result.add(field)
            elif part.startswith("-"):
                field = part[1:]
                result.discard(field)
            else:
                # No modifier, treat as add
                if part in AVAILABLE_FIELDS:
                    result.add(part)
        return result
    else:
        # Explicit list of fields (always include key)
        result = {"key"}
        for part in parts:
            if part in AVAILABLE_FIELDS:
                result.add(part)
        return result
