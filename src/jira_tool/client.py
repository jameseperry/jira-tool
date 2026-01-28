"""JIRA API client."""

import json as json_module
from datetime import datetime
from typing import Any

import requests


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

    def format_error(self) -> str:
        """Format error for user-friendly display."""
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
        
        # Error details from response
        if self.response:
            if "errorMessages" in self.response and self.response["errorMessages"]:
                lines.append("Error Messages:")
                for msg in self.response["errorMessages"]:
                    lines.append(f"  • {msg}")
            if "errors" in self.response and self.response["errors"]:
                lines.append("Field Errors:")
                for field, msg in self.response["errors"].items():
                    lines.append(f"  • {field}: {msg}")
            if "message" in self.response and "errorMessages" not in self.response:
                lines.append(f"Message: {self.response['message']}")
        
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
