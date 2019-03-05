import os
import sys
import shell
import daemon
import eventloop
import tcprelay
import udprelay
import asyncdns

import sys
import os
import logging
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))


shell.check_python()

# fix py2exe
if hasattr(sys, "frozen") and sys.frozen in ("windows_exe", "console_exe"):
    p = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(p)

#config = shell.get_config(True)
# print('~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~')
# print(config)

config = {'server': 'pynalysi.xyz',
          'server_port': 8080,
          'password': b'hello,world!',
          'method': 'aes-256-cfb',
          'port_password': None,
          'timeout': 300,
          'fast_open': False,
          'workers': 1,
          'pid-file': '/var/run/shadowsocks.pid',
          'log-file': '/var/log/shadowsocks.log',
          'verbose': False,
          'local_address': '192.168.3.161',
          'local_port': 1081,
          'one_time_auth': False,
          'prefer_ipv6': False,
          'daemon': 'start'}


# daemon.daemon_exec(config)
logging.info("starting local at %s:%d" % (config['local_address'], config['local_port']))
try:
    dns_resolver = asyncdns.DNSResolver()
    tcp_server = tcprelay.TCPRelay(config, dns_resolver, True)
    udp_server = udprelay.UDPRelay(config, dns_resolver, True)
    loop = eventloop.EventLoop()
    dns_resolver.add_to_loop(loop)
    tcp_server.add_to_loop(loop)
    udp_server.add_to_loop(loop)

    def handler(signum, _):
        logging.warn('received SIGQUIT, doing graceful shutting down..')
        tcp_server.close(next_tick=True)
        udp_server.close(next_tick=True)
    signal.signal(getattr(signal, 'SIGQUIT', signal.SIGTERM), handler)

    def int_handler(signum, _):
        sys.exit(1)
    signal.signal(signal.SIGINT, int_handler)

    daemon.set_user(config.get('user', None))
    loop.run()
except Exception as e:
    shell.print_exception(e)
    sys.exit(1)
