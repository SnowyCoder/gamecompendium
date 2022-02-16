# Game Compendium
A fast modular flexible search engine in the palm of your hands

#### Table of Contents
- [Summary](#summary)
- [How to Run](#how-to-run)
  - [Configuration](#configuration)
  - [Dependencies](#dependencies)
  - [Running](#running)
  - [Evaluation](#evaluation)
- [Query Language](#query-language)
- [Adding Sources](#adding-sources)
- [Technical Info](#technical-info)
  - [Query Aggregation](#query-aggregation)
  - [Entity Resolution](#entity-resolution)

## Summary
This project indexes **every game from both [IGDB](https://www.igdb.com/)
and [Steam](https://store.steampowered.com/)**,
indexing them in separate indices. When a query is run it will run in both
indices and the results will be aggregated using a custom version of the
top-k threshold algorithm.

Since there are a lot of documents (games) indexing all of them will take
quite a long time (30 minutes to 1 hour), most of it is used in entity resolution.
this time could be reduced using multiprocessing, but this is outside our
project's scope.

Dumping the data will take a MUCH longer time, since steam has very strict
rate limits. We suggest using shared dumps instead of downloading them
by hand (it would take 2-4 days).

## How to Run
### Configuration
The first thing you should do is setup your config file.
```bash
$ cp config.example.toml config.toml
$ vi config.toml
```
If you work with already dumped data you only
need to configure `download_full` that will select how many games to index.
If you set it to `false` only ~10% of the most famous games will be used,
allowing for faster iteration times.

### Dependencies

This project uses [poetry](https://python-poetry.org/) for dependency management.

Install poetry then run
```bash
$ poetry shell
```
To get a shell within a virtual environment with the project dependencies
(the first time will take a minute or two).

### Running

```bash
$ python3 gamecompendium/main.py
```
To start the project in "prompt mode", append to the last command `--help`
to see all the arguments it accepts.

```bash
$ python3 gamecompendium/main.py --help
usage: main.py [-h] [--only {igdb,steam}] {scrape,index,evaluate} ...

All the best games on the tip of your tongue

positional arguments:
  {scrape,index,evaluate}
    scrape              Only download the required data (will take a while)
    index               Only index the sources
    evaluate            Evaluate

options:
  -h, --help            show this help message and exit
  --only {igdb,steam}, -o {igdb,steam}
                        Only use determined data sources
```

Using `scrape` will only download games and write them to the dumps
(if they haven't been fully downloaded yet).
`index` will only index the documents and quit, scraping them only if necessary.
In all sub-commands (except `evaluate`) you can use `--only {igdb,steam}` to
limit the sources to process.

WARNING: when indexing it's best NOT to limit the sources used since
entity resolution only works if all sources are present.

If you only want to query steam games you can run
```bash
$ python3 gamecompendium/main.py --only steam
```

You can use `--force` to re-index your documents
```bash
$ python3 gamecompendium/main.py index --force
```

And you can use `--update` to update your dumps with
new games (old games won't be updated).
```bash
$ python3 gamecompendium/main.py scrape --update
```

### Evaluation
Automatic evaluation is also supported! (whohoo!).
To use it run
```bash
$ python3 gamecompendium/main.py evaluate main.benchmark
```
It will run our [main benchmark](main.benchmark) and print results to console
once it's done.

The code computes: Discounted Cumulative Gain (raw and normalized),
precision (natural and standard), average precision (raw and interpolated) and
mean average precision.

## Query Language
We used the default
[whoosh query language](https://whoosh.readthedocs.io/en/latest/querylang.html)
with some [bug fixes](https://github.com/mchaput/whoosh/pull/23) and minor
improvements to have a better seamless experience.

By default, every term will be searched in both name, summary and story line,
giving more weight to the name, also the OR conjunction is used by default:
"portal 2" will search portal OR 2 in every name, summary and storyline.
This gives us more results but since score is added the search experience should
be the same, just more resilient.
If you don't want to use this default behaviours you can type it manually:
`name:portal AND name:2` or `name:(portal AND 2)`.

For better integration with lazy-typed queries we also give a boost to
specified fields.
In the query `portal date:2011` the `date:` part of the query will have
more weight than the unspecified part.
Same with `Gran Theft Auto name:(San Andreas)`, the manually-specified name
will take more weight in the query scoring.

If you want to add more weight to a part of the query you can do so with the
caret operator: `name:grand name:theft^2` ("theft" will have twice the weight
of "grand")

You can also use phrase queries (`"grand theft auto"`), positional phrase queries
(`"grand auto"~2` where "grand" is at max 2 word distant from "auto"), range
queries `"grand theft auto" AND date:[2005 to 2010]"`. For more examples [check out
our benchmark](main.benchmark)




## Adding sources
Steam and IGDB don't have all the games you need? That's what we think too!
Luckily it's really easy to add additional sources to game compendium!

Write your own implementation that satisfies `source.py`
[protocol](https://www.python.org/dev/peps/pep-0544/)
then add an instance of it in `app.py`'s `DEFAULT_SOURCES`, it's that easy!
Our algorithms are thought with extensibility in mind and they will
work with 2, 3 or 10 information sources!

## Technical Info
There ae multiple considerable technical barriers we had to overcome,
we'll discuss them here shortly, check out the source code for
more details.

### Query Aggregation
#### [go to file](gamecompendium/aggregator.py)

We use a slightly different version of the **Top-k
Threshold algorithm** (Fagin et al. 2001*) (random access version).
Since games aren't always in all the sources, we need to change the
score aggregation function.
Instead of summing results from different sources we **average** the scores.
So if instance x is found in source A, B, C `Sx = (Sxa + Sxb + Sxc) / 3`,
while if instance y is found only in B and C `Sy = (Syb + Syc) / 2`.
This means that entities do not gain anything from being in multiple sources.
To make this work efficiently the threshold computation should also be different,
we can prove mathematically that `threshold = max(cdim1.score, ..., cdiml.score)`,
is the minimum threshold function for this case, and this is the formula
that we're using right now ([**mathematical proof** in the source code](
gamecompendium/aggregator.py)).

### Entity Resolution
#### [go to file](gamecompendium/resolver.py)

Games don't have a "hard" definition as games are only what we (as humans) think
of them. **We found this "definition" of game similar to the goal of Information
Retrieval**, we then use the system itself to help us discriminate entities.

The idea is this: for the first source indexed, every game will have its own
entity, from the second source the IR system would search each game in the already
indexed sources (with various heuristics), and if an entity is found, it will
be reused, otherwise another entity will be generated.
We call this **Recursive Entity Resolution**.

