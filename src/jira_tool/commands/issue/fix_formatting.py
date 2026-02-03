"""Issue fix-formatting subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
)
from jira_tool.utils import markdown_to_adf


def adf_has_formatting(adf: dict | None) -> bool:
    """Check if ADF document already has proper formatting.
    
    Returns True if the ADF contains formatting marks (bold, italic, links, code, etc.)
    or structured blocks (headings, lists, code blocks, blockquotes, etc.).
    
    This is used to detect documents that are already properly formatted,
    so we don't accidentally destroy their formatting by re-processing.
    """
    if not adf or not isinstance(adf, dict):
        return False
    
    # Block types that indicate real formatting (beyond plain paragraphs)
    formatted_block_types = {
        "heading", "bulletList", "orderedList", "codeBlock", 
        "blockquote", "rule", "table", "panel", "expand",
        "mediaSingle", "mediaGroup",
    }
    
    def check_node(node: dict) -> bool:
        if not isinstance(node, dict):
            return False
        
        node_type = node.get("type", "")
        
        # Check if this is a formatted block type
        if node_type in formatted_block_types:
            return True
        
        # Check for text marks (bold, italic, links, code, etc.)
        if node_type == "text":
            marks = node.get("marks", [])
            if marks:
                return True
        
        # Check for special inline nodes
        if node_type in ("mention", "emoji", "inlineCard", "status", "date"):
            return True
        
        # Recursively check children
        content = node.get("content", [])
        for child in content:
            if check_node(child):
                return True
        
        return False
    
    return check_node(adf)


def extract_plain_text_from_adf(adf: dict | None) -> str | None:
    """Extract plain text from ADF, preserving markdown syntax that may be in the text.
    
    This is different from extract_text_from_adf - it doesn't add Rich markup,
    and preserves the raw text content exactly as stored.
    """
    if not adf or not isinstance(adf, dict):
        return None
    
    def extract_content(node: dict, list_depth: int = 0, list_type: str | None = None, item_index: int = 0) -> str:
        node_type = node.get("type", "")
        content = node.get("content", [])
        attrs = node.get("attrs", {})
        
        # Text node - return raw text
        if node_type == "text":
            return node.get("text", "")
        
        # Hard break
        if node_type == "hardBreak":
            return "\n"
        
        # Process children
        parts = []
        child_item_index = 0
        for child in content:
            if isinstance(child, dict):
                if child.get("type") == "listItem":
                    parts.append(extract_content(child, list_depth, list_type, child_item_index))
                    child_item_index += 1
                else:
                    parts.append(extract_content(child, list_depth, list_type, item_index))
        
        joined = "".join(parts)
        
        # Block-level handling
        if node_type == "paragraph":
            return joined + "\n"
        
        elif node_type == "heading":
            level = attrs.get("level", 1)
            # Don't add markdown heading syntax - just return the text
            # The original might have had markdown that wasn't converted
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
            # Don't add list markers - just extract the text
            return joined
        
        elif node_type == "codeBlock":
            return joined + "\n"
        
        elif node_type == "blockquote":
            return joined
        
        elif node_type == "rule":
            return "---\n"
        
        return joined
    
    result = extract_content(adf).strip()
    return result or None


@issue.command("fix-formatting")
@click.argument("issue_keys", nargs=-1, required=True)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be changed without actually updating"
)
@click.option(
    "--force", "-f", is_flag=True, default=False,
    help="Fix formatting even if the document appears to already be formatted"
)
@click.option(
    "--show-before", is_flag=True, default=False,
    help="Show the extracted text before conversion"
)
@click.option(
    "--show-after", is_flag=True, default=False,
    help="Show the ADF that will be written"
)
@format_options
@click.pass_obj
@handle_api_errors
def issue_fix_formatting(
    ctx,
    issue_keys: tuple[str, ...],
    dry_run: bool,
    force: bool,
    show_before: bool,
    show_after: bool,
    output_format: str,
):
    """Fix markdown formatting in issue descriptions.
    
    This command fetches issues that have raw markdown text in their descriptions
    (e.g., literal **bold** or [links](url) showing as plain text) and re-saves
    them with proper ADF formatting so the markdown renders correctly in JIRA.
    
    Issues that already have proper ADF formatting (bold, links, headings, lists,
    code blocks, etc.) are automatically skipped to avoid destroying existing
    formatting. Use --force to override this check.
    
    \b
    Examples:
      # Fix a single issue
      jira-tool issue fix-formatting PROJ-123
      
      # Fix multiple issues
      jira-tool issue fix-formatting PROJ-123 PROJ-124 PROJ-125
      
      # Preview what would be changed
      jira-tool issue fix-formatting PROJ-123 --dry-run --show-before --show-after
      
      # Force re-processing even if already formatted
      jira-tool issue fix-formatting PROJ-123 --force
    """
    results = []
    
    for issue_key in issue_keys:
        # Fetch the issue
        issue_data = ctx.client.get_issue(issue_key)
        fields = issue_data.get("fields", {})
        description_adf = fields.get("description")
        
        if not description_adf:
            click.echo(click.style(f"⚠ {issue_key}: No description to fix", fg="yellow"), err=True)
            results.append({
                "key": issue_key,
                "status": "skipped",
                "reason": "no description",
            })
            continue
        
        # Check if already properly formatted (unless --force is used)
        if not force and adf_has_formatting(description_adf):
            click.echo(click.style(f"⏭ {issue_key}: Already has ADF formatting, skipping (use --force to override)", fg="cyan"), err=True)
            results.append({
                "key": issue_key,
                "status": "skipped",
                "reason": "already formatted",
            })
            continue
        
        # Extract plain text (preserving any markdown syntax in the text)
        extracted_text = extract_plain_text_from_adf(description_adf)
        
        if not extracted_text:
            click.echo(click.style(f"⚠ {issue_key}: Could not extract description text", fg="yellow"), err=True)
            results.append({
                "key": issue_key,
                "status": "skipped",
                "reason": "extraction failed",
            })
            continue
        
        if show_before:
            click.echo(click.style(f"\n{'─' * 50}", fg="dim"), err=True)
            click.echo(click.style(f"Extracted text from {issue_key}:", fg="cyan", bold=True), err=True)
            click.echo(extracted_text, err=True)
        
        # Convert markdown to proper ADF
        new_adf = markdown_to_adf(extracted_text)
        
        if show_after:
            click.echo(click.style(f"\n{'─' * 50}", fg="dim"), err=True)
            click.echo(click.style(f"New ADF for {issue_key}:", fg="cyan", bold=True), err=True)
            import json
            click.echo(json.dumps(new_adf, indent=2), err=True)
        
        if dry_run:
            click.echo(click.style(f"✓ [DRY RUN] Would fix formatting for {issue_key}", fg="green", bold=True))
            results.append({
                "key": issue_key,
                "status": "would_update",
                "extracted_text": extracted_text if show_before else None,
            })
        else:
            # Update the issue with the new ADF directly (bypass markdown_to_adf in update_issue)
            ctx.client.put(f"issue/{issue_key}", json={"fields": {"description": new_adf}})
            
            click.echo(click.style(f"✓ Fixed formatting for {issue_key}", fg="green", bold=True))
            if ctx.client.base_url:
                browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
                click.echo(f"  URL: {browse_url}")
            
            results.append({
                "key": issue_key,
                "status": "updated",
            })
    
    # Output summary for non-text formats
    if output_format != "text":
        output_data(results, output_format)
