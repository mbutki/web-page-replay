#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import errno
import logging
import platformsettings
import socket
import SocketServer


class DnsProxyError(Exception):
  pass

class PermissionDenied(DnsProxyError):
  pass


class UdpDnsHandler(SocketServer.DatagramRequestHandler):
  """Resolve DNS queries to localhost.

  Possible alternative implementation:
  http://howl.play-bow.org/pipermail/dnspython-users/2010-February/000119.html
  """

  STANDARD_QUERY_OPERATION_CODE = 0

  def handle(self):
    self.data = self.rfile.read()
    self.transaction_id = self.data[0]
    self.flags = self.data[1]
    self.qa_counts = self.data[4:6]
    self.domain = ''
    operation_code = (ord(self.data[2]) >> 3) & 15
    if operation_code == self.STANDARD_QUERY_OPERATION_CODE:
      self.wire_domain = self.data[12:]
      self.domain = self._domain(self.wire_domain)
    else:
      logging.debug("DNS request with non-zero operation code: %s",
                    operation_code)

    logging.debug('DNS reply for %s with %s', self.domain, self.server.host)
    self.reply(self.get_dns_reply(self.server.host))

  @classmethod
  def _domain(cls, wire_domain):
    domain = ''
    index = 0
    length = ord(wire_domain[index])
    while length:
      domain += wire_domain[index + 1:index + length + 1] + '.'
      index += length + 1
      length = ord(wire_domain[index])
    return domain

  def reply(self, buf):
    self.wfile.write(buf)

  def get_dns_reply(self, ip):
    packet = ''
    if self.domain:
      logging.debug("DNS request to fake DNS server: %s -> %s", self.domain, ip)
      packet = (
          self.transaction_id +
          self.flags +
          '\x81\x80' +        # standard query response, no error
          self.qa_counts * 2 + '\x00\x00\x00\x00' +  # Q&A counts
          self.wire_domain +
          '\xc0\x0c'          # pointer to domain name
          '\x00\x01'          # resource record type ("A" host address)
          '\x00\x01'          # class of the data
          '\x00\x00\x00\x3c'  # ttl (seconds)
          '\x00\x04' +        # resource data length (4 bytes for ip)
          socket.inet_aton(ip)
          )
    return packet


class DnsProxyServer(SocketServer.ThreadingUDPServer):
  def __init__(self, host='127.0.0.1', port=53, platform_settings=platformsettings.get_platform_settings()):
    self.host = host
    self.platform_settings = platform_settings
    try:
      SocketServer.ThreadingUDPServer.__init__(
          self, (host, port), UdpDnsHandler)
    except socket.error, (error_number, msg):
      if error_number == errno.EACCES:
        raise PermissionDenied
      raise
    logging.info('Started DNS server on (%s:%s)...', host, port)
    platform_settings.set_primary_dns(host)

  def cleanup(self):
    self.platform_settings.restore_primary_dns()
    self.shutdown()
    logging.info('Shutdown DNS server')
