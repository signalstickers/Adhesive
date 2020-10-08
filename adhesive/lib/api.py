import aiohttp
from aiohttp import ClientSession as HttpSession
import dataclasses
import operator
import secrets
import ssl
from dataclasses import dataclass
from typing import List, Tuple, Dict, NewType, Optional
from pathlib import Path

from . import auth
from .crypto import encrypt_attachment
from axolotl.kdf.hkdf import HKDF
from .signal_stickers import StickerImage
from .stickers_pb2 import StickerPack

"""Signal sticker pack API"""

# https://github.com/signalapp/Signal-Desktop/blob/v1.36.3/ts/textsecure/WebAPI.ts

"""PEM encoded public key"""
PemCertificate = NewType('PemCertificate', str)

@dataclass
class WebApi:
	url: str
	cdn_urls: Dict[int, str]
	version: str
	proxy_url: Optional[str] = dataclasses.field(default=None)
	_http: HttpSession = dataclasses.field(default=None, init=False, repr=False)

	def __post_init__(self):
		self._http = HttpSession(
			headers={
				'User-Agent': 'Signal Desktop ' + self.version,
				'X-Signal-Agent': 'OWD',
			},
			trust_env=True,
			raise_for_status=True,
			auth=aiohttp.BasicAuth(*auth.get_credentials()),
		)
		self.ssl = ssl.create_default_context(cafile=Path(__file__).parent / 'signal-ca.crt')

	# fusion of https://github.com/signalapp/Signal-Desktop/blob/v1.36.3/ts/textsecure/WebAPI.ts#L1654-L1705
	# and https://github.com/signalapp/Signal-Desktop/blob/v1.36.3/sticker-creator/preload.js#L128-L152
	# and https://github.com/signalapp/Signal-Desktop/blob/v1.36.3/ts/Crypto.ts
	# the encryption was moved into the API function for convenience.
	async def put_stickers(
		self,
		manifest: StickerPack,
		stickers: List[StickerImage],
		cover: StickerImage
	):
		pack_key = secrets.token_bytes(32)
		aes_key, mac_key = self.derive_sticker_pack_keys(pack_key)
		iv = secrets.token_bytes(16)

		enc_manifest = encrypt_attachment(manifest.SerializeToString(), aes_key, mac_key, iv)
		# TODO do this in parallel
		enc_stickers = [encrypt_attachment(sticker.image, aes_key, mac_key, iv) for sticker in stickers + [cover]]

		# get manifest and sticker upload parameters
		async with self._http.get(
			f'{self.cdn_urls[0]}/v1/sticker/pack/form/{len(stickers)}',
			ssl=self.ssl,
			proxy=self.proxy_url,
		) as resp:
			print(await resp.text())
			a

		manifest_params = self.make_put_params(manifest, enc_manifest)

	@staticmethod
	def derive_sticker_pack_keys(pack_key: bytes) -> Tuple[bytes, bytes]:
		salt = b'\0' * 32
		info = b'Signal Sticker Pack'
		keys = HKDF().deriveSecrets(inputKeyMaterial=pack_key, salt=salt, info=info, outputLength=32 * 2)
		assert len(keys) == 32 * 2
		aes_key = keys[:32]
		mac_key = keys[32:64]
		return aes_key, mac_key

	@classmethod
	def from_config(cls, config: dict):
		return cls(
			url=config['serverUrl'],
			cdn_urls={
				0: config['cdnUrl0'],
				2: config['cdnUrl2'],
			},
			proxy_url=config.get('proxyUrl'),
			version=config['version'],
		)
