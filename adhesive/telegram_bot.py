#!/usr/bin/env python3

import textwrap
import urllib.parse

import telethon
from telethon import TelegramClient, errors, events, tl

import logging
logger = logging.getLogger(__name__)

# so that we can register them all in the correct order later (globals() is not guaranteed to be ordered)
event_handlers = []
def register_event(*args, **kwargs):
	def deco(f):
		event_handlers.append(events.register(*args, **kwargs)(f))
		return f
	return deco

@register_event(events.NewMessage(pattern=r'^/start'))
async def intro(event):
	await event.respond(textwrap.dedent("""
		Hi there! I'm a simple bot that converts Telegram stickers to Signal stickers and back.
		To begin, send me a link to either a sticker pack. Here's what a telegram sticker pack looks like:
		`https://t.me/addstickers/animals`
		And here's a Signal sticker pack:
		`https://signal.art/addstickers/#pack_id=9acc9e8aba563d26a4994e69263e3b25&pack_key=5a6dff3948c28efb9b7aaf93ecc375c69fc316e78077ed26867a14d10a0f6a12`

		This bot is open-source software under the terms of the AGPLv3 license. You can find the source code at:
		https://github.com/iomintz/Adhesive
	"""))

@register_event(events.NewMessage(pattern=r'^(https?|sgnl|tg)://'))
async def convert(event):
	link = event.message.message
	parsed = urllib.parse.urlparse(link)
	# TODO deduplicate this mess
	try:
		if parsed.scheme in ('http', 'https'):
			if parsed.netloc == 't.me':
				pack_info = (parsed.path.rpartition('/')[-1],)
				converter = convert_to_signal
			elif parsed.netloc == 'signal.art':
				query = dict(urllib.parse.parse_qsl(parsed.fragment))
				pack_info = query['pack_id'], query['pack_key']
				converter = convert_to_telegram
			else:
				raise ValueError
		elif parsed.scheme == 'tg':
			pack_info = (parsed.path.rpartition('/')[-1],)
			converter = convert_to_signal
		elif parsed.scheme == 'sgnl':
			query = dict(urllib.parse.parse_qsl(parsed.query))
			pack_info = query['pack_id'], query['pack_key']
			converter = convert_to_telegram
		else:
			raise ValueError
	except (KeyError, ValueError):
		await event.respond('Invalid sticker pack link provided. Run /start for help.')
		return

	await event.respond(f'Parsed link: {converter} {pack_info}')

async def convert_to_signal(event, pack_name):
	...

async def convert_to_telegram(event, pack_id, pack_key):
	...

def build_client():
	import toml
	with open('config.toml') as f:
		config = toml.load(f)['telegram']

	client = TelegramClient(config['session_name'], config['api_id'], config['api_hash'])
	client.config = config

	for handler in event_handlers:
		client.add_event_handler(handler)

	return client

import logging
logging.basicConfig(level=logging.INFO)

async def main():
	client = build_client()
	await client.start(bot_token=client.config['api_token'])
	async with client:
		await client.run_until_disconnected()

if __name__ == '__main__':
	import asyncio
	asyncio.run(main())
