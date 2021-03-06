#!/usr/bin/env python3

import sys
import textwrap
from subprocess import call


def update_os():
    print("goSecure_Server_Script - Update OS\n")
    call("sudo yum update -y", shell=True)

def enable_ip_forward():
    print("goSecure_Server_Script - Enable IP Forward\n")
    with open("/etc/sysctl.conf") as fin:
        lines = fin.readlines()

    for i, line in enumerate(lines):
        if "net.ipv4.ip_forward" in line:
            lines[i] = "net.ipv4.ip_forward = 1\n"

    with open("/etc/sysctl.conf", "w") as fout:
        for line in lines:
            fout.write(line)

    call(["sudo", "sysctl", "-p"])


def configure_firewall():
    print("goSecure_Server_Script - Configure Firewall\n")
    iptables_rules = textwrap.dedent("""\
        # Firewall configuration written by system-config-firewall
        # Manual customization of this file is not recommended.
        *filter
        :INPUT DROP [0:0]
        :FORWARD DROP [0:0]
        :OUTPUT ACCEPT [0:0]
        -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
        # -A INPUT -p icmp -j ACCEPT
        -A INPUT -i lo -j ACCEPT
        -A INPUT -m state --state NEW -m tcp -p tcp --dport 22 -j ACCEPT
        -A INPUT -m udp -p udp --dport 500 -j ACCEPT
        -A INPUT -m udp -p udp --dport 4500 -j ACCEPT
        -A FORWARD -i eth0 -o eth1 -j ACCEPT
        -A FORWARD -i eth1 -o eth0 -j ACCEPT
        -A FORWARD -i ipsec0 -o eth0 -j ACCEPT
        -A FORWARD -i eth0 -o ipsec0 -j ACCEPT
        -A FORWARD -i ipsec0 -o eth1 -j ACCEPT
        -A FORWARD -i eth1 -o ipsec0 -j ACCEPT
        -A INPUT -j REJECT --reject-with icmp-host-prohibited
        -A FORWARD -j REJECT --reject-with icmp-host-prohibited
        COMMIT

        *nat
        :PREROUTING ACCEPT [0:0]
        :POSTROUTING ACCEPT [0:0]
        :OUTPUT ACCEPT [0:0]
        -A POSTROUTING -o eth0 -j MASQUERADE
        -A POSTROUTING -o eth1 -j MASQUERADE
        COMMIT\n""")

    iptables_file = open("/etc/sysconfig/iptables", "w")
    iptables_file.write(iptables_rules)
    iptables_file.close()
    call(["sudo", "service", "iptables", "restart"])


def install_strongswan():
    print("goSecure_Server_Script - Install strongSwan\n")
    install_strongswan_commands = textwrap.dedent("""\
        sudo yum groupinstall -y "Development Tools"
        sudo yum install -y unzip
        sudo yum install -y openssl-devel pam-devel
        wget -P /tmp https://download.strongswan.org/strongswan-5.5.0.tar.gz
        tar -xvzf /tmp/strongswan-5.5.0.tar.gz -C /tmp
        cd /tmp/strongswan-5.5.0/ && ./configure --prefix=/usr --sysconfdir=/etc --enable-gcm --enable-kernel-libipsec --enable-openssl --with-fips-mode=2 --disable-vici --disable-des --disable-ikev2 --disable-gmp
        make -C /tmp/strongswan-5.5.0/
        sudo make -C /tmp/strongswan-5.5.0/ install""")

    for command in install_strongswan_commands.splitlines():
        call(command, shell=True)

def configure_strongswan(client_id, client_psk):
    print("goSecure_Server_Script - Configure strongSwan\n")

    # https://www.blackhole-networks.com/IKE_Modes/ikev1-aggressive-weakness.html
    strongswan_conf = textwrap.dedent("""\
        charon {
                interfaces_use = eth0
                load_modular = yes
                i_dont_care_about_security_and_use_aggressive_mode_psk=yes
                plugins {
                        include strongswan.d/charon/*.conf
                }
        }

        include strongswan.d/*.conf""")

    strongswan_conf_file = open("/etc/strongswan.conf", "w")
    strongswan_conf_file.write(strongswan_conf)
    strongswan_conf_file.close()

    ipsec_conf = textwrap.dedent("""\
        config setup

        conn %default
                ikelifetime=60m
                keylife=20m
                rekeymargin=3m
                keyingtries=1
                keyexchange=ikev1
                left=%defaultroute
                leftsubnet=0.0.0.0/0
                leftid=@gosecure
                leftfirewall=yes
                right=%any
                rightsourceip=172.16.176.100/27
                auto=add
                authby=secret
                ike=aes256-sha384-ecp384!
                esp=aes256gcm128!
                aggressive=yes


        conn rw-client1
                rightid={0}

        # To add additional clients:
        # conn rw-client2 # increment the last number by 1 for each additional client
        #        rightid=<unique_id_of_client> # set a unique id for each client""".format(client_id))

    ipsec_conf_file = open("/etc/ipsec.conf", "w")
    ipsec_conf_file.write(ipsec_conf)
    ipsec_conf_file.close()


    ipsec_secrets = "{0} : PSK {1}".format(client_id, client_psk)

    ipsec_secrets_file = open("/etc/ipsec.secrets", "w")
    ipsec_secrets_file.write(ipsec_secrets)
    ipsec_secrets_file.close()


    call(["sudo", "service", "network", "restart"])

def start_strongswan():
    print("goSecure_Server_Script - Start strongSwan\n")
    call(["sudo", "ipsec", "start"])
    call('sudo echo "ipsec start" >> /etc/rc.d/rc.local', shell=True)

def main():
    cmdargs = str(sys.argv)

    if len(sys.argv) != 3:
        print(textwrap.dedent("""\
            Syntax is: sudo python gosecure_server_install.py <client1_id> "<client1_psk>"
            Example: sudo python gosecure_server_install.py client1.d2.local "mysupersecretpsk"\n"""))
        exit(1)

    client_id = str(sys.argv[1])
    client_psk = str(sys.argv[2])

    update_os()
    enable_ip_forward()
    configure_firewall()
    install_strongswan()
    configure_strongswan(client_id, client_psk)
    start_strongswan()
    print("goSecure_Server_Script - Completed")
    exit(0)

if __name__ == "__main__":
    main()
