"""Issue link subcommand."""

import click

from jira_tool.commands.issue import (
    issue,
    format_options,
    handle_api_errors,
    output_data,
)


@issue.group("link")
def issue_link():
    """Manage issue links."""
    pass


@issue_link.command("types")
@format_options
@click.pass_obj
@handle_api_errors
def link_types(ctx, output_format: str):
    """List available issue link types.
    
    \b
    Examples:
      jira-tool issue link types
      jira-tool issue link types --json
    """
    link_types = ctx.client.get_issue_link_types()
    
    if output_format == "text":
        click.echo(click.style("Available link types:", fg="cyan", bold=True))
        click.echo("")
        for lt in link_types:
            name = lt.get("name", "")
            inward = lt.get("inward", "")
            outward = lt.get("outward", "")
            click.echo(f"  • {name}")
            click.echo(f"      Inward: \"{inward}\"")
            click.echo(f"      Outward: \"{outward}\"")
            click.echo("")
    else:
        simplified = [
            {
                "id": lt.get("id"),
                "name": lt.get("name"),
                "inward": lt.get("inward"),
                "outward": lt.get("outward"),
            }
            for lt in link_types
        ]
        output_data(simplified, output_format)


@issue_link.command("add")
@click.argument("from_issue")
@click.argument("link_type")
@click.argument("to_issue")
@click.option(
    "--comment", "-c", default=None,
    help="Add a comment explaining the link"
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be done without actually creating the link"
)
@format_options
@click.pass_obj
@handle_api_errors
def link_add(
    ctx,
    from_issue: str,
    link_type: str,
    to_issue: str,
    comment: str | None,
    dry_run: bool,
    output_format: str,
):
    """Create a link between two issues.
    
    The link is created as: FROM_ISSUE <link_type> TO_ISSUE
    
    For example: "PROJ-123 blocks PROJ-456" means PROJ-123 blocks PROJ-456
    
    \b
    Common link types:
      - Blocks/is blocked by
      - Clones/is cloned by
      - Duplicate/is duplicated by
      - Relates (relates to)
    
    \b
    Examples:
      # PROJ-123 blocks PROJ-456
      jira-tool issue link add PROJ-123 Blocks PROJ-456
      
      # PROJ-123 duplicates PROJ-456
      jira-tool issue link add PROJ-123 Duplicate PROJ-456
      
      # PROJ-123 relates to PROJ-456
      jira-tool issue link add PROJ-123 Relates PROJ-456
      
      # Add with a comment
      jira-tool issue link add PROJ-123 Blocks PROJ-456 -c "Depends on API changes"
      
      # Dry-run
      jira-tool issue link add PROJ-123 Blocks PROJ-456 --dry-run
    
    Use 'jira-tool issue link types' to see all available link types.
    """
    # Get available link types to validate and get proper name
    available_types = ctx.client.get_issue_link_types()
    
    # Find matching link type (case-insensitive)
    link_type_lower = link_type.lower()
    matched_type = None
    for lt in available_types:
        if (lt.get("name", "").lower() == link_type_lower or
            lt.get("inward", "").lower() == link_type_lower or
            lt.get("outward", "").lower() == link_type_lower):
            matched_type = lt
            break
    
    if not matched_type:
        available = [lt.get("name") for lt in available_types]
        raise click.UsageError(
            f"Unknown link type '{link_type}'.\n"
            f"Available types: {', '.join(available)}\n"
            "Use 'jira-tool issue link types' to see details."
        )
    
    link_type_name = matched_type.get("name")
    outward_desc = matched_type.get("outward", link_type_name)
    
    payload = {
        "from_issue": from_issue,
        "link_type": link_type_name,
        "relationship": outward_desc,
        "to_issue": to_issue,
    }
    
    if comment:
        payload["comment"] = comment
    
    if dry_run:
        click.echo(click.style("DRY RUN - No link will be created", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Would create link:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would link: {from_issue} {outward_desc} {to_issue}", fg="green", bold=True))
        return
    
    # Create the link
    # JIRA API semantics: inwardIssue "inward desc" outwardIssue
    # For Blocks: inward="is blocked by", outward="blocks"
    # So for "A blocks B": A=inward (is blocked by), B=outward (blocks)... wait no
    # Testing showed: outward=159, inward=160 resulted in "160 blocks 159"
    # So for "A blocks B": A should be inward, B should be outward
    ctx.client.create_issue_link(
        link_type=link_type_name,
        inward_issue=from_issue,
        outward_issue=to_issue,
        comment=comment,
    )
    
    if output_format == "text":
        click.echo(click.style(f"✓ Linked: {from_issue} {outward_desc} {to_issue}", fg="green", bold=True))
        if comment:
            click.echo(f"  Comment: {comment}")
        if ctx.client.base_url:
            base = ctx.client.base_url.replace('/rest/api/3', '')
            click.echo(f"  {from_issue}: {base}/browse/{from_issue}")
            click.echo(f"  {to_issue}: {base}/browse/{to_issue}")
    else:
        output = {
            "from_issue": from_issue,
            "link_type": link_type_name,
            "to_issue": to_issue,
            "linked": True,
        }
        output_data(output, output_format)


@issue_link.command("list")
@click.argument("issue_key")
@format_options
@click.pass_obj
@handle_api_errors
def link_list(ctx, issue_key: str, output_format: str):
    """List all links for an issue.
    
    \b
    Examples:
      jira-tool issue link list PROJ-123
      jira-tool issue link list PROJ-123 --json
    """
    issue = ctx.client.get_issue(issue_key)
    links = issue.get("fields", {}).get("issuelinks", [])
    
    if output_format == "text":
        if not links:
            click.echo(f"No links on {issue_key}")
            return
        
        click.echo(click.style(f"Links on {issue_key}:", fg="cyan", bold=True))
        if ctx.client.base_url:
            browse_url = f"{ctx.client.base_url.replace('/rest/api/3', '')}/browse/{issue_key}"
            click.echo(f"  {browse_url}")
        click.echo("")
        
        for link in links:
            link_id = link.get("id", "")
            link_type = link.get("type", {}).get("name", "")
            
            # Determine direction and related issue
            if "outwardIssue" in link:
                direction = link.get("type", {}).get("outward", link_type)
                related = link.get("outwardIssue", {})
            else:
                direction = link.get("type", {}).get("inward", link_type)
                related = link.get("inwardIssue", {})
            
            related_key = related.get("key", "")
            related_summary = related.get("fields", {}).get("summary", "")
            related_status = related.get("fields", {}).get("status", {}).get("name", "")
            
            click.echo(f"  • {direction} {related_key}")
            click.echo(f"      {related_summary}")
            click.echo(f"      Status: {related_status} | Link ID: {link_id}")
            click.echo("")
    else:
        simplified = []
        for link in links:
            link_type = link.get("type", {}).get("name", "")
            
            if "outwardIssue" in link:
                direction = "outward"
                direction_desc = link.get("type", {}).get("outward", link_type)
                related = link.get("outwardIssue", {})
            else:
                direction = "inward"
                direction_desc = link.get("type", {}).get("inward", link_type)
                related = link.get("inwardIssue", {})
            
            simplified.append({
                "id": link.get("id"),
                "type": link_type,
                "direction": direction,
                "relationship": direction_desc,
                "related_issue": related.get("key"),
                "related_summary": related.get("fields", {}).get("summary"),
                "related_status": related.get("fields", {}).get("status", {}).get("name"),
            })
        output_data(simplified, output_format)


@issue_link.command("delete")
@click.argument("link_id")
@click.option(
    "--force", "-f", is_flag=True, default=False,
    help="Skip confirmation prompt"
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Show what would be done without actually deleting the link"
)
@format_options
@click.pass_obj
@handle_api_errors
def link_delete(ctx, link_id: str, force: bool, dry_run: bool, output_format: str):
    """Delete an issue link by ID.
    
    Use 'jira-tool issue link list ISSUE' to find the link ID.
    
    \b
    Examples:
      jira-tool issue link delete 12345
      jira-tool issue link delete 12345 --force
      jira-tool issue link delete 12345 --dry-run
    """
    payload = {"link_id": link_id}
    
    if dry_run:
        click.echo(click.style("DRY RUN - Link will not be deleted", fg="yellow", bold=True), err=True)
        click.echo(click.style("─" * 50, fg="yellow"), err=True)
        click.echo("", err=True)
        
        click.echo(click.style("Would delete link:", fg="cyan", bold=True), err=True)
        output_data(payload, output_format if output_format != "text" else "yaml")
        click.echo("", err=True)
        
        click.echo(click.style(f"✓ [DRY RUN] Would delete link {link_id}", fg="green", bold=True))
        return
    
    if not force:
        click.echo(click.style(f"About to delete link {link_id}", fg="red", bold=True), err=True)
        click.echo("", err=True)
        
        if not click.confirm("Are you sure you want to delete this link?"):
            click.echo("Cancelled.", err=True)
            return
    
    ctx.client.delete_issue_link(link_id)
    
    if output_format == "text":
        click.echo(click.style(f"✓ Deleted link {link_id}", fg="green", bold=True))
    else:
        output = {
            "link_id": link_id,
            "deleted": True,
        }
        output_data(output, output_format)
