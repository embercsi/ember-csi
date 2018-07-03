FROM akrog/cinderlib:stable
LABEL maintainers="Gorka Eguileor <geguileo@redhat.com>"
LABEL description="Cinderlib CSI Plugin"

RUN yum -y install xfsprogs e2fsprogs btrfs-progs && yum clean all && rm -rf /var/cache/yum && pip install --no-cache-dir --process-dependency-links cinderlib-csi

# This is the default port, but if we change it via CSI_ENDPOINT then this will
# no longer be relevant.
EXPOSE 50051

# Define default command
CMD ["cinderlib-csi"]
