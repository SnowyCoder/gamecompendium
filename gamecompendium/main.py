import asyncio
from app import App, DEFAULT_SOURCES
from benchmark import parse_suite
import argparse

INDEX_DIR = 'indexes'


async def main():
    possible_sources = [x.name for x in DEFAULT_SOURCES]
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--only', '-o', action='store', help='Only use determined data sources',
                        choices=possible_sources)

    parser = argparse.ArgumentParser(description='All the best games on the tip of your tongue', parents=[common])
    parser.set_defaults(action='prompt')
    subparsers = parser.add_subparsers()

    subparsers.add_parser('scrape', help='Only download the required data (will take a while)', parents=[common])\
        .set_defaults(action='scrape')
    index = subparsers.add_parser('index', help='Only index the sources', parents=[common])
    index.set_defaults(action='index')
    index.add_argument('--force', '-f', help="Force a reindexing of the sources", action='store_const', const=True, default=False)
    evaluate = subparsers.add_parser('evaluate', help='Evaluate')
    evaluate.add_argument('file', help="The benchmark to run the IR against", type=argparse.FileType('rt'))
    evaluate.set_defaults(action='evaluate')

    args = parser.parse_args()

    app = App()

    if args.only is None:
        app.add_default_sources()
    else:
        app.add_source(next(x for x in DEFAULT_SOURCES if x.name == args.only))

    if args.action == 'scrape':
        await app.scrape()
    elif args.action == 'index':
        await app.init(force_reindex=args.force)
    elif args.action == 'prompt':
        await app.init()
        app.prompt()
    elif args.action == 'evaluate':
        await app.init()
        with args.file as fd:
            suite = parse_suite(fd)
        res = app.evaluate(suite)
        print(res)
    else:
        print("Unknown action: " + args.action)


if __name__ == '__main__':
    asyncio.run(main())
