import io
import gzip
import logging
import urllib.parse

import anyio
from signalstickers_client import models as signal_models
#from lottie.importers.core import import_tgs
from telethon import tl

#from .apng import export_apng

logger = logging.getLogger(__name__)

THREAD_LIMITER = None

async def convert_interactive(tg_client, stickers_client, link):
	try:
		converter, pack_info = parse_link(link)
	except ValueError:
		yield 'Invalid sticker pack link provided. Run /start for help.'
		return

	yield (
		f'Converting this pack to {"Signal" if converter is convert_to_signal else "Telegram"}. '
		'Hold on to your butts…'
	)

	try:
		converted_link = await converter(tg_client, stickers_client, *pack_info)
	except NotImplementedError as exc:
		yield exc.args[0]
	else:
		yield converted_link

def parse_link(link: str):
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
	except KeyError:
		raise ValueError

	return converter, pack_info

async def convert_to_signal(tg_client, stickers_client, pack_name):
	input_sticker_set = tl.types.InputStickerSetShortName(short_name=pack_name)
	tg_pack = await tg_client(tl.functions.messages.GetStickerSetRequest(stickerset=input_sticker_set))
	if tg_pack.set.animated:
		raise NotImplementedError('Animated packs are not supported yet.')

	# we use a dict so that we can preserve order as stickers are downloaded asynchronously
	stickers = {}

	signal_pack = signal_models.LocalStickerPack()
	signal_pack.title = tg_pack.set.title
	signal_pack.author = 'https://t.me/addstickers/' + pack_name

	async with anyio.create_task_group() as tg:
		if tg_pack.set.thumb is not None:
			await tg.spawn(download_tg_cover, tg_client, signal_pack, tg_pack)
		for i, tg_sticker in enumerate(tg_pack.documents):
			await tg.spawn(add_tg_sticker, tg_client, stickers, i, tg_sticker)

	for i in range(len(stickers)):
		signal_pack.stickers.append(stickers[i])

	del stickers

	pack_id, pack_key = await stickers_client.upload_pack(signal_pack)
	return f'https://signal.art/addstickers/#pack_id={pack_id}&pack_key={pack_key}'

async def download_tg_cover(tg_client, signal_pack, tg_pack):
	signal_sticker = signal_models.Sticker()
	signal_sticker.id = tg_pack.set.count
	thumb = tg_pack.set.thumb
	signal_sticker.image_data = await tg_client.download_file(
		tl.types.InputStickerSetThumb(
			stickerset=tl.types.InputStickerSetShortName(short_name=tg_pack.set.short_name),
			volume_id=tg_pack.set.thumb.location.volume_id,
			local_id=tg_pack.set.thumb.location.local_id,
		),
		file=bytes,
	)
	signal_pack.cover = signal_sticker

async def add_tg_sticker(tg_client, signal_stickers: dict, sticker_id: int, tg_sticker):
	signal_sticker = signal_models.Sticker()
	signal_sticker.id = sticker_id
	signal_sticker.emoji = next(
		attr
		for attr in tg_sticker.attributes
		if isinstance(attr, tl.types.DocumentAttributeSticker)
	).alt

	logger.debug('Downloading %s', signal_sticker.emoji)
	data = io.BytesIO()
	async for chunk in tg_client.iter_download(tg_sticker):
		data.write(chunk)
	data.seek(0)
	logger.debug('Downloaded %s', signal_sticker.emoji)

	if tg_sticker.mime_type == 'application/x-tgsticker':
		logger.debug('Converting %s to APNG', signal_sticker.emoji)
		image_data = await convert_tgs_to_apng(data)
	elif tg_sticker.mime_type == 'image/webp':
		image_data = data
	else:
		raise RuntimeError('unexpected image type', tg_sticker.mime_type, 'found in pack')

	signal_sticker.image_data = image_data.getvalue()

	signal_stickers[sticker_id] = signal_sticker

async def convert_tgs_to_apng(data):
	global THREAD_LIMITER

	decompressed = io.BytesIO()
	with gzip.open(data) as gz:
		decompressed.write(gz.read())

	decompressed.seek(0)
	del data

	apng = io.BytesIO()
	anim = import_tgs(decompressed)
	# make sure we share the same thread limiter so that no more than one thread is used for APNG conversion
	# globally
	# otherwise we get OOM-killed lmao
	if THREAD_LIMITER is None:
		THREAD_LIMITER = anyio.create_capacity_limiter(1)
	await anyio.run_sync_in_worker_thread(export_apng, anim, apng, limiter=THREAD_LIMITER)
	return apng

async def convert_to_telegram(tg_client, stickers_client, pack_id, pack_key):
	raise NotImplementedError('Signal → Telegram conversion is not supported yet.')
