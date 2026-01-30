"""Issue comment subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
)


def extract_comment_text(comment: dict) -> str:
    """Extract plain text from a comment's ADF body."""
    body = comment.get("body", {})
    if isinstance(body, str):
        return body
    
    # Parse ADF format
    text_parts = []
    for content in body.get("content", []):
        if content.get("type") == "paragraph":
            for item in content.get("content", []):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            text_parts.append("\n")
    
    return "".join(text_parts).strip()


def format_comment_for_display(comment: dict) -> dict:
    """Format a comment for display."""
    author = comment.get("author", {})
    return {
        "id": comment.get("id"),
        "author": author.get("displayName", author.get("emailAddress", "Unknown")),
        "created": comment.get("created", "")[:19].replace("T", " "),
        "updated": comment.get("updated", "")[:19].replace("T", " "),
        "body": extract_comment_text(comment),
    }


@issue.group("comment")
def issue_comment():
    """Manage issue comments."""
    pass


@issue_comment.command("list")
@click.argument("issue_key")
@click.option("--limit", default=50, help="Maximum number of comments to return")
@format_options
@click.pass_obj
@handle_api_errors
def comment_list(ctx, issue_key: str, limit: int, output_format: str):
    """List comments on an issue.
    
    \b
    Examples:
      jira-tool issue comment list PROJ-123
      jira-tool issue comment list PROJ-123 --limit 10
      jira-tool issue comment list PROJ-123 --json
    """
    comments = ctx.client.get_issue_comments(issue_key, max_results=limit)
    
    if output_format == "text":
        if not comments:
            click.echo(f"No comments on {issue_key}")
            return
        
        click.echo(click.style(f"Comments on {issue_key} ({len(comments)}):", fg="cyan", bold=True))
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  {browse_url}")
        click.echo("")
        
        for c in comments:
            formatted = format_comment_for_display(c)
            click.echo(click.style(f"#{formatted['id']} - {formatted['author']}", fg="green", bold=True))
            click.echo(f"  Created: {formatted['created']}")
            if formatted['created'] != formatted['updated']:
                click.echo(f"  Updated: {formatted['updated']}")
            click.echo(f"  {formatted['body'][:200]}{'...' if len(formatted['body']) > 200 else ''}")
            click.echo("")
    else:
        simplified = [format_comment_for_display(c) for c in comments]
        output_data(simplified, output_format)


@issue_comment.command("add")
@click.argument("issue_key")
@click.argument("body")
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be done without actually adding the comment"
)
@format_options
@click.pass_obj
@handle_api_errors
def comment_add(ctx, issue_key: str, body: str, dry_run: bool, output_format: str):
    """Add a comment to an issue.
    
    \b
    Examples:
      jira-tool issue comment add PROJ-123 "Working on this now"
      jira-tool issue comment add PROJ-123 "Fixed in commit abc123" --dry-run
      
      # Multi-line comment (use quotes and \\n)
      jira-tool issue comment add PROJ-123 "Line 1\\nLine 2\\nLine 3"
    """
    # Handle escaped newlines
    body = body.replace("\\n", "\n")
    
    payload = {
        "issue": issue_key,
        "body": body,
    }
    
    if dry_run:
        click.echo(click.style("DRY RUN - No comment will be added", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Would add comment:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would add comment to {issue_key}", fg="green", bold=True))
        return
    
    result = ctx.client.add_comment(issue_key, body)
    comment_id = result.get("id", "")
    
    if output_format == "text":
        click.echo(click.style(f"✓ Added comment #{comment_id} to {issue_key}", fg="green", bold=True))
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}?focusedCommentId={comment_id}"
            click.echo(f"  URL: {browse_url}")
    else:
        output = {
            "key": issue_key,
            "comment_id": comment_id,
            "added": True,
        }
        output_data(output, output_format)


@issue_comment.command("edit")
@click.argument("issue_key")
@click.argument("comment_id")
@click.argument("body")
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be done without actually editing the comment"
)
@format_options
@click.pass_obj
@handle_api_errors
def comment_edit(ctx, issue_key: str, comment_id: str, body: str, dry_run: bool, output_format: str):
    """Edit an existing comment.
    
    \b
    Examples:
      jira-tool issue comment edit PROJ-123 12345 "Updated comment text"
      jira-tool issue comment edit PROJ-123 12345 "New text" --dry-run
    """
    # Handle escaped newlines
    body = body.replace("\\n", "\n")
    
    payload = {
        "issue": issue_key,
        "comment_id": comment_id,
        "new_body": body,
    }
    
    if dry_run:
        click.echo(click.style("DRY RUN - Comment will not be edited", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Would edit comment:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would edit comment #{comment_id} on {issue_key}", fg="green", bold=True))
        return
    
    ctx.client.update_comment(issue_key, comment_id, body)
    
    if output_format == "text":
        click.echo(click.style(f"✓ Updated comment #{comment_id} on {issue_key}", fg="green", bold=True))
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}?focusedCommentId={comment_id}"
            click.echo(f"  URL: {browse_url}")
    else:
        output = {
            "key": issue_key,
            "comment_id": comment_id,
            "updated": True,
        }
        output_data(output, output_format)


@issue_comment.command("delete")
@click.argument("issue_key")
@click.argument("comment_id")
@click.option(
    "--force", "-f", is_flag=True, default=False,
    help="Skip confirmation prompt"
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be done without actually deleting the comment"
)
@format_options
@click.pass_obj
@handle_api_errors
def comment_delete(ctx, issue_key: str, comment_id: str, force: bool, dry_run: bool, output_format: str):
    """Delete a comment.
    
    \b
    Examples:
      jira-tool issue comment delete PROJ-123 12345
      jira-tool issue comment delete PROJ-123 12345 --force
      jira-tool issue comment delete PROJ-123 12345 --dry-run
    """
    # Fetch comment to show what will be deleted
    comments = ctx.client.get_issue_comments(issue_key, max_results=100)
    comment = None
    for c in comments:
        if c.get("id") == comment_id:
            comment = c
            break
    
    if not comment and not dry_run:
        raise click.ClickException(f"Comment #{comment_id} not found on {issue_key}")
    
    comment_info = format_comment_for_display(comment) if comment else {"id": comment_id, "body": "(not found)"}
    
    if dry_run:
        click.echo(click.style("DRY RUN - Comment will not be deleted", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Would delete comment:", fg="cyan", bold=True), err=True)
        output_data(comment_info, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would delete comment #{comment_id} from {issue_key}", fg="green", bold=True))
        return
    
    if not force:
        click.echo(click.style("About to delete comment:", fg="red", bold=True), err=True)
        click.echo(f"  Issue: {issue_key}", err=True)
        click.echo(f"  Comment ID: {comment_id}", err=True)
        click.echo(f"  Author: {comment_info.get('author', 'Unknown')}", err=True)
        click.echo(f"  Body: {comment_info.get('body', '')[:100]}...", err=True)
        click.echo("", err=True)
        
        if not click.confirm("Are you sure you want to delete this comment?"):
            click.echo("Cancelled.", err=True)
            return
    
    ctx.client.delete_comment(issue_key, comment_id)
    
    if output_format == "text":
        click.echo(click.style(f"✓ Deleted comment #{comment_id} from {issue_key}", fg="green", bold=True))
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  URL: {browse_url}")
    else:
        output = {
            "key": issue_key,
            "comment_id": comment_id,
            "deleted": True,
        }
        output_data(output, output_format)
