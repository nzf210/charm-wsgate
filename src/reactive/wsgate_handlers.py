import charms.reactive as reactive
import charmhelpers.core.hookenv as hookenv

import charms_openstack.bus
import charms_openstack.charm as charm

charms_openstack.bus.discover()


charm.use_defaults(
    'charm.installed',
    'config.changed',
    'update-status',
    'upgrade-charm',
    'certificates.available',
    'cluster.available')


@reactive.when('identity-credentials.available')
@reactive.when('ad-join.available')
def render(*args):
    hookenv.log("about to call the render_configs with {}".format(args))
    with charm.provide_charm_instance() as wsgate_charm:
        wsgate_charm.render_with_interfaces(
            charm.optional_interfaces(args))
        wsgate_charm.fix_permissions()
        wsgate_charm.configure_tls()
        wsgate_charm.assess_status()
    reactive.set_state('config.complete')


@reactive.when('identity-credentials.connected')
def request_keystone_credentials(keystone):
    with charm.provide_charm_instance() as wsgate_charm:
        keystone.request_credentials(
            wsgate_charm.name, region=wsgate_charm.region)
        wsgate_charm.assess_status()


@reactive.when('ha.connected')
@reactive.when_not('ha.available')
def cluster_connected(hacluster):
    with charm.provide_charm_instance() as wsgate_charm:
        wsgate_charm.configure_ha_resources(hacluster)
        wsgate_charm.assess_status()


@reactive.when('wsgate.available')
@reactive.when_any(
    'config.complete',
    'ssl.enabled')
def wsgate_connected(wsgate):
    with charm.provide_charm_instance() as wsgate_charm:
        wsgate_charm.set_wsgate_info(wsgate)


@reactive.when('ad-join.connected')
def request_credentials(creds):
    with charm.provide_charm_instance() as wsgate_charm:
        creds.request_credentials(wsgate_charm.ad_users)
        wsgate_charm.assess_status()