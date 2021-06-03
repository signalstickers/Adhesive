#!/usr/bin/env python3

import anyio
from .stickers_client import MultiStickersClient, CREATE_PACK_RL
import asqlite

INTRO = """\
Hi there! I'm a simple bot that converts Telegram stickers to Signal stickers and back.
To begin, send me a link to either kind of sticker pack. Here's what a Telegram sticker pack looks like:
`https://t.me/addstickers/animals`
And here's a Signal sticker pack:
`https://signal.art/addstickers/#pack_id=9acc9e8aba563d26a4994e69263e3b25&pack_key=5a6dff3948c28efb9b7aaf93ecc375c69fc316e78077ed26867a14d10a0f6a12`

You can also just send me a sticker and I'll convert the pack that it's from.

This bot is open-source software under the terms of the AGPLv3 license. You can find the source code at:
"""

async def build_stickers_client(db, config):
	accounts = {account['username']: account for account in config['signal']['stickers']['accounts']}
	bucket_rows = await db.fetchall('SELECT account_id, space_remaining, last_updated_at FROM signal_accounts')
	for row in bucket_rows:
		row = dict(row)
		username = row.pop('account_id')
		try:
			accounts[username]['bucket'] = CREATE_PACK_RL.new(**row)
		except KeyError:
			continue

	return MultiStickersClient(db, accounts.values())

async def main():
	import toml
	with open('config.toml') as f:
		config = toml.load(f)

	import logging
	# shockingly, this is really how the docs want you doing it
	log_level = getattr(logging, config.get('log_level', 'INFO').upper(), None)
	if not isinstance(log_level, int):
		import sys
		logging.basicConfig(level=logging.ERROR)
		logging.error('Invalid log level %s specified!', log_level)
		sys.exit(1)

	logging.basicConfig(level=log_level)

	from .telegram_bot import (
		build_client as build_tg_client,
		run as run_telegram,
	)
	from .signal_bot import (
		build_client as build_signal_client,
		run as run_signal,
	)

	async with asqlite.connect('db.sqlite3') as db, await build_stickers_client(db, config) as stickers_client:
		tg_client = build_tg_client(config, db, stickers_client)
		if config['signal'].get('username'):
			signal_client = build_signal_client(config, db, tg_client, stickers_client)

		async with anyio.create_task_group() as tg:
			await tg.spawn(run_telegram, tg_client)
			if config['signal'].get('username'):
				await tg.spawn(run_signal, signal_client)

if __name__ == '__main__':
	anyio.run(main)
