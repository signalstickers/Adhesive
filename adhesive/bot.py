#!/usr/bin/env python3

import logging

import anyio

from .telegram_bot import run as run_telegram

logging.basicConfig(level=logging.INFO)

async def main():
	import toml
	with open('config.toml') as f:
		config = toml.load(f)

	async with anyio.create_task_group() as tg:
		await tg.spawn(run_telegram, config)

if __name__ == '__main__':
	anyio.run(main)
