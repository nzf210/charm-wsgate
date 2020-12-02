# Overview

This charm provides [FreeRDP WebConnect](https://github.com/FreeRDP/FreeRDP-WebConnect), which can be integrated in a Hyper-V based [Charmed OpenStack](https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/) deployment. FreeRDP WebConnect is the equivalent of [NoVNC](https://novnc.com/info.html) for [LibVirt](https://libvirt.org/) based systems.

It can be used as a stand-alone service as well, which allows you to access any RDP enabled Windows machine, through a HTML5 compliant web browser.

## Building

Set environment variables

```bash
export CHARM_LAYERS_DIR=$HOME/charms/layers
export CHARM_BASE=$HOME/charms
export CHARM_INTERFACES_DIR=$HOME/charms/interfaces
```

Ensure those folders exist:

```bash
mkdir -p $CHARM_LAYERS_DIR
mkdir -p $CHARM_BASE
mkdir -p $CHARM_INTERFACES_DIR
```

Fetch needed interfaces:

```bash
git clone https://github.com/cloudbase/charm-interface-ad-join.git $CHARM_INTERFACES_DIR/interface-ad-join
git clone https://github.com/cloudbase/charm-interface-wsgate.git $CHARM_INTERFACES_DIR/interface-wsgate
```

Build the charm:

```bash
git clone https://github.com/cloudbase/charm-wsgate.git
cd charm-wsgate/src
charm build
```

## Usage

Partial deployment only:

```bash
# Deploy on a new machine. We recommend you use an LXD container if possible.
juju deploy $CHARM_BASE/build/builds/wsgate
```

If you wish to integrate with an existing Hyper-V based OpenStack, you must also have Active Directory deployed. FreeRDP WebConnect will use AD credentials to authenticate against Windows compute hosts.

```bash
juju add-relation wsgate active-directory
juju add-relation wsgate keystone
juju add-relation wsgate active-directory
```

If you require TLS, add a relation to vault:

```bash
juju add-relation wsgate vault
```

This charm also supports HA.

```bash
juju add-unit -n 2 wsgate
juju deploy cs:~openstack-charmers-next/hacluster hacluster-wsgate

juju config wsgate vip=<your VIP goes here>
juju add-relation wsgate hacluster-wsgate
```
