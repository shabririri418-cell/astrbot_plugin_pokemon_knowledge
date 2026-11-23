"""Read-only query CLI plus an explicit offline sealing command."""
import argparse
import asyncio
import json

from .service import KnowledgeService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='Path to the locally built SQLite database')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('seal', help='Verify and close WAL; stop all writers first')
    search = commands.add_parser('search')
    search.add_argument('query')
    read = commands.add_parser('read')
    read.add_argument('title')
    read.add_argument('--section', default='')
    read.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    if args.command == 'seal':
        from .snapshot import seal_database
        print(json.dumps(seal_database(args.db), ensure_ascii=False, indent=2))
        return
    service = KnowledgeService(args.db)
    if args.command == 'status':
        ready = service.ready()
        value = dict(ready=ready, coverage=service.store.metadata('coverage', {}) if ready else {})
        print(json.dumps(value, ensure_ascii=False, indent=2))
    elif args.command == 'search':
        print(asyncio.run(service.query('search', query=args.query[:160], limit=5, max_chars=6500)))
    else:
        print(asyncio.run(service.query('read', title=args.title[:160], section=args.section[:100],
                                      offset=max(0, args.offset), max_chars=5000)))


if __name__ == '__main__':
    main()
