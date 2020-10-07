from dataclasses import dataclass
from typing import List, NewType

from .stickers_pb2 import StickerPack

WebpImage = NewType('WebpImage', bytes)

@dataclass
class StickerImage:
	image: WebpImage
	emoji: str

def create_pack(*, title: str, author: str, stickers: List[StickerImage], cover: StickerImage) -> StickerPack:
	manifest = StickerPack()
	manifest.title = title
	manifest.author = author
	for id, sticker in enumerate(stickers):
		sticker_meta = StickerPack.Sticker()
		manifest.stickers.append(sticker_meta)
		sticker_meta.id = id
		sticker_meta.emoji = sticker.emoji

	manifest.cover.emoji = ''
	manifest.cover.id = len(manifest.stickers or '☭') - 1
	manifest.stickers.append(manifest.cover)

	return manifest
