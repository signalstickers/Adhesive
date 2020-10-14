#!/usr/bin/env python3

import textwrap
from functools import wraps

import anyio
import telethon
from telethon import TelegramClient, errors, events, tl
from signalstickers_client import StickersClient as SignalStickersClient

from .glue import convert_link_interactive, convert_pack_interactive, convert_to_signal
from .bot import INTRO, build_stickers_client

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
	await event.respond(INTRO + event.client.source_code_url)
	raise events.StopPropagation

@register_event(events.NewMessage(pattern=r'^(https?|sgnl|tg)://'))
async def convert(event):
	async for response in convert_link_interactive(event.client, event.client.stickers_client, event.message.message):
		await event.respond(response)
	raise events.StopPropagation

def sticker_message_required(handler):
	@wraps(handler)
	async def wrapped_handler(event):
		message = event.message
		if not isinstance(message.media, tl.types.MessageMediaDocument):
			return
		for attr in message.media.document.attributes:
			if isinstance(attr, tl.types.DocumentAttributeSticker):
				event.sticker_set = attr.stickerset
				return await handler(event)

	return wrapped_handler

@register_event(events.NewMessage)
@sticker_message_required
async def convert_sticker(event):
	async for response in convert_pack_interactive(
		event.client, event.client.stickers_client, convert_to_signal, event.sticker_set,
	):
		await event.respond(response)

def build_client(config, stickers_client):
	tg_config = config['telegram']
	signal_stickers_config = config['signal']['stickers']

	client = TelegramClient(tg_config.get('session_name', 'adhesive'), tg_config['api_id'], tg_config['api_hash'])
	client.config = tg_config
	client.source_code_url = config['source_code_url']
	client.stickers_client = stickers_client

	for handler in event_handlers:
		client.add_event_handler(handler)

	return client

async def run(client):
	await client.start(bot_token=client.config['api_token'])
	client.user = await client.get_me()
	async with client, client.stickers_client:
		await client.run_until_disconnected()

def main():
	import toml
	with open('config.toml') as f:
		config = toml.load(f)

	stickers_client = build_stickers_client(config)
	client = build_client(config, stickers_client)

	anyio.run(run, client)

if __name__ == '__main__':
	main()
