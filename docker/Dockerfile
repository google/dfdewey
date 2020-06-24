# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Use the official Docker Hub Ubuntu 18.04 base image
FROM ubuntu:18.04

# Update the base image
RUN apt update
RUN apt -y install apt-utils && apt -y upgrade && apt -y dist-upgrade

# Setup install environment and DFDewey dependencies
RUN apt install -y build-essential git autoconf automake flex gcc g++ libewf-dev libssl-dev zlib1g-dev libxml2-dev dpkg-dev openssl patch wget bison
# TODO(dfjxs): Package and install from GIFT PPA
RUN git clone --recursive https://github.com/simsong/bulk_extractor
RUN cd bulk_extractor && autoheader -f && aclocal -I m4 && autoconf -f && automake --add-missing --copy && ./configure && make -j $(nproc) && make install
RUN rm -Rf ./bulk_extractor

# Setup dfDewey
RUN git clone https://github.com/google/dfdewey.git
RUN apt install -y python3 python3-pip python3-dev
RUN pip3 install -r dfdewey/requirements.txt
COPY dfdewey /usr/bin/
RUN chmod a+x /usr/bin/dfdewey
