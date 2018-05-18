Cinderlib CSI driver
====================

.. image:: https://img.shields.io/pypi/v/cinderlib_csi.svg
   :target: https://pypi.python.org/pypi/cinderlib_csi

.. image:: https://img.shields.io/pypi/pyversions/cinderlib_csi.svg
   :target: https://pypi.python.org/pypi/cinderlib_csi

.. image:: https://pyup.io/repos/github/akrog/cinderlib_csi/shield.svg
     :target: https://pyup.io/repos/github/akrog/cinderlib_csi/
     :alt: Updates

.. image:: https://img.shields.io/:license-apache-blue.svg
   :target: http://www.apache.org/licenses/LICENSE-2.0


CSI Python driver that leverages all Cinder drivers to provide block volumes
without needing to run any additional service, such as RabbitMQ, MariaDB,
Cinder-API, Cinder-Scheduler, or Cinder-Volume.

Current code is is a **Proof of Concept** only compatible with Cinder
OSP-12/Pike release.

* Free software: Apache Software License 2.0
* Documentation: Pending


Features
--------

This CSI driver is up to date with latest CSI specs including the `new
snapshots feature
<https://github.com/container-storage-interface/spec/pull/224>`_ recently
introduced.

Currently supported features are:

- Create block volume
- Creating snapshots
- Creating a block volume from a snapshot
- Delete block volume
- Deleting snapshots
- Listing volumes with pagination
- Listing snapshots with pagination
- Attaching volumes
- Detaching volumes
- Reporting storage capacity
- Probing the node
- Retrieving the plugin info


Runtime Dependencies
--------------------

This driver requires that Cinder v11.0 (OSP-12/Pike) is already installed in
the system, how this is accomplished is left to the installer, as there are
multiple ways this can be accomplished:

- From OSP repositories
- From RDO repositories
- From github
- From other repositories

Any other basic requirement is already handled by `cinderlib-csi` when
installing from PyPi.

Besides the basic dependencies there are also some drivers that have additional
requirements that must be met for proper operation of the driver and/or
attachment/detachment operations, just like in Cinder.

Some of these Python dependencies for the Controller servicer are:

- DRBD: dbus and drbdmanage
- HPE 3PAR: python-3parclient
- Kaminario: krest
- Pure: purestorage
- Dell EMC VMAX, IBM DS8K: pyOpenSSL
- HPE Lefthad: python-lefthandclient
- Fujitsu Eternus DX: pywbem
- IBM XIV: pyxcli
- RBD: rados and rbd
- Dell EMC VNX: storops
- Violin: vmemclient
- INFINIDAT: infinisdk, capacity, infy.dtypes.wwn, infi.dtypes.iqn

Other backends may also require additional packages, for example LVM on
CentOS/RHEL requires the `targetcli` package, so please check with your
hardware vendor.

Besides the Controller requirements there are usually requirements for the
Node servicer needed to handle the attaching and detaching of volumes to the
node based on the connection used to access the storage.  For example:

- iSCSI: iscsi-initiator-tools and device-mapper-multipath
- RBD/Ceph: ceph-common package


Installation
------------

First we need to install the Cinder Python package, for example to install from
RDO on CentOS:

.. code-block:: shell

    $ sudo yum install -y centos-release-openstack-pike
    $ sudo yum install -y openstack-cinder python-pip


Then we just need to install the `cinderlib-csi` package:

.. code-block:: shell

    $ sudo pip install cinderlib-csi

Now we should install any additional package required by our backend.

For iSCSI backends we'll want to install:

.. code-block:: shell

    $ sudo yum install iscsi-initiator-utils
    $ sudo yum install device-mapper-multipath
    $ sudo mpathconf --enable --with_multipathd y --user_friendly_names n --find_multipaths y

For RBD we'll also need a specific package:

.. code-block:: shell

    $ sudo yum install ceph-common


Configuration
-------------

The CSI driver is configured via environmental variables, any value that
doesn't have a default is a required value.

+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Name                       | Role       | Description                                                   | Default                                                                                                  | Example                                                                                                                                                                                                                                 |
+============================+============+===============================================================+==========================================================================================================+=========================================================================================================================================================================================================================================+
| `CSI_ENDPOINT`             | all        | IP and port to bind the service                               | [::]:50051                                                                                               | 192.168.1.22:50050                                                                                                                                                                                                                      |
+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| `CSI_MODE`                 | controller | Role the service should perform: controller, node, all        | all                                                                                                      | controller                                                                                                                                                                                                                              |
+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| `X_CSI_STORAGE_NW_IP`      | node       | IP address in the Node used to connect to the storage         | IP resolved from Node's fqdn                                                                             | 192.168.1.22                                                                                                                                                                                                                            |
+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| `X_CSI_NODE_ID`            | node       | ID used by this node to identify itself to the controller     | Node's fqdn                                                                                              | csi_test_node                                                                                                                                                                                                                           |
+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| `X_CSI_PERSISTENCE_CONFIG` | all        | Configuration of the `cinderlib` metadata persistence plugin. | {'storage': 'db', 'connection': 'sqlite:///db.sqlite'}                                                   | {'storage': 'db', 'connection': 'mysql+pymysql://root:stackdb@192.168.1.1/cinder?charset=utf8'}                                                                                                                                         |
+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| `X_CSI_CINDERLIB_CONFIG`   | controller | Global `cinderlib` configuration                              | {'project_id': 'com.redhat.cinderlib-csi', 'user_id': 'com.redhat.cinderlib-csi', 'root_helper': 'sudo'} | {"project_id":"com.redhat.cinderlib-csi","user_id":"com.redhat.cinderlib-csi","root_helper":"sudo"}                                                                                                                                     |
+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| `X_CSI_BACKEND_CONFIG`     | controller | Driver configuration                                          |                                                                                                          | {"volume_backend_name": "rbd", "volume_driver": "cinder.volume.drivers.rbd.RBDDriver", "rbd_user": "cinder", "rbd_pool": "volumes", "rbd_ceph_conf": "/etc/ceph/ceph.conf", "rbd_keyring_conf": "/etc/ceph/ceph.client.cinder.keyring"} |
+----------------------------+------------+---------------------------------------------------------------+----------------------------------------------------------------------------------------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

The only role that has been tested at the moment is the default one, where
Controller and Node servicer are executed in the same service (`CSI_MODE=all`),
and other modes are expected to have issues at the moment.


Staring the plugin
------------------

Once we have installed `cinderlib-csi` and required dependencies (for the
backend and for the connection type) we just have to run the `cinderlib-csi`
service with a user that can do passwordless sudo.

.. code-block:: shell

    $ cinderlib-csi


Testing the plugin
------------------

There are several examples of running the CSI cinderlib driver in the
`examples` directory both for a baremetal deployment and a containerized
version of the driver.

In all cases we have to run the plugin first before we can test it, and for
that we have to check the configuration provided as a test before starting the
plugin.  By default all examples run the service on port 50051.


Baremetal
~~~~~~~~~

For example to test with the LVM driver on our development environment we can
just run the following commands from the root of the `cinderlib-csi` project:

.. code-block:: shell

    $ cd tmp
    $ sudo dd if=/dev/zero of=cinder-volumes bs=1048576 seek=22527 count=1
    $ sudo lodevice=`losetup --show -f ./cinder-volumes`
    $ sudo pvcreate $lodevice
    $ sudo vgcreate cinder-volumes $lodevice
    $ sudo vgscan --cache
    $ cd ../examples/baremetal
    $ ./run.sh lvm
    py27 develop-inst-nodeps: /home/geguileo/code/reuse-cinder-drivers/cinderlib-csi
    py27 installed: ...
    ___ summary ___
      py27: skipped tests
      congratulations :)
    Starting cinderlib CSI v0.0.1 (cinderlib: 0.1.0, cinder: 11.1.1.dev41)
    Running backend LVMVolumeDriver v3.0.0
    Now serving on [::]:50051...


There is also an example of testing a Ceph cluster using a user called "cinder"
and the "volumes" pool.  For the Ceph/RBD backend, due to a limitation in
Cinder, we need to have both the credentials and the configuration in
`/etc/ceph` for it to work.

.. code-block:: shell

    $ cd examples/baremetal
    $ ./run.sh rbd
    Starting cinderlib CSI v0.0.1 (cinderlib: 0.1.0, cinder: 11.1.0)
    Running backend RBDDriver v1.2.0
    Now serving on [::]:50051...


There is also an XtremIO example that only requires the iSCSI connection
packages.


Containerized
~~~~~~~~~~~~~

There is a sample `Dockerfile` included in the project that has been used to
create the `akrog/cinderlib-csi` container available in the docker hub.

There are two bash scripts, one for each example, that will run the CSI driver
on a container, be aware that the container needs to run as privileged to mount
the volumes.

For the RBD example we need to copy our "ceph.conf" and
"ceph.client.cinder.keyring" files, assuming we are using the "cinder" user
into the example/docker directory replacing the existing ones.

.. code-block:: shell

    $ cd examples/docker
    $ ./rbd.sh
    Starting cinderlib CSI v0.0.1 (cinderlib: 0.1.0, cinder: 11.1.0)
    Running backend RBDDriver v1.2.0
    Now serving on [::]:50051...

CSC
~~~

Now that we have the service running we can use the `CSC tool
<https://github.com/rexray/gocsi/tree/master/csc>`_ to run
commands simulating the Container Orchestration system.

Due to the recent changes in the CSI spec not all commands are available yet,
so you won't be able to test the snapshot commands.

Checking the plugin info:

.. code-block:: shell

    $ csc identity plugin-info -e tcp://127.0.0.1:50051
    "com.redhat.cinderlib-csi"      "0.0.1" "cinder-driver"="RBDDriver"     "cinder-driver-supported"="True"        "cinder-driver-version"="1.2.0" "cinder-version"="11.1.0"       "cinderlib-version"="0.1.0"     "persistence"="DBPersistence"

Checking the node id:

.. code-block:: shell

    $ csc node get-id -e tcp://127.0.0.1:50051
    localhost.localdomain

    $ hostname -f
    localhost.localdomain

Checking the current backend capacity:

.. code-block:: shell

    $ csc controller get-capacity -e tcp://127.0.0.1:50051
    24202140712

Creating a volume:

.. code-block:: shell

    $ csc controller create-volume --cap SINGLE_NODE_WRITER,block --req-bytes 2147483648 disk -e tcp://127.0.0.1:50051
    "5ee5fd7c-45cd-44cf-af7b-06081f680f2c"  2147483648


Listing volumes:

.. code-block:: shell

    $ csc controller list-volumes -e tcp://127.0.0.1:50051
    "5ee5fd7c-45cd-44cf-af7b-06081f680f2c"  2147483648

Attaching the volume to `tmp/mnt/publish` on baremetal:

.. code-block:: shell

    $ touch ../../tmp/mnt/{staging,publish}

    $ csc controller publish --cap SINGLE_NODE_WRITER,block --node-id `hostname -f` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    "5ee5fd7c-45cd-44cf-af7b-06081f680f2c"  "connection_info"="{\"connector\": {\"initiator\": \"iqn.1994-05.com.redhat:aa532823bac9\", \"ip\": \"127.0.0.1\", \"platform\": \"x86_64\", \"host\": \"localhost.localdomain\", \"do_local_attach\": false, \"os_type\": \"linux2\", \"multipath\": false}, \"conn\": {\"driver_volume_type\": \"rbd\", \"data\": {\"secret_uuid\": null, \"volume_id\": \"5ee5fd7c-45cd-44cf-af7b-06081f680f2c\", \"auth_username\": \"cinder\", \"secret_type\": \"ceph\", \"name\": \"volumes/volume-5ee5fd7c-45cd-44cf-af7b-06081f680f2c\", \"discard\": true, \"keyring\": \"[client.cinder]\\n\\tkey = AQCQPetaof03IxAAoHZJD6kGxiMQfLdn3QzdlQ==\\n\", \"cluster_name\": \"ceph\", \"hosts\": [\"192.168.1.22\"], \"auth_enabled\": true, \"ports\": [\"6789\"]}}}"

    $ csc node stage --pub-info connection_info="irrelevant" --cap SINGLE_NODE_WRITER,block --staging-target-path `realpath ../../tmp/mnt/staging` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

    $ csc node publish --cap SINGLE_NODE_WRITER,block --pub-info connection_info="irrelevant" --staging-target-path `realpath ../../tmp/mnt/staging` --target-path `realpath ../../tmp/mnt/publish` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

Attaching the volume to `tmp/mnt/publish` on container:

.. code-block:: shell

    $ touch ../../tmp/mnt/{staging,publish}

    $ csc controller publish --cap SINGLE_NODE_WRITER,block --node-id `hostname -f` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    "5ee5fd7c-45cd-44cf-af7b-06081f680f2c"  "connection_info"="{\"connector\": {\"initiator\": \"iqn.1994-05.com.redhat:aa532823bac9\", \"ip\": \"127.0.0.1\", \"platform\": \"x86_64\", \"host\": \"localhost.localdomain\", \"do_local_attach\": false, \"os_type\": \"linux2\", \"multipath\": false}, \"conn\": {\"driver_volume_type\": \"rbd\", \"data\": {\"secret_uuid\": null, \"volume_id\": \"5ee5fd7c-45cd-44cf-af7b-06081f680f2c\", \"auth_username\": \"cinder\", \"secret_type\": \"ceph\", \"name\": \"volumes/volume-5ee5fd7c-45cd-44cf-af7b-06081f680f2c\", \"discard\": true, \"keyring\": \"[client.cinder]\\n\\tkey = AQCQPetaof03IxAAoHZJD6kGxiMQfLdn3QzdlQ==\\n\", \"cluster_name\": \"ceph\", \"hosts\": [\"192.168.1.22\"], \"auth_enabled\": true, \"ports\": [\"6789\"]}}}"

    $ csc node stage --pub-info connection_info="irrelevant" --cap SINGLE_NODE_WRITER,block --staging-target-path /mnt/staging 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

    $ csc node publish --cap SINGLE_NODE_WRITER,block --pub-info connection_info="irrelevant" --staging-target-path /mnt/staging --target-path /mnt/publish 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c


Detaching the volume on baremetal:

.. code-block:: shell

    $ csc node unpublish --target-path `realpath ../../tmp/mnt/publish` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

    $ csc node unstage --staging-target-path `realpath ../../tmp/mnt/staging` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

    $ csc controller unpublish --node-id `hostname -f` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

Detaching the volume on container:

.. code-block:: shell

    $ csc node unpublish --target-path /mnt/publish 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

    $ csc node unstage --staging-target-path /tmp/mnt/staging 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

    $ csc controller unpublish --node-id `hostname -f` 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051
    5ee5fd7c-45cd-44cf-af7b-06081f680f2c

Deleting the volume:

.. code-block:: shell

    $ csc controller delete-volume 5ee5fd7c-45cd-44cf-af7b-06081f680f2c -e tcp://127.0.0.1:50051


Capable operational modes
-------------------------

The CSI spec defines a set of `AccessModes` that CSI drivers can support, such
as single writer, single reader, multiple writers, single writer and multiple
readers.

This CSI driver currently only supports `SINGLE_MODE_WRITER`, although it will
also succeed with the `SINGLE_MODE_READER_ONLY` mode and mount it as
read/write.


Support
-------

For any questions or concerns please file an issue with the
`cinderlib-csi <https://github.com/akrog/cinderlib-csi/issues>`_
project or ping me on IRC (my handle is geguileo and I hang on the
#openstack-cinder channel in Freenode).


TODO
----

There are many things that need to be done in this POC driver, and here's a non
exhaustive list:

- Support for NFS volumes
- Support for mount filesystems
- Support for Kubernetes CRDs as the persistence storage
- Unit tests
- Functional tests
- Improve received parameters checking
- Make driver more resilient
- Test driver in Kubernetes
- Review some of the returned error codes
- Support volume attributes via cinder volume types
- Look into multi-attaching
- Support read-only mode
- Report capacity based on over provisioning values
- Configure the private data location
