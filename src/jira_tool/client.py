"""JIRA API client."""

import json as json_module
from datetime import datetime
from typing import Any

import requests

from jira_tool.utils import markdown_to_adf


# HTTP status code descriptions for common errors
HTTP_STATUS_DESCRIPTIONS = {
    400: "Bad Request - The request was malformed or contains invalid parameters",
    401: "Unauthorized - Authentication failed (check email/API token)",
    403: "Forbidden - You don't have permission for this operation",
    404: "Not Found - The resource doesn't exist or you can't access it",
    405: "Method Not Allowed - This HTTP method isn't supported for this endpoint",
    409: "Conflict - The request conflicts with current state (e.g., duplicate)",
    410: "Gone - This API endpoint has been removed/deprecated",
    429: "Rate Limited - Too many requests, slow down",
    500: "Internal Server Error - JIRA server error",
    502: "Bad Gateway - JIRA is temporarily unavailable",
    503: "Service Unavailable - JIRA is temporarily unavailable",
}


class JiraError(Exception):
    """Exception raised for JIRA API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: dict | None = None,
        url: str | None = None,
        method: str | None = None,
        request_body: dict | None = None,
        query_params: dict | None = None,
        response_headers: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.url = url
        self.method = method
        self.request_body = request_body
        self.query_params = query_params
        self.response_headers = response_headers
        self.timestamp = datetime.now().isoformat()

    def format_error(self, field_name_map: dict[str, str] | None = None) -> str:
        """Format error for user-friendly display.
        
        Args:
            field_name_map: Optional mapping of field IDs to human-readable names
        """
        lines = []
        
        # Main error message with description
        if self.status_code:
            desc = HTTP_STATUS_DESCRIPTIONS.get(self.status_code, "")
            if desc:
                lines.append(f"JIRA API Error: HTTP {self.status_code} - {desc}")
            else:
                lines.append(f"JIRA API Error: HTTP {self.status_code}")
        else:
            lines.append("JIRA API Error")
        
        lines.append("")
        
        # Track if we have field errors for hint
        has_field_errors = False
        
        # Error details from response
        if self.response:
            if "errorMessages" in self.response and self.response["errorMessages"]:
                lines.append("Error Messages:")
                for msg in self.response["errorMessages"]:
                    lines.append(f"  • {msg}")
            if "errors" in self.response and self.response["errors"]:
                has_field_errors = True
                lines.append("Field Errors:")
                for field, msg in self.response["errors"].items():
                    # Try to get human-readable field name
                    display_name = field
                    if field_name_map and field in field_name_map:
                        display_name = f"{field_name_map[field]} ({field})"
                    elif field.startswith("customfield_"):
                        # Mark as custom field even if we don't have the name
                        display_name = f"{field} (custom field)"
                    lines.append(f"  • {display_name}: {msg}")
            if "message" in self.response and "errorMessages" not in self.response:
                lines.append(f"Message: {self.response['message']}")
        
        # Add hint for field errors
        if has_field_errors and self.status_code == 400:
            lines.append("")
            lines.append("💡 Hint: Use these commands to discover fields and allowed values:")
            lines.append("   jira-tool field list -q <search>          # Find field names and IDs")
            lines.append("   jira-tool field options <PROJECT> <TYPE>  # See required fields & allowed values")
            lines.append("   --field \"Field Name=value\"                # Pass custom fields by name")
        
        # Request details section
        lines.append("")
        lines.append("─" * 50)
        lines.append("Request Details:")
        
        if self.method and self.url:
            lines.append(f"  {self.method} {self.url}")
        
        if self.query_params:
            lines.append(f"  Query Params: {json_module.dumps(self.query_params, indent=4, default=str)}")
        
        if self.request_body:
            # Truncate large request bodies but show structure
            body_str = json_module.dumps(self.request_body, indent=2, default=str)
            if len(body_str) > 500:
                # Show truncated version
                lines.append(f"  Request Body (truncated):")
                for line in body_str[:500].split('\n'):
                    lines.append(f"    {line}")
                lines.append(f"    ... ({len(body_str)} chars total)")
            else:
                lines.append(f"  Request Body:")
                for line in body_str.split('\n'):
                    lines.append(f"    {line}")
        
        # Response headers that might be useful
        if self.response_headers:
            useful_headers = {}
            for key in ['x-request-id', 'x-aaccountid', 'x-arequestid', 'retry-after', 'x-ratelimit-remaining']:
                if key in self.response_headers:
                    useful_headers[key] = self.response_headers[key]
            if useful_headers:
                lines.append(f"  Response Headers: {useful_headers}")
        
        lines.append(f"  Timestamp: {self.timestamp}")
        lines.append("─" * 50)
        
        return "\n".join(lines)


class JiraClient:
    """Client for interacting with JIRA Cloud REST API."""

    def __init__(self, base_url: str, email: str, api_token: str):
        """Initialize the JIRA client.

        Args:
            base_url: JIRA instance URL (e.g., https://yourcompany.atlassian.net)
            email: JIRA account email address
            api_token: JIRA API token (generate at https://id.atlassian.com/manage-profile/security/api-tokens)
        """
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/rest/api/3"
        self.agile_url = f"{self.base_url}/rest/agile/1.0"
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict[str, Any]:
        """Make a request to the JIRA API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json: JSON body for POST/PUT requests

        Returns:
            Response JSON as dictionary

        Raises:
            JiraError: If the API returns an error
        """
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json,
        )

        if not response.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {"message": response.text}
            
            # Capture response headers (case-insensitive dict to regular dict)
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            
            raise JiraError(
                message=f"JIRA API error: {response.status_code}",
                status_code=response.status_code,
                response=error_data,
                url=url,
                method=method,
                request_body=json,
                query_params=params,
                response_headers=response_headers,
            )

        # Some endpoints return no content
        if response.status_code == 204:
            return {}

        # Handle empty response bodies (some 201 responses have no body)
        if not response.content:
            return {}

        return response.json()

    def get(self, endpoint: str, params: dict | None = None) -> dict[str, Any]:
        """Make a GET request."""
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        """Make a POST request."""
        return self._request("POST", endpoint, json=json)

    def put(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        """Make a PUT request."""
        return self._request("PUT", endpoint, json=json)

    def delete(self, endpoint: str) -> dict[str, Any]:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint)

    def _agile_request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict[str, Any]:
        """Make a request to the JIRA Agile API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json: JSON body for POST/PUT requests

        Returns:
            Response JSON as dictionary

        Raises:
            JiraError: If the API returns an error
        """
        url = f"{self.agile_url}/{endpoint.lstrip('/')}"

        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json,
        )

        if not response.ok:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {"message": response.text}

            # Capture response headers (case-insensitive dict to regular dict)
            response_headers = {k.lower(): v for k, v in response.headers.items()}

            raise JiraError(
                message=f"JIRA Agile API error: {response.status_code}",
                status_code=response.status_code,
                response=error_data,
                url=url,
                method=method,
                request_body=json,
                query_params=params,
                response_headers=response_headers,
            )

        # Some endpoints return no content
        if response.status_code == 204:
            return {}

        # Handle empty response bodies
        if not response.content:
            return {}

        return response.json()

    def agile_get(self, endpoint: str, params: dict | None = None) -> dict[str, Any]:
        """Make a GET request to Agile API."""
        return self._agile_request("GET", endpoint, params=params)

    def agile_post(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        """Make a POST request to Agile API."""
        return self._agile_request("POST", endpoint, json=json)

    # =========================================================================
    # Issue methods
    # =========================================================================
    def get_issue(self, issue_key: str, fields: list[str] | None = None) -> dict[str, Any]:
        """Get a specific issue by key.

        Args:
            issue_key: The issue key (e.g., PROJ-123)
            fields: Optional list of fields to return

        Returns:
            Issue data dictionary
        """
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        return self.get(f"issue/{issue_key}", params=params)

    def get_issue_comments(self, issue_key: str, max_results: int = 50) -> list[dict[str, Any]]:
        """Get comments for an issue.

        Args:
            issue_key: The issue key (e.g., PROJ-123)
            max_results: Maximum number of comments to return

        Returns:
            List of comment dictionaries
        """
        result = self.get(f"issue/{issue_key}/comment", params={"maxResults": max_results})
        return result.get("comments", [])

    # Default fields to request for issue searches
    DEFAULT_SEARCH_FIELDS = [
        "summary", "status", "issuetype", "priority", "assignee", "reporter",
        "created", "updated", "duedate", "labels", "components", "fixVersions",
        "parent", "subtasks", "issuelinks", "timetracking", "description", "project"
    ]

    def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        fields: list[str] | None = None,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        """Search for issues using JQL.

        Args:
            jql: JQL query string
            max_results: Maximum number of results
            fields: Optional list of fields to return (defaults to common fields)
            next_page_token: Token for pagination (from previous response)

        Returns:
            Search results dictionary with 'issues', 'isLast', and optionally 'nextPageToken'
        """
        body: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields if fields is not None else self.DEFAULT_SEARCH_FIELDS,
        }
        if next_page_token:
            body["nextPageToken"] = next_page_token
        return self.post("search/jql", json=body)

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str,
        description: str | None = None,
        assignee: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
        components: list[str] | None = None,
        parent: str | None = None,
        extra_fields: dict | None = None,
    ) -> dict[str, Any]:
        """Create a new JIRA issue.

        Args:
            project_key: Project key (e.g., PROJ)
            summary: Issue summary/title
            issue_type: Issue type (e.g., Bug, Story, Task, Epic)
            description: Issue description (Markdown supported, converted to ADF)
            assignee: Assignee account ID or email
            priority: Priority name (e.g., "P1: High")
            labels: List of labels
            components: List of component names
            parent: Parent issue key (for sub-tasks or epic children)
            extra_fields: Additional fields as a dict

        Returns:
            Created issue data dictionary
        """
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        if description:
            # Convert Markdown to Atlassian Document Format
            fields["description"] = markdown_to_adf(description)

        if assignee:
            # Could be account ID or email - JIRA expects accountId
            fields["assignee"] = {"id": assignee} if assignee.startswith("accountid:") else {"accountId": assignee}

        if priority:
            fields["priority"] = {"name": priority}

        if labels:
            fields["labels"] = labels

        if components:
            fields["components"] = [{"name": c} for c in components]

        if parent:
            fields["parent"] = {"key": parent}

        if extra_fields:
            fields.update(extra_fields)

        return self.post("issue", json={"fields": fields})

    def update_issue(
        self,
        issue_key: str,
        summary: str | None = None,
        description: str | None = None,
        assignee: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
        components: list[str] | None = None,
        extra_fields: dict | None = None,
    ) -> dict[str, Any]:
        """Update an existing JIRA issue.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            summary: New summary/title
            description: New description (Markdown supported, converted to ADF)
            assignee: New assignee account ID or email (use "" to unassign)
            priority: New priority name
            labels: New labels (replaces existing)
            components: New components (replaces existing)
            extra_fields: Additional fields as a dict (already translated)

        Returns:
            Empty dict on success (204 response)
        """
        fields: dict[str, Any] = {}

        if summary is not None:
            fields["summary"] = summary

        if description is not None:
            # Convert Markdown to Atlassian Document Format
            fields["description"] = markdown_to_adf(description)

        if assignee is not None:
            if assignee == "":
                fields["assignee"] = None  # Unassign
            else:
                fields["assignee"] = {"id": assignee} if assignee.startswith("accountid:") else {"accountId": assignee}

        if priority is not None:
            fields["priority"] = {"name": priority}

        if labels is not None:
            fields["labels"] = labels

        if components is not None:
            fields["components"] = [{"name": c} for c in components]

        if extra_fields:
            fields.update(extra_fields)

        return self.put(f"issue/{issue_key}", json={"fields": fields})

    def delete_issue(self, issue_key: str, delete_subtasks: bool = False) -> dict[str, Any]:
        """Delete a JIRA issue.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            delete_subtasks: If True, also delete subtasks. If False and issue has
                           subtasks, the deletion will fail.

        Returns:
            Empty dict on success (204 response)
        """
        endpoint = f"issue/{issue_key}"
        if delete_subtasks:
            endpoint += "?deleteSubtasks=true"
        return self.delete(endpoint)

    def move_issue(
        self,
        issue_key: str,
        target_project: str,
        component_mapping: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Move an issue to a different project.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            target_project: Target project key
            component_mapping: Optional mapping of old component names to new component names

        Returns:
            Response dict (may be empty on 204)

        Note:
            The issue key will change after the move. The new key is not returned by the API,
            but follows the pattern: {target_project}-{new_number}

        Raises:
            JiraError: If the move fails (incompatible issue types, required fields, permissions)
        """
        fields: dict[str, Any] = {
            "project": {"key": target_project}
        }

        # If component mapping is provided, update components
        if component_mapping:
            # Get current issue to see its components
            issue = self.get_issue(issue_key, fields=["components"])
            current_components = issue.get("fields", {}).get("components", [])

            # Map components
            new_components = []
            for comp in current_components:
                old_name = comp.get("name", "")
                new_name = component_mapping.get(old_name, old_name)
                new_components.append({"name": new_name})

            if new_components:
                fields["components"] = new_components

        result = self.put(f"issue/{issue_key}", json={"fields": fields})
        return result

    # =========================================================================
    # Transition methods
    # =========================================================================
    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """Get available transitions for an issue.

        Args:
            issue_key: Issue key (e.g., PROJ-123)

        Returns:
            List of available transitions with id, name, and target status
        """
        result = self.get(f"issue/{issue_key}/transitions")
        return result.get("transitions", [])

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: str | None = None,
        fields: dict | None = None,
    ) -> dict[str, Any]:
        """Transition an issue to a new status.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            transition_id: The transition ID (from get_transitions)
            comment: Optional comment to add with the transition (Markdown supported)
            fields: Optional fields to set during transition (e.g., resolution)

        Returns:
            Empty dict on success (204 response)
        """
        payload: dict[str, Any] = {
            "transition": {"id": transition_id}
        }

        if comment:
            payload["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": markdown_to_adf(comment)
                        }
                    }
                ]
            }

        if fields:
            payload["fields"] = fields

        return self.post(f"issue/{issue_key}/transitions", json=payload)

    # =========================================================================
    # Comment methods
    # =========================================================================
    def get_issue_comments(self, issue_key: str, max_results: int = 50) -> list[dict[str, Any]]:
        """Get comments for an issue.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            max_results: Maximum number of comments to return

        Returns:
            List of comment dictionaries
        """
        result = self.get(f"issue/{issue_key}/comment", params={"maxResults": max_results})
        return result.get("comments", [])

    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            body: Comment text (Markdown supported, converted to ADF)

        Returns:
            The created comment object
        """
        # Convert Markdown to Atlassian Document Format
        adf_body = markdown_to_adf(body)

        return self.post(f"issue/{issue_key}/comment", json={"body": adf_body})

    def update_comment(self, issue_key: str, comment_id: str, body: str) -> dict[str, Any]:
        """Update an existing comment.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            comment_id: The comment ID
            body: New comment text (Markdown supported, converted to ADF)

        Returns:
            The updated comment object
        """
        adf_body = markdown_to_adf(body)

        return self.put(f"issue/{issue_key}/comment/{comment_id}", json={"body": adf_body})

    def delete_comment(self, issue_key: str, comment_id: str) -> dict[str, Any]:
        """Delete a comment.

        Args:
            issue_key: Issue key (e.g., PROJ-123)
            comment_id: The comment ID

        Returns:
            Empty dict on success (204 response)
        """
        return self.delete(f"issue/{issue_key}/comment/{comment_id}")

    # =========================================================================
    # Issue Link methods
    # =========================================================================
    def get_issue_link_types(self) -> list[dict[str, Any]]:
        """Get all available issue link types.

        Returns:
            List of link type dictionaries with id, name, inward, outward
        """
        result = self.get("issueLinkType")
        return result.get("issueLinkTypes", [])

    def create_issue_link(
        self,
        link_type: str,
        inward_issue: str,
        outward_issue: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Create a link between two issues.

        Args:
            link_type: The link type name (e.g., "Blocks", "Duplicate", "Relates")
            inward_issue: The inward issue key (e.g., PROJ-123 blocks PROJ-456 - this is PROJ-456)
            outward_issue: The outward issue key (e.g., PROJ-123 blocks PROJ-456 - this is PROJ-123)
            comment: Optional comment to add with the link (Markdown supported)

        Returns:
            Empty dict on success (201 response)
        """
        payload: dict[str, Any] = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_issue},
            "outwardIssue": {"key": outward_issue},
        }

        if comment:
            payload["comment"] = {
                "body": markdown_to_adf(comment)
            }

        return self.post("issueLink", json=payload)

    def delete_issue_link(self, link_id: str) -> dict[str, Any]:
        """Delete an issue link.

        Args:
            link_id: The link ID

        Returns:
            Empty dict on success (204 response)
        """
        return self.delete(f"issueLink/{link_id}")

    # =========================================================================
    # Project methods
    # =========================================================================
    def get_projects(self) -> list[dict[str, Any]]:
        """Get all accessible projects.

        Returns:
            List of project dictionaries
        """
        return self.get("project")

    def get_project(self, project_key: str) -> dict[str, Any]:
        """Get a specific project by key.

        Args:
            project_key: The project key

        Returns:
            Project data dictionary
        """
        return self.get(f"project/{project_key}")

    # =========================================================================
    # Component methods
    # =========================================================================
    def get_project_components(self, project_key: str) -> list[dict[str, Any]]:
        """Get all components for a project.

        Args:
            project_key: The project key

        Returns:
            List of component dictionaries
        """
        return self.get(f"project/{project_key}/components")

    def create_component(
        self,
        project_key: str,
        name: str,
        description: str | None = None,
        lead_account_id: str | None = None,
        assignee_type: str | None = None,
    ) -> dict[str, Any]:
        """Create a new component in a project.

        Args:
            project_key: The project key
            name: Component name
            description: Optional component description
            lead_account_id: Optional component lead's account ID
            assignee_type: Optional assignee type (PROJECT_DEFAULT, COMPONENT_LEAD,
                          PROJECT_LEAD, UNASSIGNED)

        Returns:
            Created component dictionary
        """
        payload: dict[str, Any] = {
            "name": name,
            "project": project_key,
        }

        if description is not None:
            payload["description"] = description

        if lead_account_id is not None:
            payload["leadAccountId"] = lead_account_id

        if assignee_type is not None:
            payload["assigneeType"] = assignee_type

        return self.post("component", json=payload)

    # =========================================================================
    # Field methods
    # =========================================================================
    def get_fields(self) -> list[dict[str, Any]]:
        """Get all available fields in the JIRA instance.

        Returns:
            List of field dictionaries with id, name, custom, schema, etc.
        """
        return self.get("field")

    def get_field_map(self) -> dict[str, dict[str, Any]]:
        """Get a mapping of field names to field info (ID and schema).

        Returns:
            Dictionary mapping lowercase field names to field info dicts.
            Each dict contains 'id' and 'schema' keys.
        """
        fields = self.get_fields()
        field_map = {}
        
        for field in fields:
            field_id = field.get("id", "")
            field_name = field.get("name", "")
            field_key = field.get("key", "")
            schema = field.get("schema", {}) or {}
            
            field_info = {
                "id": field_id,
                "schema": schema,
            }
            
            # Map by lowercase name
            if field_name:
                field_map[field_name.lower()] = field_info
            
            # Also map by key if different from name
            if field_key and field_key.lower() != field_name.lower():
                field_map[field_key.lower()] = field_info
            
            # Also map by ID itself for explicit customfield_XXXXX references
            if field_id:
                field_map[field_id.lower()] = field_info
        
        return field_map

    def _format_field_value(self, value: Any, schema: dict) -> Any:
        """Format a field value based on its schema type.

        Args:
            value: The raw value to format
            schema: The field schema from JIRA

        Returns:
            Properly formatted value for the JIRA API
        """
        field_type = schema.get("type", "")
        
        # Option fields expect {"value": "..."} or {"id": "..."}
        if field_type == "option":
            if isinstance(value, dict):
                return value  # Already formatted
            return {"value": value}
        
        # Array of options
        if field_type == "array" and schema.get("items") == "option":
            if isinstance(value, list):
                return [{"value": v} if not isinstance(v, dict) else v for v in value]
            return [{"value": value}]
        
        # User fields expect {"accountId": "..."} or {"id": "..."}
        if field_type == "user":
            if isinstance(value, dict):
                return value
            return {"accountId": value}
        
        # Array of users
        if field_type == "array" and schema.get("items") == "user":
            if isinstance(value, list):
                return [{"accountId": v} if not isinstance(v, dict) else v for v in value]
            return [{"accountId": value}]
        
        # For string fields that use ADF (like text areas), convert to ADF
        if field_type == "string" and schema.get("custom", "").endswith(":textarea"):
            if isinstance(value, str):
                return {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": line}]
                        }
                        for line in value.split("\n")
                        if line.strip()
                    ] or [{"type": "paragraph", "content": [{"type": "text", "text": " "}]}]
                }
        
        # Default: return as-is
        return value

    def translate_field_names(self, fields_dict: dict[str, Any]) -> dict[str, Any]:
        """Translate human-readable field names to JIRA field IDs and format values.

        Args:
            fields_dict: Dictionary with field names as keys

        Returns:
            Dictionary with field IDs as keys, values formatted appropriately
        """
        field_map = self.get_field_map()
        translated = {}
        
        for name, value in fields_dict.items():
            # Look up the field info
            field_info = field_map.get(name.lower())
            
            if field_info is None:
                # Check if it's already a valid field ID (customfield_XXXXX)
                if name.startswith("customfield_") or name in ["summary", "description", "project", "issuetype", "assignee", "reporter", "priority", "labels", "components", "parent", "status", "resolution", "fixVersions", "versions", "duedate"]:
                    # No schema info available, pass through as-is
                    translated[name] = value
                    continue
                else:
                    raise JiraError(
                        message=f"Unknown field: '{name}'. Use 'jira-tool field list' to see available fields.",
                        status_code=None,
                    )
            
            field_id = field_info["id"]
            schema = field_info.get("schema", {})
            
            # Format the value based on schema
            formatted_value = self._format_field_value(value, schema)
            translated[field_id] = formatted_value
        
        return translated

    # =========================================================================
    # Board methods (Agile API)
    # =========================================================================
    def get_boards(
        self,
        project_key: str | None = None,
        board_type: str | None = None,
        name: str | None = None,
        max_results: int = 50,
        strict_project_filter: bool = True,
    ) -> list[dict[str, Any]]:
        """Get all boards, optionally filtered.

        Args:
            project_key: Filter by project key
            board_type: Filter by type (scrum, kanban)
            name: Filter by board name (contains match)
            max_results: Maximum results to return
            strict_project_filter: If True and project_key is set, only return boards
                                  that belong to that project (not just boards whose
                                  filters mention it)

        Returns:
            List of board dictionaries
        """
        params: dict[str, Any] = {"maxResults": max_results}
        if project_key:
            params["projectKeyOrId"] = project_key
        if board_type:
            params["type"] = board_type
        if name:
            params["name"] = name

        result = self.agile_get("board", params=params)
        boards = result.get("values", [])

        # Post-filter to only include boards that actually belong to the project
        if project_key and strict_project_filter:
            boards = [
                b for b in boards
                if b.get("location", {}).get("projectKey") == project_key
            ]

        return boards

    def get_board(self, board_id: int | str) -> dict[str, Any]:
        """Get a specific board by ID.

        Args:
            board_id: The board ID

        Returns:
            Board dictionary
        """
        return self.agile_get(f"board/{board_id}")

    def get_board_configuration(self, board_id: int | str) -> dict[str, Any]:
        """Get board configuration including columns, filters, etc.

        Args:
            board_id: The board ID

        Returns:
            Board configuration dictionary
        """
        return self.agile_get(f"board/{board_id}/configuration")

    def create_board(
        self,
        name: str,
        board_type: str,
        filter_id: int | str,
    ) -> dict[str, Any]:
        """Create a new board.

        Args:
            name: Board name
            board_type: Board type (scrum or kanban)
            filter_id: ID of the filter (JQL query) to use for this board

        Returns:
            Created board dictionary
        """
        payload = {
            "name": name,
            "type": board_type,
            "filterId": int(filter_id),
        }
        return self.agile_post("board", json=payload)

    # =========================================================================
    # Filter methods
    # =========================================================================
    def get_filters(self, max_results: int = 50) -> list[dict[str, Any]]:
        """Get filters owned by or shared with the current user.

        Args:
            max_results: Maximum results to return

        Returns:
            List of filter dictionaries
        """
        result = self.get("filter/my", params={"maxResults": max_results})
        return result.get("values", []) if isinstance(result, dict) else result

    def get_filter(self, filter_id: int | str) -> dict[str, Any]:
        """Get a specific filter by ID.

        Args:
            filter_id: The filter ID

        Returns:
            Filter dictionary with id, name, jql, etc.
        """
        return self.get(f"filter/{filter_id}")

    def create_filter(
        self,
        name: str,
        jql: str,
        description: str | None = None,
        favourite: bool = False,
    ) -> dict[str, Any]:
        """Create a new filter.

        Args:
            name: Filter name
            jql: JQL query string
            description: Optional filter description
            favourite: Whether to mark as favourite

        Returns:
            Created filter dictionary
        """
        payload: dict[str, Any] = {
            "name": name,
            "jql": jql,
            "favourite": favourite,
        }
        if description:
            payload["description"] = description

        return self.post("filter", json=payload)

