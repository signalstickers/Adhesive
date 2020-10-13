#!/usr/bin/env python3

import anyio
from signalstickers_client import StickersClient as SignalStickersClient

INTRO = """\
Hi there! I'm a simple bot that converts Telegram stickers to Signal stickers and back.
To begin, send me a link to either kind of sticker pack. Here's what a Telegram sticker pack looks like:
`https://t.me/addstickers/animals`
And here's a Signal sticker pack:
`https://signal.art/addstickers/#pack_id=9acc9e8aba563d26a4994e69263e3b25&pack_key=5a6dff3948c28efb9b7aaf93ecc375c69fc316e78077ed26867a14d10a0f6a12`

This bot is open-source software under the terms of the AGPLv3 license. You can find the source code at:
"""

def build_stickers_client(config):
	return SignalStickersClient(
		config['signal']['stickers']['username'],
		config['signal']['stickers']['password'],
	)

async def main():
	import logging
	logging.basicConfig(level=logging.INFO)

	import toml
	with open('config.toml') as f:
		config = toml.load(f)

	stickers_client = build_stickers_client(config)

	from .telegram_bot import (
		build_client as build_tg_client,
		run as run_telegram,
	)
	from .signal_bot import (
		build_client as build_signal_client,
		run as run_signal,
	)

	tg_client = build_tg_client(config, stickers_client)
	signal_client = build_signal_client(config, tg_client, stickers_client)

	async with anyio.create_task_group() as tg:
		await tg.spawn(run_telegram, tg_client)
		await tg.spawn(run_signal, signal_client)

if __name__ == '__main__':
	anyio.run(main)
