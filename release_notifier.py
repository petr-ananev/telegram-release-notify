import json
import os
import re
from collections import deque
from typing import Optional

import requests
from jira import JIRA, Issue, JIRAError


class ReleaseNotifier:
    """Handles JIRA issue management and Telegram notifications."""

    def __init__(self):
        self.jira_host = os.environ["JIRA_HOST"]
        self.jira_base = f"https://{self.jira_host}/browse"
        self.jira_username = os.environ["JIRA_USERNAME"]
        self.jira_password = os.environ["JIRA_PASSWORD"]
        self.jira_qa_testers = [u.strip() for u in os.environ["JIRA_QA_TESTERS"].split(",")]
        self.jira_qa_lead = os.environ["JIRA_QA_LEAD"]

        self.jira = JIRA(f"https://{self.jira_host}", auth=(self.jira_username, self.jira_password))

        self.bot_token = os.environ["BOT_TOKEN"]
        self.chat_id = os.environ["CHAT_ID"]
        self.telegram_proxy = os.environ.get("TELEGRAM_PROXY")

        self.workflow_matrix = self._load_workflow_matrix()

    def _load_workflow_matrix(self) -> dict:
        """Load workflow matrix from JSON file."""
        try:
            with open("workflow_matrix.json", "r") as f:
                return json.load(f)
        except Exception as e:
            raise RuntimeError(f"Error loading workflow_matrix.json: {e}")

    def extract_jira_tickets(self, commits: list[str]) -> list[str]:
        """Extract JIRA ticket IDs from commit messages."""
        pattern = re.compile(r'[A-Z]+-\d+')
        tickets, seen = [], set()
        for commit in commits:
            for match in pattern.findall(commit):
                if match not in seen:
                    seen.add(match)
                    tickets.append(match)
        return tickets

    def find_issues(self, tickets: list[str]) -> list[Issue]:
        """Fetch issues from JIRA API."""
        issues: list[Issue] = []
        for ticket in tickets:
            try:
                issue = self.jira.issue(ticket)
                issues.append(issue)
            except JIRAError as e:
                print(f"Error getting issue {ticket}: {e}")
            except Exception as e:
                print(f"Unexpected error getting issue {ticket}: {e}")
        return issues

    def _find_path_to_target(self, issue_type: str, current_status: str, target_status: str) -> list[str]:
        """Find path from current_status to target_status using BFS."""
        if issue_type not in self.workflow_matrix:
            return []

        if current_status == target_status:
            return [current_status]

        issue_workflow = self.workflow_matrix[issue_type]
        queue = deque([(current_status, [current_status])])
        visited = {current_status}

        while queue:
            status, path = queue.popleft()

            if status not in issue_workflow:
                continue

            for next_status in issue_workflow[status].keys():
                if next_status == target_status:
                    return path + [next_status]

                if next_status not in visited:
                    visited.add(next_status)
                    queue.append((next_status, path + [next_status]))

        return []

    def change_issue_status(self, issue: Issue, target_status: str) -> tuple[bool, str]:
        """
        Transition issue to target status using workflow matrix path.
        Returns (success, message).
        """
        try:
            issue_type = issue.fields.issuetype.name
            current_status = issue.fields.status.name

            if issue_type not in self.workflow_matrix:
                return False, f"{issue.key} - issue type '{issue_type}' not in workflow matrix"

            path = self._find_path_to_target(issue_type, current_status, target_status)

            if not path:
                return False, f"{issue.key} - no path from '{current_status}' to '{target_status}'"

            # Follow the path
            for i in range(len(path) - 1):
                from_status = path[i]
                to_status = path[i + 1]
                transition_name = self.workflow_matrix[issue_type][from_status][to_status]

                transitions = self.jira.transitions(issue)
                transition_id = None
                for t in transitions:
                    if t['name'] == transition_name:
                        transition_id = t['id']
                        break

                if transition_id:
                    self.jira.transition_issue(issue, transition_id)
                    issue = self.jira.issue(issue.key)
                else:
                    return False, f"{issue.key} - transition '{transition_name}' not available"

            return True, f"{issue.key} - status changed to {target_status}"
        except Exception as e:
            return False, f"{issue.key} - error changing status: {e}"

    def change_assignee(self, issue: Issue) -> tuple[bool, str]:
        """
        Change issue assignee based on Reporter.
        Returns (success, message).
        """
        try:
            reporter = issue.fields.reporter.name if issue.fields.reporter else None

            if not reporter:
                return False, f"{issue.key} - no reporter found"

            if reporter in self.jira_qa_testers:
                assignee = reporter
            else:
                assignee = self.jira_qa_lead

            issue.update(assignee={"name": assignee})
            return True, f"{issue.key} - assigned to {assignee}"
        except Exception as e:
            return False, f"{issue.key} - error changing assignee: {e}"

    def process_release(self, environment: str, release: str, rc: str, commits: list[str]) -> dict:
        """
        Process release: extract tickets, change statuses and assignees.
        Returns dict with results.
        """
        results = {
            "environment": environment,
            "release": release,
            "rc": rc,
            "tickets_found": 0,
            "status_changes": [],
            "assignee_changes": [],
            "issues": [],
        }

        tickets = self.extract_jira_tickets(commits)
        results["tickets_found"] = len(tickets)

        if not tickets:
            return results

        issues = self.find_issues(tickets)

        for issue in issues:
            results["issues"].append(issue)

            # Change status
            issue_type = issue.fields.issuetype.name
            target_status = "DEV Ready For Testing" if issue_type == "Bug" else "Testing"
            success, msg = self.change_issue_status(issue, target_status)
            results["status_changes"].append((success, msg))

            # Change assignee
            success, msg = self.change_assignee(issue)
            results["assignee_changes"].append((success, msg))

        return results

    def build_message(self, environment: str, release: str, rc: str, issues: list[Issue]) -> str:
        """Build Telegram message from issues."""
        lines = [f"\U0001f4cb На {environment} {release}-rc{rc}:"]
        for issue in issues:
            url = f"{self.jira_base}/{issue.key}"
            title = issue.fields.summary
            safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f'<a href="{url}">{issue.key} - {safe_title}</a>')
        return "\n\n".join(lines)

    def send_telegram(self, message: str) -> bool:
        """Send message to Telegram. Returns success status."""
        try:
            proxies = {"https": self.telegram_proxy} if self.telegram_proxy else None
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                proxies=proxies,
                timeout=15,
            )
            return resp.ok
        except Exception as e:
            print(f"Telegram error: {e}")
            return False
