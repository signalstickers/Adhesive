#!/usr/bin/env python3

import io
import textwrap
import urllib.parse

import anyio
import telethon
from telethon import TelegramClient, errors, events, tl
from signalstickers_client import StickersClient as SignalStickersClient
from signalstickers_client import models as signal_models
from lottie.importers.core import import_tgs

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
	await converter(event, *pack_info)

async def convert_to_signal(event, pack_name):
	tg_pack = await event.client(tl.functions.messages.GetStickerSetRequest(
		stickerset=tl.types.InputStickerSetShortName(short_name=pack_name)
	))

	# we use a dict so that we can preserve order as stickers are downloaded asynchronously
	stickers = {}

	signal_pack = signal_models.LocalStickerPack()
	signal_pack.title = tg_pack.set.title
	signal_pack.author = 'https://t.me/addstickers/' + pack_name

	async with anyio.create_task_group() as tg:
		for i, tg_sticker in enumerate(tg_pack.documents):
			await tg.spawn(add_tg_sticker, event, stickers, i, tg_sticker)

	for i in range(len(stickers)):
		signal_pack.stickers.append(stickers[i])

	del stickers

	pack_id, pack_key = await event.client.signal_client.upload_pack(signal_pack)
	await event.respond(f'https://signal.art/addstickers/#pack_id={pack_id}&pack_key={pack_key}')

async def add_tg_sticker(event, signal_stickers: dict, sticker_id: int, tg_sticker):
	signal_sticker = signal_models.Sticker()
	signal_sticker.id = sticker_id
	signal_sticker.emoji = next(
		attr
		for attr in tg_sticker.attributes
		if isinstance(attr, tl.types.DocumentAttributeSticker)
	).alt

	data = io.BytesIO()
	async for chunk in event.client.iter_download(tg_sticker):
		data.write(chunk)
	data.seek(0)

	if tg_sticker.mime_type == 'application/x-tg-sticker':
		webp_data = convert_tgs_to_webp(data)
	elif tg_sticker.mime_type == 'image/webp':
		webp_data = data
	else:
		raise RuntimeError('unexpected image type', tg_sticker.mime_type, 'found in pack', pack_name)

	signal_sticker.image_data = data.getvalue()

	signal_stickers[sticker_id] = signal_sticker

def convert_tgs_to_webp(data):
	decompressed = io.BytesIO()
	with gzip.open(data) as gz:
		decompressed.write(gz.read())

	decompressed.seek(0)
	del data

	anim = import_tgs(decompressed)


async def convert_to_telegram(event, pack_id, pack_key):
	...

def build_client():
	import toml
	with open('config.toml') as f:
		config = toml.load(f)
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

async def main():
	client = build_client()
	await client.start(bot_token=client.config['api_token'])
	async with client:
		await client.run_until_disconnected()

if __name__ == '__main__':
	anyio.run(main)
