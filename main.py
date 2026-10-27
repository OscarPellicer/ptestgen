"""Entry point of the ``ptestgen`` console script (``main:main``). The parser is in
``ptestgen.cli`` and each command's handler in its own module."""
import logging
import sys


def main():
    if sys.argv[1:] == ["--agents"]:
        from ptestgen.agent_skill import agents_text
        print(agents_text())
        return

    from ptestgen.cli import build_parser, setup_logging
    args = build_parser().parse_args()
    setup_logging(args.log_level)

    if hasattr(args, 'func'):
        try:
            args.func(args)
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}", exc_info=True)
            print(f"\n--- Error ---\nAn unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
