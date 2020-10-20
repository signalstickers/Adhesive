import io
import gzip
import random
import logging
import urllib.parse

import anyio
import telethon.utils
import telethon.errors
from signalstickers_client import models as signal_models
#from lottie.importers.core import import_tgs
from telethon import tl

import PIL.Image

#from .apng import export_apng

logger = logging.getLogger(__name__)

THREAD_LIMITER = None

# Yes, this is kind of a jank API. No, I don't really care :)
async def convert_link_interactive(db, tg_client, stickers_client, link):
	try:
		converter, pack_info = parse_link(link)
	except ValueError:
		yield False, 'Invalid sticker pack link provided. Run /start for help.'
		return

	async for is_link, message in convert_pack_interactive(db, tg_client, stickers_client, converter, *pack_info):
		yield is_link, message

IN_PROGRESS = object()

async def convert_pack_interactive(db, tg_client, stickers_client, converter, *pack_info):
	in_progress_message = (
		f'Converting this pack to {"Signal" if converter is convert_to_signal else "Telegram"}. '
		'Hold on to your butts…'
	)

	# This seems like a pretty strange thing to do. Allow me to explain.
	# Converter functions are async generators which are expected to either raise an error,
	# or yield IN_PROGRESS. If they yield, then that means that all checks passed and the conversion
	# has begun. The last thing they should yield is the resulting link.
	started = False
	try:
		async for response in converter(db, tg_client, stickers_client, *pack_info):
			if response is IN_PROGRESS:
				started = True
				yield False, in_progress_message
			else:
				yield response
	except (ValueError, NotImplementedError) as exc:
		yield False, exc.args[0]

def parse_link(link: str):
	parsed = urllib.parse.urlparse(link)
	# TODO deduplicate this mess
	try:
		if parsed.scheme in ('http', 'https'):
			if parsed.netloc in ('t.me', 'telegram.dog'):
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

async def convert_to_signal(db, tg_client, stickers_client, pack):
	if isinstance(pack, str):
		input_sticker_set = tl.types.InputStickerSetShortName(short_name=pack)
	else:
		input_sticker_set = pack
	try:
		tg_pack = await tg_client(tl.functions.messages.GetStickerSetRequest(input_sticker_set))
	except telethon.errors.StickersetInvalidError:
		raise ValueError('Sticker pack not found.')

	row = await db.fetchone(
		"""
		SELECT signal_pack_id, signal_pack_key
		FROM packs
		WHERE tg_hash = ?
		""",
		tg_pack.set.hash,
	)
	if row:
		yield True, (*row, tg_pack_url(tg_pack.set.short_name))
		return

	if tg_pack.set.animated:
		raise NotImplementedError('Animated packs are not supported yet.')

	yield IN_PROGRESS

	signal_pack = signal_models.LocalStickerPack()
	signal_pack.title = tg_pack.set.title
	signal_pack.stickers = [None] * tg_pack.set.count
	signal_pack.author = tg_pack_url(tg_pack.set.short_name)

	if tg_pack.set.thumb is not None:
		await download_tg_cover(tg_client, signal_pack, tg_pack)
	for i, tg_sticker in enumerate(tg_pack.documents):
		await add_tg_sticker(tg_client, signal_pack, i, tg_sticker)

	pack_info = list(map(bytes.fromhex, await stickers_client.upload_pack(signal_pack)))

	await db.execute(
		"""
		INSERT INTO packs (tg_hash, signal_pack_id, signal_pack_key)
		VALUES (?, ?, ?)
		ON CONFLICT DO NOTHING
		""",
		tg_pack.set.hash, *pack_info,
	)

	yield True, (*pack_info, tg_pack_url(tg_pack.set.short_name))

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

async def add_tg_sticker(tg_client, signal_pack: signal_models.LocalStickerPack, sticker_id: int, tg_sticker):
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

	signal_pack.stickers[sticker_id] = signal_sticker

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

async def convert_to_telegram(_, tg_client, stickers_client, pack_id, pack_key):
	# first make sure it's a valid sticker pack
	try:
		pack = await stickers_client.get_pack(pack_id, pack_key)
	except Exception:
		raise ValueError('Sticker pack not found.')

	stickers = []

	# then make sure we haven't already converted this one
	# this _by_<bot username> suffix is mandatory
	tg_short_name = f'signal_{pack_id}_by_{tg_client.user.username}'

	try:
		await tg_client(tl.functions.messages.GetStickerSetRequest(tl.types.InputStickerSetShortName(tg_short_name)))
	except telethon.errors.StickersetInvalidError:
		pass
	else:
		raise ValueError('This sticker pack has been converted before as ' + tg_pack_url(tg_short_name))

	yield IN_PROGRESS

	# used to do this in parallel but that just caused a lot of rate-limiting
	for sticker in pack.stickers:
		stickers.append(await convert_signal_sticker(tg_client, sticker))

	title = f'{pack.title} by {pack.author}'
	if len(title) > 64:
		title = pack.title
	if len(title) > 64:
		title = textwrap.shorten(title, 64, placeholder=' …')

	try:
		tg_pack = await tg_client(tl.functions.stickers.CreateStickerSetRequest(
			# this user id can be anyone but it has to not be a bot
			user_id='gnu_unix_grognard',
			title=title,
			short_name=tg_short_name,
			stickers=stickers,
			thumb=pack.cover and await upload_document(
				tg_client,
				'image/png',
				await webp_to_png(pack.cover.image_data, thumbnail=True)
			),
		))
	except telethon.errors.rpcerrorlist.ShortnameOccupyFailedError:
		# handle a race condition occurring when the same pack is sent to us to convert to signal twice
		raise ValueError('This sticker pack has been converted before as ' + tg_pack_url(tg_short_name))

	yield True, tg_pack_url(tg_pack.set.short_name)

async def convert_signal_sticker(tg_client, signal_sticker):
	return tl.types.InputStickerSetItem(
		document=await upload_document(tg_client, 'image/png', await webp_to_png(signal_sticker.image_data)),
		emoji=signal_sticker.emoji,
	)

async def upload_document(tg_client, mime_type: str, data: bytes):
	media = await tg_client(tl.functions.messages.UploadMediaRequest('me', await tg_client.upload_file(data)))
	return telethon.utils.get_input_document(media)

def signal_pack_url(pack_id, pack_key):
	if isinstance(pack_id, bytes): pack_id = pack_id.hex()
	if isinstance(pack_key, bytes): pack_key = pack_key.hex()
	return f'https://signal.art/addstickers/#pack_id={pack_id}&pack_key={pack_key}'

def tg_pack_url(short_name):
	domain = random.choices(('t.me', 'telegram.dog'), weights=(0.75, 0.25))[0]
	return f'https://{domain}/addstickers/{short_name}'

async def webp_to_png(image_data: bytes, *, thumbnail=False) -> bytes:
	return await anyio.run_sync_in_worker_thread(_webp_to_png, image_data, thumbnail)

def _webp_to_png(image_data: bytes, thumbnail=False) -> bytes:
	input = io.BytesIO(image_data)
	input.seek(0)
	im = PIL.Image.open(input)
	if thumbnail:
		# normally this would distort the image, but we assume that all stickers are square anyway
		im = im.resize((100, 100))
	out = io.BytesIO()
	im.save(out, format='PNG')
	del input
	return out.getvalue()

async def propose_to_signalstickers_dot_com(http, metadata: dict, *, token, test_mode=False):
	metadata['test_mode'] = test_mode
	r = await http.post(
		'https://api.signalstickers.com/propose',
		json=metadata,
		headers={'X-Auth-Token': token},
		timeout=60,
	)
	return r.status_code, r.json()
