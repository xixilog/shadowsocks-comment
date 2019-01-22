
# -*- coding: utf-8 -*-



import os
import sys
import hashlib
import logging

import common
from crypto import rc4_md5, openssl, sodium, table


method_supported = {}
method_supported.update(rc4_md5.ciphers)
method_supported.update(openssl.ciphers)
method_supported.update(sodium.ciphers)
method_supported.update(table.ciphers)


def random_string(length):
    return os.urandom(length)


cached_keys = {}


def try_cipher(key, method=None):
    Encryptor(key, method)


def EVP_BytesToKey(password, key_len, iv_len):
    # 生成key 和 iv，实际是通过m[i-1] + password不断经过md5生成水印
    # 其中m[i-1]为上一次上一次生成的md5，开始第一次直接使用password
    # 当生成的所有md5总长度大于 key_len + iv_len时候，取data[:key_len]
    # 为key,取data[key_len:key_len+iv_len为iv
    # equivalent to OpenSSL's EVP_BytesToKey() with count 1
    # so that we make the same key and iv as nodejs version
    cached_key = '%s-%d-%d' % (password, key_len, iv_len)
    r = cached_keys.get(cached_key, None)
    if r:
        return r
    m = []
    i = 0
    while len(b''.join(m)) < (key_len + iv_len):
        md5 = hashlib.md5()
        data = password
        if i > 0:
            data = m[i - 1] + password
        md5.update(data)
        m.append(md5.digest())
        i += 1
    ms = b''.join(m)
    key = ms[:key_len]
    iv = ms[key_len:key_len + iv_len]
    cached_keys[cached_key] = (key, iv)
    return key, iv


# 既能加密也能解密，第一次加密的时候，会在数据包头放入加密的iv向量cipher_iv
# 第一次解密的时候会从包头得到解密的iv向量decipher_iv(就是前者对端放入的加密向量)
# 通过key(由密码通过多次md5生成)+iv加密与解密，密码是预共享的，而iv在第一次传输
# 的时候包含在数据头部，同时两端都知道iv向量的长度，因此两端都知道对方的key与iv
# 参考 http://www.cnblogs.com/UnGeek/p/5831883.html
class Encryptor(object):
    def __init__(self, password, method):
        self.password = password
        # 与密码关联生成的
        self.key = None
        self.method = method
        # 用于标示是否已经发送iv向量
        self.iv_sent = False
        self.cipher_iv = b''
        self.decipher = None
        # 解密向量对应对端的加密向量，反之加密向量一样，可以看到encrypt和decrypt函数
        # 在发送第一个数据包的时候，encrypt首先要在数据头部加入cipher_iv，在收到第一个
        # 数据包的时候，decrypt要先取出decipher_iv
        self.decipher_iv = None
        method = method.lower()
        self._method_info = self.get_method_info(method)
        if self._method_info:
            self.cipher = self.get_cipher(password, method, 1,
                                          random_string(self._method_info[1]))
        else:
            logging.error('method %s not supported' % method)
            sys.exit(1)

    def get_method_info(self, method):
        method = method.lower()
        m = method_supported.get(method)
        return m

    def iv_len(self):
        return len(self.cipher_iv)

    def get_cipher(self, password, method, op, iv):
        # iv 是随机值 os.urandom
        password = common.to_bytes(password)
        m = self._method_info
        if m[0] > 0:
            key, iv_ = EVP_BytesToKey(password, m[0], m[1])
        else:
            # key_length == 0 indicates we should use the key directly
            key, iv = password, b''
        self.key = key
        # 长度不够也没问题
        iv = iv[:m[1]]
        if op == 1:
            # ope 1 表示iv用于加密
            # this iv is for cipher not decipher
            # 什么鬼，直接赋值不就好
            self.cipher_iv = iv[:m[1]]
        return m[2](method, key, iv, op)

    def encrypt(self, buf):
        if len(buf) == 0:
            return buf
        # 发送第一个包的时候要发送iv向量给对端
        if self.iv_sent:
            return self.cipher.update(buf)
        else:
            self.iv_sent = True
            return self.cipher_iv + self.cipher.update(buf)

    def decrypt(self, buf):
        if len(buf) == 0:
            return buf
        if self.decipher is None:
            # 收到第一个包有对端加密向量
            decipher_iv_len = self._method_info[1]
            decipher_iv = buf[:decipher_iv_len]
            self.decipher_iv = decipher_iv
            self.decipher = self.get_cipher(self.password, self.method, 0,
                                            iv=decipher_iv)
            buf = buf[decipher_iv_len:]
            if len(buf) == 0:
                return buf
        return self.decipher.update(buf)


def gen_key_iv(password, method):
    method = method.lower()
    (key_len, iv_len, m) = method_supported[method]
    key = None
    if key_len > 0:
        key, _ = EVP_BytesToKey(password, key_len, iv_len)
    else:
        key = password
    # 随机向量
    iv = random_string(iv_len)
    return key, iv, m


def encrypt_all_m(key, iv, m, method, data):
    result = []
    # 头部是向量
    result.append(iv)
    cipher = m(method, key, iv, 1)
    result.append(cipher.update(data))
    return b''.join(result)


def dencrypt_all(password, method, data):
    # 给udp解密用的
    result = []
    method = method.lower()
    (key_len, iv_len, m) = method_supported[method]
    key = None
    if key_len > 0:
        key, _ = EVP_BytesToKey(password, key_len, iv_len)
    else:
        key = password
    # 数据中包含有iv
    iv = data[:iv_len]
    data = data[iv_len:]
    cipher = m(method, key, iv, 0)
    result.append(cipher.update(data))
    return b''.join(result), key, iv


def encrypt_all(password, method, op, data):
    result = []
    method = method.lower()
    (key_len, iv_len, m) = method_supported[method]
    key = None
    if key_len > 0:
        key, _ = EVP_BytesToKey(password, key_len, iv_len)
    else:
        key = password
    if op:
        # 加密的数据头放入向量
        iv = random_string(iv_len)
        result.append(iv)
    else:
        # 解密的时候，数据头部是向量，后面是数据
        iv = data[:iv_len]
        data = data[iv_len:]
    cipher = m(method, key, iv, op)
    result.append(cipher.update(data))
    return b''.join(result)


CIPHERS_TO_TEST = [
    'aes-128-cfb',
    'aes-256-cfb',
    'rc4-md5',
    'salsa20',
    'chacha20',
    'table',
]


def test_encryptor():
    from os import urandom
    plain = urandom(10240)
    for method in CIPHERS_TO_TEST:
        logging.warn(method)
        encryptor = Encryptor(b'key', method)
        decryptor = Encryptor(b'key', method)
        cipher = encryptor.encrypt(plain)
        plain2 = decryptor.decrypt(cipher)
        assert plain == plain2


def test_encrypt_all():
    from os import urandom
    plain = urandom(10240)
    for method in CIPHERS_TO_TEST:
        logging.warn(method)
        cipher = encrypt_all(b'key', method, 1, plain)
        plain2 = encrypt_all(b'key', method, 0, cipher)
        assert plain == plain2


def test_encrypt_all_m():
    from os import urandom
    plain = urandom(10240)
    for method in CIPHERS_TO_TEST:
        logging.warn(method)
        key, iv, m = gen_key_iv(b'key', method)
        cipher = encrypt_all_m(key, iv, m, method, plain)
        plain2, key, iv = dencrypt_all(b'key', method, cipher)
        assert plain == plain2


if __name__ == '__main__':
    test_encrypt_all()
    test_encryptor()
    test_encrypt_all_m()
