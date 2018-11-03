FROM ubuntu:18.04

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update \
&& apt-get install -y vim rsync vagrant virtualbox

COPY Vagrantfile /var/tmp
COPY bootstrap.sh /var/tmp

WORKDIR /var/tmp
CMD ["vagrant", "up" ]
