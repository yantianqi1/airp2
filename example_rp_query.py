"""CLI demo for RP query context + grounded response."""
import argparse
import json

from api.rp_query_api import RPQueryService


def main():
    parser = argparse.ArgumentParser(description="RP Query Demo")
    parser.add_argument("--session", default="demo-session", help="Session ID")
    parser.add_argument("--message", required=True, help="User message")
    parser.add_argument("--unlocked", type=int, default=None, help="Max unlocked chapter")
    parser.add_argument(
        "--active-character",
        action="append",
        dest="active_characters",
        default=None,
        help="Active character (repeatable)",
    )
    args = parser.parse_args()

    service = RPQueryService.from_config_file("config.yaml")

    context = service.query_context(
        message=args.message,
        session_id=args.session,
        unlocked_chapter=args.unlocked,
        active_characters=args.active_characters,
    )
    response = service.respond(
        message=args.message,
        session_id=args.session,
        worldbook_context=context["worldbook_context"],
        citations=context["citations"],
        unlocked_chapter=args.unlocked,
        active_characters=args.active_characters,
    )

    print("=" * 80)
    print("[Worldbook Context]")
    print(json.dumps(context, ensure_ascii=False, indent=2))
    print("\n" + "=" * 80)
    print("[Assistant Reply]")
    print(response["assistant_reply"])


if __name__ == "__main__":
    main()
