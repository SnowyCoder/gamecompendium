from pathlib import Path

import toml

CONFIG_PATH = Path('./config.toml')

if not CONFIG_PATH.exists():
    raise Exception("Config not found")

with CONFIG_PATH.open('rt') as fd:
    config = toml.load(fd)


