import json
import os
import subprocess
import random

import charms_openstack.charm
import charms_openstack.adapters as adapters

import charms.reactive as reactive
import charmhelpers.core.hookenv as hookenv
import charms_openstack.ip as os_ip

import charmhelpers.core as ch_core
import charmhelpers.contrib.network.ip as ch_ip
from charmhelpers.core.templating import render
from charms_openstack.charm.utils import (
    is_data_changed,
)
import charmhelpers.contrib.openstack.ha.utils as os_ha_utils

WSGATE_USER = "wsgate"
WSGATE_GROUP = "wsgate"
WSGATE_HOME = "/home/wsgate"
WSGATE_CFG_DIR = os.path.join(WSGATE_HOME, "snap/wsgate/common")
WSGATE_CFG = os.path.join(WSGATE_CFG_DIR, "wsgate.ini")
NGINX_DIR = "/etc/nginx"
NGINX_CFG = os.path.join(NGINX_DIR, "nginx.conf")
NGINX_SSL_DIR = os.path.join(NGINX_DIR, "ssl")


@adapters.adapter_property('ad-join')
def credentials(args):
    ad_join = reactive.endpoint_from_flag(
        'ad-join.available')
    if ad_join:
        return ad_join.credentials()
    return None


class ConfigAdapter(adapters.APIConfigurationAdapter):

    @property
    def apache_enabled(self):
        return False
 

class WSGateCharm(charms_openstack.charm.HAOpenStackCharm):
    """Charm class for the WSGate charm."""

    name = "wsgate"
    packages = ["nginx"]
    release = "train"
    release_pkg = "wsgate"
    configuration_class = ConfigAdapter

    required_relations = [
        'identity-credentials', 'ad-join']

    api_ports = {
        'wsgate': {
            os_ip.PUBLIC: 5115,
            os_ip.ADMIN: 5115,
            os_ip.INTERNAL: 5115,
        },
    }

    source_config_key = "source"
    python_version = 3
    systemd_file = "/etc/systemd/system/wsgate.service"

    services = [name, "nginx"]
    restart_map = {
        WSGATE_CFG: [name,],
        NGINX_CFG: ["nginx",],
    }
    ha_resources = ['vips', 'haproxy', 'dnsha']

    group = "wsgate"

    def __init__(self, **kw):
        super().__init__(**kw)

    def apache_enabled(self):
        return False

    def enable_memcache(self, release=None):
        return False

    def configure_wsgate_ca(self, ca_cert, ca_chain=None):
        ca_file = os.path.join(WSGATE_CFG_DIR, "keystone_ca.pem")
        if ca_cert:
            with open(ca_file, 'w') as fd:
                fd.write(ca_cert)
                if ca_cert.endswith('\n') is False:
                    fd.write('\n')
                if ca_chain:
                    fd.write(ca_chain)
            self.config["wsgate_ca_file"] = ca_file

    def configure_tls(self, certificates_interface=None):
        if certificates_interface is None:
            certificates_interface = reactive.endpoint_from_flag(
                'certificates.available')
        tls_objects = super(
            charms_openstack.charm.OpenStackAPICharm, self).configure_tls(
                certificates_interface=certificates_interface)
        with is_data_changed(
                'configure_ssl.ssl_objects', tls_objects) as changed:
            if tls_objects:
                for tls_object in tls_objects:
                    self.set_state('ssl.requested', True)
                    path = NGINX_SSL_DIR
                    self.configure_cert(
                        path,
                        tls_object['cert'],
                        tls_object['key'],
                        cn=tls_object['cn'])

                    if 'chain' in tls_object:
                        self.configure_wsgate_ca(
                            tls_object["ca"], tls_object['chain'])
                    else:
                        self.configure_wsgate_ca(tls_object["ca"])
                    self.configure_nginx(path, tls_object['cn'])
                    self.service_reload('nginx')

                self.remove_state('ssl.requested')
                self.set_state('ssl.enabled', True)
            else:
                self.set_state('ssl.enabled', False)

    def configure_nginx(self, path, cn=None):
        cert_name = "cert"
        key_name = "key"
        if cn is not None:
            cert_name = "cert_{}".format(cn)
            key_name = "key_{}".format(cn)
        cert_path = os.path.join(path, cert_name)
        if os.path.isfile(cert_path):
            self.config["ssl_certificate"] = cert_path
        key_path = os.path.join(path, key_name)
        if os.path.isfile(key_path):
            self.config["ssl_certificate_key"] = key_path
    
    def fix_permissions(self):
        ch_core.host.chownr(
            WSGATE_HOME,
            owner=WSGATE_USER,
            group=WSGATE_GROUP,
            chowntopdir=True)
        os.chown(NGINX_CFG, 0, 0)

    def install(self):
        super(charms_openstack.charm.OpenStackAPICharm, self).install()
        channel = self.config.get("channel", "stable")

        subprocess.check_call(
            ["sudo", "snap", "install",
             "--channel=%s" % channel,
             "wsgate"])

        if not ch_core.host.group_exists(WSGATE_GROUP):
            ch_core.host.add_group(
                WSGATE_GROUP, system_group=True)
        # Create the user
        if not ch_core.host.user_exists(WSGATE_USER):
            ch_core.host.adduser(
                WSGATE_USER, shell="/usr/sbin/nologin",
                system_user=True, primary_group=WSGATE_GROUP,
                home_dir=WSGATE_HOME)

        # Create the directory
        if not os.path.exists(WSGATE_HOME):
            ch_core.host.mkdir(
                WSGATE_HOME,
                owner=WSGATE_USER,
                group=WSGATE_GROUP,
                perms=0o755)
        
        if not os.path.exists(WSGATE_CFG_DIR):
            ch_core.host.mkdir(
                WSGATE_CFG_DIR,
                owner=WSGATE_USER,
                group=WSGATE_GROUP,
                perms=0o755)

        ch_core.host.chownr(
            WSGATE_HOME,
            owner=WSGATE_USER,
            group=WSGATE_GROUP,
            chowntopdir=True)

        # Systemd File
        render(
            source="wsgate.service",
            target=self.systemd_file,
            context={
                "username": WSGATE_USER,
                "cfg_file": WSGATE_CFG,
            },
            owner='root',
            perms=0o644,
        )
        cmd = ["/usr/bin/systemctl", "daemon-reload"]
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)

        cmd = ["/usr/bin/systemctl", "enable", self.name]
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    
    @property
    def ad_users(self):
        cfg_groups = self.config["ad-groups"]
        groups = []
        if not cfg_groups:
            groups.append("Users")
        else:
            for group in cfg_groups.split(','):
                groups.append(group.strip())

        user = self.config["ad-user"] or self.name
        users = {
            user: groups
        }
        return users

    def _get_allowed_user(self):
        creds = credentials(None)
        if creds and len(creds):
            return {
                "username": creds[0]["username"],
                "full_username": creds[0]["full_username"],
                "netbios_domain": creds[0]["netbios_name"],
                "domain": creds[0]["domain"]
            }
        return None

    def set_wsgate_info(self, wsgate):
        is_ready = reactive.flags.is_flag_set('config.complete')
        has_ssl = reactive.flags.get_state('ssl.enabled')
        ha_available = reactive.flags.is_flag_set('ha.available')
        proto = "https" if has_ssl is True else "http"
        local_ip = ch_ip.get_relation_ip("internal")
        addr = self.config["vip"] if ha_available else local_ip
        allowed_user = self._get_allowed_user()

        if not allowed_user:
            # We don't have AD credentials yet. Defer for later
            return

        relation_data = {
            "enabled": is_ready,
            "html5_proxy_base_url": "%(proto)s://%(address)s:%(port)s/" % {
                "proto": proto,
                "address": addr,
                "port": self.api_ports["wsgate"][os_ip.PUBLIC],
            },
            "allow_user": allowed_user,
        }
        for unit in wsgate.all_joined_units:
            wsgate.set_wsgate_info(
                unit.relation.relation_id,
                relation_data)

