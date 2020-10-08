import binascii
import hashlib
import secrets
import cryptography.hazmat.primitives.ciphers
import cryptography.hazmat.primitives.ciphers.algorithms
import cryptography.hazmat.primitives.padding
import cryptography.hazmat.primitives.hashes
import cryptography.hazmat.primitives.hmac
import cryptography.hazmat.primitives as primitives
import axolotl_curve25519 as curve
from os import PathLike
from typing import Tuple

# https://github.com/signalapp/Signal-Desktop/blob/v1.36.3/ts/Crypto.ts#L152
# https://github.com/signalapp/Signal-Desktop/blob/v1.36.3/ts/textsecure/Crypto.ts#L111

def encrypt_attachment(plaintext: bytes, aes_key: bytes, mac_key: bytes, iv: bytes) -> Tuple[bytes, bytes]:
	if len(aes_key) != 32:
		raise ValueError('invalid AES key length')
	if len(mac_key) != 32:
		raise ValueError('invalid MAC key length')
	if len(iv) != 16:
		raise ValueError('invalid IV length')

	ct = encrypt_aes256_cbc_pkcs_padding(aes_key, iv, plaintext)
	iv_and_ct = iv + ct

	mac = hmac_sha256(mac_key, iv_and_ct)
	final = iv_and_ct + mac
	return final, hashlib.sha256(final).digest()

#def encrypt_file(public_key: bytes, unique_id: bytes, plaintext: bytes):
#	ephemeral_private_key = curve.generatePrivateKey(secrets.token_bytes(32))
#	ephemeral_public_key = curve.generatePublicKey(ephemeral_private_key)
#	print(*map(len, (public_key, ephemeral_private_key)))
#	agreement = curve.calculateAgreement(public_key, ephemeral_private_key)
#	key = hmac_sha256(agreement, unique_id)
#	prefix = ephemeral_public_key[1:]
#	return prefix + encrypt_symmetric(key, plaintext)

IV_LENGTH = 16
MAC_LENGTH = 16
NONCE_LENGTH = 16

def encrypt_symmetric(key: bytes, plaintext: bytes) -> bytes:
	iv = b'\0' * IV_LENGTH
	nonce = secrets.token_bytes(NONCE_LENGTH)
	cipher_key = hmac_sha256(key, nonce)
	mac_key = hmac_sha256(key, cipher_key)
	ct = encrypt_aes256_cbc_pkcs_padding(cipher_key, iv, plaintext)
	mac = hmac_sha256(mac_key, ct)[:MAC_LENGTH]
	return nonce + ct + mac

def hmac_sha256(key: bytes, plaintext: bytes) -> bytes:
	h = primitives.hmac.HMAC(key, primitives.hashes.SHA256())
	h.update(plaintext)
	return h.finalize()

def encrypt_aes256_cbc_pkcs_padding(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
	cipher = primitives.ciphers.Cipher(primitives.ciphers.algorithms.AES(key), primitives.ciphers.modes.CBC(iv))
	ctor = cipher.encryptor()
	padder = primitives.padding.PKCS7(128).padder()
	padder.update(plaintext)
	return ctor.update(padder.finalize()) + ctor.finalize()
