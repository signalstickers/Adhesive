import io

import anyio
from signalstickers_client import models as signal_models
from lottie.importers.core import import_tgs
from telethon import tl

async def convert_to_signal(tg_client, signal_client, pack_name):
	tg_pack = await tg_client(tl.functions.messages.GetStickerSetRequest(
		stickerset=tl.types.InputStickerSetShortName(short_name=pack_name)
	))

	# we use a dict so that we can preserve order as stickers are downloaded asynchronously
	stickers = {}

	signal_pack = signal_models.LocalStickerPack()
	signal_pack.title = tg_pack.set.title
	signal_pack.author = 'https://t.me/addstickers/' + pack_name

	async with anyio.create_task_group() as tg:
		for i, tg_sticker in enumerate(tg_pack.documents):
			await tg.spawn(add_tg_sticker, tg_client, stickers, i, tg_sticker)

	for i in range(len(stickers)):
		signal_pack.stickers.append(stickers[i])

	del stickers

	pack_id, pack_key = await signal_client.upload_pack(signal_pack)
	return f'https://signal.art/addstickers/#pack_id={pack_id}&pack_key={pack_key}'

async def add_tg_sticker(tg_client, signal_stickers: dict, sticker_id: int, tg_sticker):
	signal_sticker = signal_models.Sticker()
	signal_sticker.id = sticker_id
	signal_sticker.emoji = next(
		attr
		for attr in tg_sticker.attributes
		if isinstance(attr, tl.types.DocumentAttributeSticker)
	).alt

	data = io.BytesIO()
	async for chunk in tg_client.iter_download(tg_sticker):
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
