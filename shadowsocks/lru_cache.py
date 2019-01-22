
# -*- coding: utf-8 -*-





import collections
import logging
import time


# this LRUCache is optimized for concurrency, not QPS
# n: concurrency, keys stored in the cache
# m: visits not timed out, proportional to QPS * timeout
# get & set is O(1), not O(n). thus we can support very large n
# TODO: if timeout or QPS is too large, then this cache is not very efficient,
#       as sweep() causes long pause


class LRUCache(collections.MutableMapping):
    """This class is not thread safe"""

    def __init__(self, timeout=60, close_callback=None, *args, **kwargs):
        self.timeout = timeout
        self.close_callback = close_callback
        self._store = {}
        # 某个时间点访问了哪些key，以time.time()作为索引
        self._time_to_keys = collections.defaultdict(list)
        # 某个key最后访问的时间
        self._keys_to_last_time = {}
        # 访问的时间点队列，每次访问都往此队列添加时间点，相当于访问的历史时间点
        self._last_visits = collections.deque()
        self._closed_values = set()
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key):
        # O(1)
        t = time.time()
        self._keys_to_last_time[key] = t
        self._time_to_keys[t].append(key)
        self._last_visits.append(t)
        return self._store[key]

    def __setitem__(self, key, value):
        # O(1)
        t = time.time()
        self._keys_to_last_time[key] = t
        self._store[key] = value
        self._time_to_keys[t].append(key)
        self._last_visits.append(t)

    def __delitem__(self, key):
        # O(1)
        del self._store[key]
        del self._keys_to_last_time[key]

    def __iter__(self):
        return iter(self._store)

    def __len__(self):
        return len(self._store)

    def sweep(self):
        # O(m)
        now = time.time()
        c = 0
        while len(self._last_visits) > 0:
            least = self._last_visits[0]
            # 最早访问的在队列头
            if now - least <= self.timeout:
                break
            # 有通知回调，需要调用此回调通知用户
            if self.close_callback is not None:
                for key in self._time_to_keys[least]:
                    if key in self._store:
                        # 确认该时间点访问的key是否已经超时
                        if now - self._keys_to_last_time[key] > self.timeout:
                            value = self._store[key]
                            if value not in self._closed_values:
                                self.close_callback(value)
                                # 防止重复回调通知
                                self._closed_values.add(value)
            self._last_visits.popleft()
            # 清楚节点
            for key in self._time_to_keys[least]:
                if key in self._store:
                    if now - self._keys_to_last_time[key] > self.timeout:
                        del self._store[key]
                        del self._keys_to_last_time[key]
                        c += 1
            del self._time_to_keys[least]
        if c:
            self._closed_values.clear()
            logging.debug('%d keys swept' % c)


def test():
    c = LRUCache(timeout=0.3)

    c['a'] = 1
    assert c['a'] == 1

    time.sleep(0.5)
    c.sweep()
    assert 'a' not in c

    c['a'] = 2
    c['b'] = 3
    time.sleep(0.2)
    c.sweep()
    assert c['a'] == 2
    assert c['b'] == 3

    time.sleep(0.2)
    c.sweep()
    c['b']
    time.sleep(0.2)
    c.sweep()
    assert 'a' not in c
    assert c['b'] == 3

    time.sleep(0.5)
    c.sweep()
    assert 'a' not in c
    assert 'b' not in c

    global close_cb_called
    close_cb_called = False

    def close_cb(t):
        global close_cb_called
        assert not close_cb_called
        close_cb_called = True

    c = LRUCache(timeout=0.1, close_callback=close_cb)
    c['s'] = 1
    c['s']
    time.sleep(0.1)
    c['s']
    time.sleep(0.3)
    c.sweep()

if __name__ == '__main__':
    test()
