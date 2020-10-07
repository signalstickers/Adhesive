import binascii
import cryptography.hazmat.primitives as primitives
from axolotl.util.keyhelper import KeyHelper
from axolotl.ecc.curve import Curve
from axolotl.ecc.djbec import DjbECPrivateKey
from os import PathLike

# https://github.com/signalapp/Signal-Desktop/blob/v1.36.3/ts/Crypto.ts#L152

def encrypt_file(key: bytes, unique_id: bytes, plaintext: bytes):
	ephemeral_key_pair = KeyHelper.generateIdentityKeyPair()
	agreement = Curve.calculateAgreement(key, ephemeral_key_pair.privateKey)
	prefix = ephemeral_key_pair.publicKey[1:]
	return prefix + encrypt_symmetric(key, plaintext)

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
