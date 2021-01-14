Introduction
============

The Container Storage Interface (`CSI`_) is a standard for provision and use block and file storage systems in containerized workloads on Container Orchestration Systems (COs) like OpenShift.

Using this interface new storage systems can be exposed to COs without needing to change the COs code.

Ember-CSI is an Open Source implementation of the `CSI`_ specification supporting storage solutions from multiple vendors by leveraging a library called `cinderlib <https://docs.openstack.org/cinderlib/latest/>`_ that provides an abstraction layer over the storage drivers.


Features
--------

Ember-CSI supports `CSI`_ versions 0.2, 0.3, 1.0, and 1.1 providing the following features:

- Volume provisioning: file and block types
- Volume cloning
- Volume deletion
- Snapshot creation
- Create volume from a snapshot
- Snapshots deletion
- Listing volumes with pagination
- Listing snapshots with pagination
- Attaching/Detaching volumes
- Multi pod attaching (block mode only)
- Storage capacity reporting
- Node probing

Limitations
-----------

There are 2 types of volumes in OpenShift and Kubernetes, Block and File, and while both are supported by Ember-CSI, behind the scenes all the storage drivers in Ember-CSI are for block storage systems.

To provide File volumes from block storage Ember-CSI connects the volumes to the host, formats and present them to the Orchestrator for the containerized workloads.

Since File type volumes are locally attached block volumes they cannot be shared between containers, so the Shared Access (RWX) Access Mode is not supported.

This limitation does not apply to block volumes, that can be mounted in multiple hosts simultaneously and it's the application the one responsible to orchestrate the proper access to the disk.

Supported drivers
-----------------

Ember-CSI includes a good number of storage drivers, but due to limitation on hardware availability only a small number of them have been validated at one point or another.  In alphabetical order they are:

- HPE3PARFC
- HPE3PARISCSI
- KaminarioISCSI
- LVMVolume
- PowerMaxFC
- PowerMaxISCSI
- PureFC
- PureISCSI
- QnapISCSI
- RBD
- SolidFire
- SynoISCSI
- XtremIOFC
- XtremIOISCSI

The remaining drivers included in Ember-CSI have not been validated yet:

- ACCESSIscsi
- AS13000
- FJDXFC
- FJDXISCSI
- FlashSystemFC
- FlashSystemISCSI
- GPFS
- GPFSRemote
- HPELeftHandISCSI
- HPMSAFC
- HPMSAISCSI
- HedvigISCSI
- HuaweiFC
- HuaweiISCSI
- IBMStorage
- InStorageMCSFC
- InStorageMCSISCSI
- InfortrendCLIFC
- InfortrendCLIISCSI
- LenovoFC
- LenovoISCSI
- LinstorDrbd
- LinstorIscsi
- MStorageFC
- MStorageISCSI
- MacroSANFC
- MacroSANISCSI
- NetAppCmodeFibreChannel
- NetAppCmodeISCSI
- NexentaISCSI
- PSSeriesISCSI
- Quobyte
- RSD
- SCFC
- SCISCSI
- SPDK
- Sheepdog
- StorPool
- StorwizeSVCFC
- StorwizeSVCISCSI
- Unity
- VNX
- VZStorage
- VxFlexOS
- WindowsISCSI
- WindowsSmbfs
- ZadaraVPSAISCS


.. _CSI: https://github.com/container-storage-interface/spec
