import os
import sys
import asyncdns
import manager
import udprelay
import tcprelay
import eventloop
import daemon
import shell
import logging
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))


def main():
    shell.check_python()

    config = shell.get_config(False)

    daemon.daemon_exec(config)

    if config['port_password']:
        if config['password']:
            logging.warn('warning: port_password should not be used with '
                         'server_port and password. server_port and password '
                         'will be ignored')
    else:
        config['port_password'] = {}
        server_port = config['server_port']
        if type(server_port) == list:
            for a_server_port in server_port:
                config['port_password'][a_server_port] = config['password']
        else:
            config['port_password'][str(server_port)] = config['password']

    if config.get('manager_address', 0):
        logging.info('entering manager mode')
        manager.run(config)
        return

    tcp_servers = []
    udp_servers = []

    if 'dns_server' in config:  # allow override settings in resolv.conf
        dns_resolver = asyncdns.DNSResolver(config['dns_server'],
                                            config['prefer_ipv6'])
    else:
        dns_resolver = asyncdns.DNSResolver(prefer_ipv6=config['prefer_ipv6'])

    port_password = config['port_password']
    del config['port_password']
    # 不同端口监听
    for port, password in port_password.items():
        a_config = config.copy()
        a_config['server_port'] = int(port)
        a_config['password'] = password
        logging.info("starting server at %s:%d" %
                     (a_config['server'], int(port)))
        # tcp 与 udp 对应
        tcp_servers.append(tcprelay.TCPRelay(a_config, dns_resolver, False))
        udp_servers.append(udprelay.UDPRelay(a_config, dns_resolver, False))

    def run_server():
        def child_handler(signum, _):
            logging.warn('received SIGQUIT, doing graceful shutting down..')
            list(map(lambda s: s.close(next_tick=True),
                     tcp_servers + udp_servers))
        # 收到SIGQUIT信号，关闭所有监听端口
        signal.signal(getattr(signal, 'SIGQUIT', signal.SIGTERM),
                      child_handler)

        def int_handler(signum, _):
            sys.exit(1)
        # 收到SIGINT直接退出
        signal.signal(signal.SIGINT, int_handler)

        try:
            loop = eventloop.EventLoop()
            # 与loop关联
            dns_resolver.add_to_loop(loop)
            list(map(lambda s: s.add_to_loop(loop), tcp_servers + udp_servers))

            daemon.set_user(config.get('user', None))
            loop.run()
        except Exception as e:
            shell.print_exception(e)
            sys.exit(1)

    # 多进程模式
    if int(config['workers']) > 1:
        if os.name == 'posix':
            children = []
            is_child = False
            for i in range(0, int(config['workers'])):
                r = os.fork()
                # 子进程跑
                if r == 0:
                    logging.info('worker started')
                    is_child = True
                    run_server()
                    break
                else:
                    children.append(r)  # 添加到父进程
            if not is_child:
                # 父进程跑下来
                def handler(signum, _):
                    # 主进程收到中断，杀死所有子进程
                    for pid in children:
                        try:
                            os.kill(pid, signum)
                            os.waitpid(pid, 0)
                        except OSError:  # child may already exited
                            pass
                    sys.exit()
                signal.signal(signal.SIGTERM, handler)
                signal.signal(signal.SIGQUIT, handler)
                signal.signal(signal.SIGINT, handler)

                # master
                for a_tcp_server in tcp_servers:
                    a_tcp_server.close()
                for a_udp_server in udp_servers:
                    a_udp_server.close()
                dns_resolver.close()
                # 等待所有子进程结束
                for child in children:
                    os.waitpid(child, 0)
        else:
            logging.warn('worker is only available on Unix/Linux')
            run_server()
    else:
        run_server()  # 单进程跑


if __name__ == '__main__':
    main()
