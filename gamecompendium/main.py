import asyncio
from app import App, DEFAULT_SOURCES
from benchmark import parse_suite
import argparse
import math

INDEX_DIR = 'indexes'
# Everything >= 2 is "relevant" (used for everything except DCG-related stuff)
RELEVANCE_THRESHOLD = 2


def compute_discounted_cumulative_gain(data: list[int]) -> int:
    if len(data) == 0:
        return 0
    return data[0] + sum([(data[i] / math.log(i + 1, 2)) for i in range(1, len(data))])


async def main():
    possible_sources = [x.name for x in DEFAULT_SOURCES]
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--only', '-o', action='store', help='Only use determined data sources',
                        choices=possible_sources)

    parser = argparse.ArgumentParser(description='All the best games on the tip of your tongue', parents=[common])
    parser.set_defaults(action='prompt')
    subparsers = parser.add_subparsers()

    scrape = subparsers.add_parser('scrape', help='Only download the required data (will take a while)', parents=[common])
    scrape.set_defaults(action='scrape')
    scrape.add_argument('--update', help="Update the dumped files with new entries", action='store_const', const=True, default=False)
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
        await app.scrape(update=args.update)
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
        avg_precisions = []
        interp_precisions = [0] * 10
        for el in res:
            print(f"{el.query.query} : {[x.relevance for x in el.query.scores]} {el.raw}")

            # DCG
            val = compute_discounted_cumulative_gain(el.raw)
            print(f"DCG: {val}")

            # IDEAL DCG
            ideal_list = sorted([x.relevance for x in el.query.scores], reverse=True)
            val_ideal = compute_discounted_cumulative_gain(ideal_list)

            print(f"IDEAL DCG: {val_ideal}")
            print(f"NDCG: {val/val_ideal}")

            # NATURAL PRECISION
            natural_pr = []
            tot_rel = sum([x.relevance >= RELEVANCE_THRESHOLD for x in el.query.scores])
            for i, entry in enumerate(el.raw):
                if entry >= RELEVANCE_THRESHOLD:
                    precision = (len(natural_pr) + 1)/(i + 1)
                    natural_pr.append(precision)
            print("Natural precision: ")
            print(" | ".join([f"{(i + 1) / tot_rel}:{value}" for i, value in enumerate(natural_pr)]))

            # STANDARD PRECISION
            precisions = [0.0] * 10
            for i in range(10):
                maxval = max([value for j, value in enumerate(natural_pr) if (j + 1) / tot_rel >= (i + 1) / 10], default=0)
                precisions[i] = maxval
                interp_precisions[i] += maxval
            print("Standard precision: ")
            print(" | ".join([f"{(i+1)/10}:{value}" for i, value in enumerate(precisions)]))

            avg_prc = sum(natural_pr) / tot_rel
            print(f"Average non-interpolated precision: {avg_prc}")

            avg_int_prc = sum(precisions) / 10
            avg_precisions.append(avg_int_prc)
            print(f"Average interpolated precision: {avg_int_prc}")
            print("\n")

        mean_avg = sum(avg_precisions)/len(res)
        print(f"Mean average precision: {mean_avg}")
        print("Average Standard precision: ")
        print(" | ".join([f"{(key + 1) / 10}:{value / len(interp_precisions)}" for key, value in enumerate(interp_precisions)]))
            
    else:
        print("Unknown action: " + args.action)


if __name__ == '__main__':
    asyncio.run(main())
