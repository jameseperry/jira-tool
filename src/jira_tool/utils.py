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


def extract_text_from_adf(adf: dict | None) -> str | None:
    """Extract plain text from Atlassian Document Format."""
    if not adf or not isinstance(adf, dict):
        return None
    
    def extract_content(node: dict) -> str:
        if node.get("type") == "text":
            return node.get("text", "")
        
        content = node.get("content", [])
        parts = []
        for child in content:
            if isinstance(child, dict):
                parts.append(extract_content(child))
        
        # Add newlines for block elements
        if node.get("type") in ("paragraph", "heading", "listItem", "tableCell"):
            return "".join(parts) + "\n"
        elif node.get("type") == "hardBreak":
            return "\n"
        
        return "".join(parts)
    
    return extract_content(adf).strip() or None


def simplify_issue(issue: dict, comments: list[dict] | None = None, children: list[dict] | None = None) -> dict:
    """Convert raw JIRA API issue to a simplified format."""
    fields = issue.get("fields", {})
    
    simplified = {
        "key": issue.get("key"),
        "id": issue.get("id"),
        "summary": (fields.get("summary") or "").strip(),
        "description": extract_text_from_adf(fields.get("description")),
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
                "body": extract_text_from_adf(c.get("body")),
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
