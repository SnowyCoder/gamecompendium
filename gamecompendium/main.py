import asyncio
from app import App, DEFAULT_SOURCES
from benchmark import parse_suite
import argparse
import math
import collections
INDEX_DIR = 'indexes'


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
        for el in res:
            
            print(f"{el}")
            
            # DCG
            val = (el.raw[0]  + sum([(el.raw[i]/math.log(i+1,2)) for i in range(1,len(el.raw))])  )
            print(f"DCG: {val}")
            
            # IDEAL DCG
            ideal_list = sorted(el.raw,reverse=True)
            val_ideal = (ideal_list[0]  + sum([(ideal_list[i]/math.log(i+1,2)) for i in range(1,len(ideal_list))])  )
            
            print(f"IDEAL DCG: {val_ideal}")
            print(f"NDCG: {val/val_ideal}")
            
            # NATURAL PRECISION
            natural_pr = {}
            doc_count = 0
            tot_rel = sum([1 for elem in el.raw if elem != 0])
            for i in range(len(el.raw)):
                if el.raw[i] != 0:
                    doc_count += 1
                    precision = doc_count/(i+1)
                    natural_pr[doc_count/tot_rel] = precision
            print("Natural precision: ")
            print(" | ".join([f"{key}:{value}" for key,value in natural_pr.items()]))
            
            # STANDARD PRECISION
            precisions = {}
            for i in range(len(el.raw)-1,-1,-1):
                maxval = max([value for key,value in natural_pr.items() if key >= (i/10)])
                precisions[(i+1)/10] =  maxval
            ord_prec = collections.OrderedDict(sorted(precisions.items()))
            print("Standard precision: ")
            print(" | ".join([f"{key}:{value}" for key,value in ord_prec.items()]))
            
            avg_prc = sum(list(natural_pr.values()))/tot_rel
            print(f"Average non-interpolated precision: {avg_prc}")
            
            avg_int_prc = sum(list(precisions.values()))/10
            avg_precisions.append(avg_int_prc)
            print(f"Average interpolated precision: {avg_int_prc}")
            print("\n")
        
        mean_avg = sum(avg_precisions)/len(res)
        print(f"Mean average precision: {mean_avg}")
            
    else:
        print("Unknown action: " + args.action)


if __name__ == '__main__':
    asyncio.run(main())
