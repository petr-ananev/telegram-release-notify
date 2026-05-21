#!/usr/bin/env python3
"""CLI version for direct script invocation."""

import argparse
import sys

from dotenv import load_dotenv

from release_notifier import ReleaseNotifier

load_dotenv()


def main() -> None:
    """Run release notification via CLI."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Send release notification to Telegram")
    parser.add_argument("environment", help="Environment, e.g. QA")
    parser.add_argument("release", help="Release version, e.g. 26.1.0")
    parser.add_argument("rc", help="RC number, e.g. 7")
    parser.add_argument("commits", nargs="+", help='Commit strings, e.g. "abc123(BugFix DEV-123 Fix something)"')
    args = parser.parse_args()

    environment = args.environment
    release = args.release
    rc = args.rc
    commits = args.commits

    print(f"Release: {release}-rc{rc}")
    print(f"Commits: {commits}\n")

    try:
        notifier = ReleaseNotifier()

        # Process release
        print("Processing...")
        results = notifier.process_release(environment, release, rc, commits)

        print(f"\nFound tickets: {results['tickets_found']}")
        print("\nStatus changes:")
        for success, msg in results["status_changes"]:
            print(f"  {'✅' if success else '❌'} {msg}")

        print("\nAssignee changes:")
        for success, msg in results["assignee_changes"]:
            print(f"  {'✅' if success else '❌'} {msg}")

        # Send telegram
        if results["issues"]:
            print("\nBuilding Telegram message...")
            message = notifier.build_message(environment, release, rc, results["issues"])

            print("\n--- Telegram message ---")
            print(message)
            print("-----------------------\n")

            if notifier.send_telegram(message):
                print("✅ Message sent to Telegram successfully.")
            else:
                print("❌ Failed to send message to Telegram.")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
