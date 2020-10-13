#!/usr/bin/env python3

import textwrap

import anyio
import telethon
from telethon import TelegramClient, errors, events, tl
from signalstickers_client import StickersClient as SignalStickersClient

from .glue import parse_link

import logging
logging.basicConfig(level=logging.INFO)
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
	try:
		converter, pack_info = parse_link(event.message.message)
	except ValueError:
		await event.respond('Invalid sticker pack link provided. Run /start for help.')
		return

	await event.respond(
		f'Converting this pack to {"Signal" if converter.__name__ == "convert_to_signal" else "Telegram"}. '
		'Hold on to your butts…'
	)

	try:
		converted_link = await converter(event.client, event.client.signal_client, *pack_info)
	except NotImplementedError as exc:
		await event.respond(exc.args[0])
	else:
		await event.respond(converted_link)

def build_client(config):
	tg_config = config['telegram']
	signal_stickers_config = config['signal']['stickers']

	client = TelegramClient(tg_config.get('session_name', 'adhesive'), tg_config['api_id'], tg_config['api_hash'])
	client.config = tg_config
	client.signal_client = SignalStickersClient(
		signal_stickers_config['username'],
		signal_stickers_config['password'],
	)

	for handler in event_handlers:
		client.add_event_handler(handler)

	return client

async def run(config):
	client = build_client(config)
	await client.start(bot_token=client.config['api_token'])
	async with client:
		await client.run_until_disconnected()

def main():
	import toml
	with open('config.toml') as f:
		config = toml.load(f)

	anyio.run(run, config)

if __name__ == '__main__':
	main()
