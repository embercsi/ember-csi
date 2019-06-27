# History

## 1.0.0 (2019-xx-yy)

## Bugs:

- Fix listings with invalid token
- Fix list pagination with future tokens
- Fix volume cloning
- Fix getting volume stats

## 0.9.0 (2019-06-04)

Beta release with full CSI v0.2, v0.3, and v1.0 spec support.

### Features

- Multi-driver support on single container
- Support for mount filesystems
- Support for block
- Topology support
- Snapshot support
- Liveness probe
- CRD metadata persistence plugin
- Multi-version support on single container
- Aliases for configuration
- Storage driver list tool
- Support live debugging of running driver
- Duplicated requests queuing support (for k8s)
- Support of mocked probe
- Configurable default mount filesystem

### Bugs

- Fix issues receiving duplicated RPC calls
- Fix UUID warning
- Check staging and publishing targets
- Exit on binding error


## 0.0.2 (2018-06-19)

* Use cinderlib v0.2.1 instead of github branch


## 0.0.1 (2018-05-18)

* First release on PyPI.
