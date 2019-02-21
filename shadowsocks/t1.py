import os
import sys
import shell
import daemon


config = shell.get_config(False)
daemon.daemon_exec(config)




#print(config)


#data = {'server': '127.0.0.100', 'server_port': 8388, 'password': b'hello,world!', 'method': 'aes-256-cfb', 'port_password': None, 'timeout': 300, 'fast_open': False, 'workers': 1, 'pid-file': '/var/run/shadowsocks.pid', 'log-file': '/var/log/shadowsocks.log', 'verbose': False, 'local_address': '127.0.0.1', 'local_port': 1080, 'one_time_auth': False, 'prefer_ipv6': False, 'forbidden_ip': <common.IPNetwork object at 0x7fc386cedba8>}
