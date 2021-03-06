#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

import sys
import gevent
sys.path.append("../common/tests")
from testtools.matchers import Equals, Contains, Not
from test_utils import *
import test_common
import test_case
import xmltodict
import collections
from vnc_api.vnc_api import *

try:
    import device_manager 
except ImportError:
    from device_manager import device_manager 

from time import sleep

def retry_exc_handler(tries_remaining, exception, delay):
    print >> sys.stderr, "Caught '%s', %d tries remaining, sleeping for %s seconds" % (exception, tries_remaining, delay)


def retries(max_tries, delay=1, backoff=2, exceptions=(Exception,), hook=None):
    def dec(func):
        def f2(*args, **kwargs):
            mydelay = delay
            tries = range(max_tries)
            tries.reverse()
            for tries_remaining in tries:
                try:
                   return func(*args, **kwargs)
                except exceptions as e:
                    if tries_remaining > 0:
                        if hook is not None:
                            hook(tries_remaining, e, mydelay)
                        sleep(mydelay)
                        mydelay = mydelay * backoff
                    else:
                        raise
                else:
                    break
        return f2
    return dec

def dictMatch(patn, real):
    """dict match pattern"""
    result = True
    if type(patn) is collections.OrderedDict:
        patn = dict(patn)
    if type(real) is collections.OrderedDict:
        real = dict(real)
    try:
        for pkey, pvalue in patn.iteritems():
            if type(pvalue) is dict or type(pvalue) is collections.OrderedDict:
                if type(real[pkey]) is list:   # it is possible if one more than config object is present
                    result = False 
                    for real_item in real[pkey]:
                        result = dictMatch(pvalue, real_item)
                        if result == True:
                            break
                else:  
                    result = dictMatch(pvalue, real[pkey])
            elif type(pvalue) is list:
                result = listMatch(pvalue, real[pkey])
            else:
                if real[pkey] != pvalue:
                    result = False
                    #print "dict key '%s' value '%s' not found in real '%s'\nParents - \nreal '%s'\npatn '%s' "%(pkey, pvalue, real[pkey], real, patn)
                else:
                    result = True
            if result == False:
                #print "Dict key '%s' with value '%s' not found in real '%s'\nParent: \n real '%s'patn '%s'"%(pkey, pvalue, real[pkey], real, patn)
                return result
    except (AssertionError, KeyError):
        result = False
    return result

def listMatch(patn, real):
    result = True
    try:
        for item in patn:
            if type(item) is dict or type(item) is collections.OrderedDict:
                result = False
                for real_item in real:
                    if type(real_item) is dict or type(real_item) is collections.OrderedDict:
                        result = dictMatch(item, real_item)
                        if result == True:
                            break
                if result == False:
                    #print "list Item %s not found in real %s"%(item, real)
                    return result
            elif item not in real:
                #print "list Item %s not found in real %s"%(item, real)
                result = False
    except (AssertionError, KeyError):
        result = False
    return result

# An example usage of above dict compare utilties 
#d1 = {'x': [{'a':'2', 'b':{3: ['iii', 'bb']}}]}
#d2 = {'x': [{'a':'2', 'b':{5: 'xx', 3: ['iii', 'bb'], 4: 'iv'},'c':'4'}]}
#b = dictMatch(d1, d2)   # True

class TestDM(test_case.DMTestCase):

    @retries(10, hook=retry_exc_handler)
    def check_netconf_config_mesg(self, target, xml_config_str):
        manager = fake_netconf_connect(target)
        # convert xmls to dict and see if expected xml config is present in generated config
        # expected config is only the minimum config expected from a test case where as
        # generated config may contain more than that
        #print "\n gen: %s\n expect: %s\n"%(manager.configs[-1], xml_config_str)
        gen_cfg = xmltodict.parse(manager.configs[-1])
        expect_cfg = xmltodict.parse(xml_config_str)
        result = dictMatch(expect_cfg, gen_cfg)
        self.assertTrue(result)
            
    def test_basic_dm(self):
        vn1_name = 'vn1'
        vn2_name = 'vn2'
        vn1_obj = VirtualNetwork(vn1_name)
        vn2_obj = VirtualNetwork(vn2_name)

        vn1_uuid = self._vnc_lib.virtual_network_create(vn1_obj)
        vn2_uuid = self._vnc_lib.virtual_network_create(vn2_obj)

        bgp_router, pr = self.create_router('router1', '1.1.1.1')
        pr.set_virtual_network(vn1_obj)
        self._vnc_lib.physical_router_update(pr)

        pi = PhysicalInterface('pi1', parent_obj = pr)
        pi_id = self._vnc_lib.physical_interface_create(pi)

        li = LogicalInterface('li1', parent_obj = pi)
        li_id = self._vnc_lib.logical_interface_create(li)
        
        for obj in [vn1_obj, vn2_obj]:
            ident_name = self.get_obj_imid(obj)
            gevent.sleep(2)
            ifmap_ident = self.assertThat(FakeIfmapClient._graph, Contains(ident_name))


        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group></bgp></protocols><routing-options><route-distinguisher-id/></routing-options><routing-instances><instance operation="replace"><name>__contrail__default-domain_default-project_vn1</name><instance-type>vrf</instance-type><vrf-import>__contrail__default-domain_default-project_vn1-import</vrf-import><vrf-export>__contrail__default-domain_default-project_vn1-export</vrf-export><vrf-target/><vrf-table-label/></instance></routing-instances><policy-options><policy-statement><name>__contrail__default-domain_default-project_vn1-export</name><term><name>t1</name><then><community><add/><target_64512_8000001/></community><accept/></then></term></policy-statement><policy-statement><name>__contrail__default-domain_default-project_vn1-import</name><term><name>t1</name><from><community>target_64512_8000001</community></from><then><accept/></then></term><then><reject/></then></policy-statement><community><name>target_64512_8000001</name><members>target:64512:8000001</members></community></policy-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)

        self._vnc_lib.logical_interface_delete(li.get_fq_name())
        self._vnc_lib.physical_interface_delete(pi.get_fq_name())
        self._vnc_lib.physical_router_delete(pr.get_fq_name())
        self._vnc_lib.bgp_router_delete(bgp_router.get_fq_name())

        self._vnc_lib.virtual_network_delete(fq_name=vn1_obj.get_fq_name())
        self._vnc_lib.virtual_network_delete(fq_name=vn2_obj.get_fq_name())

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name operation="delete">__contrail__</name></groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)
    # end test_basic_dm
#end

    def test_advance_dm(self):
        vn1_name = 'vn1'
        vn2_name = 'vn2'
        vn1_obj = VirtualNetwork(vn1_name)
        vn2_obj = VirtualNetwork(vn2_name)

        ipam_obj = NetworkIpam('ipam1')
        self._vnc_lib.network_ipam_create(ipam_obj)
        vn1_obj.add_network_ipam(ipam_obj, VnSubnetsType(
            [IpamSubnetType(SubnetType("10.0.0.0", 24))]))

        vn1_uuid = self._vnc_lib.virtual_network_create(vn1_obj)
        vn2_uuid = self._vnc_lib.virtual_network_create(vn2_obj)

        bgp_router, pr = self.create_router('router1', '1.1.1.1')
        pr.set_virtual_network(vn1_obj)
        self._vnc_lib.physical_router_update(pr)

        pi = PhysicalInterface('pi1', parent_obj = pr)
        pi_id = self._vnc_lib.physical_interface_create(pi)

        fq_name = ['default-project', 'vmi1']
        vmi = VirtualMachineInterface(fq_name=fq_name, parent_type = 'project')
        vmi.set_virtual_network(vn1_obj)
        self._vnc_lib.virtual_machine_interface_create(vmi)

        li = LogicalInterface('li1', parent_obj = pi)
        li.vlan_tag = 100
        li.set_virtual_machine_interface(vmi)
        li_id = self._vnc_lib.logical_interface_create(li)

        
        for obj in [vn1_obj, vn2_obj]:
            ident_name = self.get_obj_imid(obj)
            gevent.sleep(2)
            ifmap_ident = self.assertThat(FakeIfmapClient._graph, Contains(ident_name))

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group></bgp></protocols><routing-options><route-distinguisher-id/></routing-options><routing-instances><instance operation="replace"><name>__contrail__default-domain_default-project_vn1</name><instance-type>vrf</instance-type><interface><name>li1</name></interface><vrf-import>__contrail__default-domain_default-project_vn1-import</vrf-import><vrf-export>__contrail__default-domain_default-project_vn1-export</vrf-export><vrf-target/><vrf-table-label/><routing-options><static><route><name>10.0.0.0/24</name><discard/></route></static><auto-export><family><inet><unicast/></inet></family></auto-export></routing-options></instance></routing-instances><policy-options><policy-statement><name>__contrail__default-domain_default-project_vn1-export</name><term><name>t1</name><then><community><add/><target_64512_8000001/></community><accept/></then></term></policy-statement><policy-statement><name>__contrail__default-domain_default-project_vn1-import</name><term><name>t1</name><from><community>target_64512_8000001</community></from><then><accept/></then></term><then><reject/></then></policy-statement><community><name>target_64512_8000001</name><members>target:64512:8000001</members></community></policy-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)

        self._vnc_lib.logical_interface_delete(li.get_fq_name())
        self._vnc_lib.virtual_machine_interface_delete(vmi.get_fq_name())
        self._vnc_lib.physical_interface_delete(pi.get_fq_name())
        self._vnc_lib.physical_router_delete(pr.get_fq_name())
        self._vnc_lib.bgp_router_delete(bgp_router.get_fq_name())

        self._vnc_lib.virtual_network_delete(fq_name=vn1_obj.get_fq_name())
        self._vnc_lib.virtual_network_delete(fq_name=vn2_obj.get_fq_name())

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name operation="delete">__contrail__</name></groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)
    # end test_advance_dm

    def test_bgp_peering(self):
        bgp_router1, pr1 = self.create_router('router1', '1.1.1.1')
        bgp_router2, pr2 = self.create_router('router2', '2.2.2.2')
        families = AddressFamilies(['route-target', 'inet-vpn', 'e-vpn'])
        bgp_sess_attrs = [BgpSessionAttributes(address_families=families)]
        bgp_sessions = [BgpSession(attributes=bgp_sess_attrs)]
        bgp_peering_attrs = BgpPeeringAttributes(session=bgp_sessions)
        bgp_router1.add_bgp_router(bgp_router2, bgp_peering_attrs)
        self._vnc_lib.bgp_router_update(bgp_router1)
        gevent.sleep(2)
        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep><neighbor><name>2.2.2.2</name><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn></family></neighbor></group></bgp></protocols><routing-options><route-distinguisher-id/><autonomous-system>64512</autonomous-system></routing-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>2.2.2.2</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep><neighbor><name>1.1.1.1</name><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn></family></neighbor></group></bgp></protocols><routing-options><route-distinguisher-id/><autonomous-system>64512</autonomous-system></routing-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'
        self.check_netconf_config_mesg('2.2.2.2', xml_config_str)

        params = bgp_router2.get_bgp_router_parameters()
        params.autonomous_system = 64513
        bgp_router2.set_bgp_router_parameters(params)
        self._vnc_lib.bgp_router_update(bgp_router2)

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group><group operation="replace"><name>__contrail_external__</name><type>external</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep><neighbor><name>2.2.2.2</name><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn></family></neighbor></group></bgp></protocols><routing-options><route-distinguisher-id/><autonomous-system>64512</autonomous-system></routing-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)
        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>2.2.2.2</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group><group operation="replace"><name>__contrail_external__</name><type>external</type><multihop/><local-address>2.2.2.2</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep><neighbor><name>1.1.1.1</name><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn></family></neighbor></group></bgp></protocols><routing-options><route-distinguisher-id/><autonomous-system>64513</autonomous-system></routing-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'
        self.check_netconf_config_mesg('2.2.2.2', xml_config_str)

        self._vnc_lib.physical_router_delete(pr1.get_fq_name())
        self._vnc_lib.bgp_router_delete(bgp_router1.get_fq_name())
        self._vnc_lib.physical_router_delete(pr2.get_fq_name())
        self._vnc_lib.bgp_router_delete(bgp_router2.get_fq_name())
    # end test_bgp_peering

    def test_network_policy(self):
        vn1_name = 'vn1'
        vn2_name = 'vn2'

        vn1_obj = self.create_virtual_network(vn1_name, '1.0.0.0/24')
        vn2_obj = self.create_virtual_network(vn2_name, '2.0.0.0/24')

        bgp_router, pr = self.create_router('router1', '1.1.1.1')
        pr.set_virtual_network(vn1_obj)
        self._vnc_lib.physical_router_update(pr)
        np = self.create_network_policy(vn1_obj, vn2_obj)

        seq = SequenceType(1, 1)
        vnp = VirtualNetworkPolicyType(seq)
        vn1_obj.set_network_policy(np, vnp)
        vn2_obj.set_network_policy(np, vnp)
        vn1_uuid = self._vnc_lib.virtual_network_update(vn1_obj)
        vn2_uuid = self._vnc_lib.virtual_network_update(vn2_obj)

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group></bgp></protocols><routing-options><route-distinguisher-id/><autonomous-system>64512</autonomous-system></routing-options><routing-instances><instance operation="replace"><name>__contrail__default-domain_default-project_vn1</name><instance-type>vrf</instance-type><vrf-import>__contrail__default-domain_default-project_vn1-import</vrf-import><vrf-export>__contrail__default-domain_default-project_vn1-export</vrf-export><vrf-target/><vrf-table-label/><routing-options><static><route><name>1.0.0.0/24</name><discard/></route></static><auto-export><family><inet><unicast/></inet></family></auto-export></routing-options></instance></routing-instances><policy-options><policy-statement><name>__contrail__default-domain_default-project_vn1-export</name><term><name>t1</name><then><community><add/><target_64512_8000001/><target_64512_8000002/></community><accept/></then></term></policy-statement><policy-statement><name>__contrail__default-domain_default-project_vn1-import</name><term><name>t1</name><from><community>target_64512_8000001</community><community>target_64512_8000002</community></from><then><accept/></then></term><then><reject/></then></policy-statement><community><name>target_64512_8000001</name><members>target:64512:8000001</members></community><community><name>target_64512_8000002</name><members>target:64512:8000002</members></community></policy-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>' 
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)

    def test_public_vrf_dm(self):
        vn1_name = 'vn1'
        vn1_obj = VirtualNetwork(vn1_name)
        vn1_obj.set_router_external(True)
        ipam_obj = NetworkIpam('ipam1')
        self._vnc_lib.network_ipam_create(ipam_obj)
        vn1_obj.add_network_ipam(ipam_obj, VnSubnetsType(
            [IpamSubnetType(SubnetType("192.168.7.0", 24))]))

        vn1_uuid = self._vnc_lib.virtual_network_create(vn1_obj)

        bgp_router, pr = self.create_router('router10', '1.1.1.1')
        pr.set_virtual_network(vn1_obj)
        self._vnc_lib.physical_router_update(pr)

        pi = PhysicalInterface('pi1', parent_obj = pr)
        pi_id = self._vnc_lib.physical_interface_create(pi)

        li = LogicalInterface('li1', parent_obj = pi)
        li_id = self._vnc_lib.logical_interface_create(li)

        for obj in [vn1_obj]:
            ident_name = self.get_obj_imid(obj)
            gevent.sleep(2)
            ifmap_ident = self.assertThat(FakeIfmapClient._graph, Contains(ident_name))

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group><group operation="replace"><name>__contrail_external__</name><type>external</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group></bgp></protocols><routing-options><route-distinguisher-id/><autonomous-system>64512</autonomous-system></routing-options><routing-instances><instance operation="replace"><name>__contrail__default-domain_default-project_vn1</name><instance-type>vrf</instance-type><vrf-import>__contrail__default-domain_default-project_vn1-import</vrf-import><vrf-export>__contrail__default-domain_default-project_vn1-export</vrf-export><vrf-target/><vrf-table-label/><routing-options><static><route><name>192.168.7.0/24</name><discard/><inet.0/></route><route><name>0.0.0.0/0</name><next-table/><inet.0/></route></static><auto-export><family><inet><unicast/></inet></family></auto-export></routing-options></instance></routing-instances><policy-options><policy-statement><name>__contrail__default-domain_default-project_vn1-export</name><term><name>t1</name><then><community><add/><target_64512_8000001/></community><accept/></then></term></policy-statement><policy-statement><name>__contrail__default-domain_default-project_vn1-import</name><term><name>t1</name><from><community>target_64512_8000001</community></from><then><accept/></then></term><then><reject/></then></policy-statement><community><name>target_64512_8000001</name><members>target:64512:8000001</members></community></policy-options><firewall><filter><name>redirect_to___contrail__default-domain_default-project_vn1_vrf</name><term><name>t1</name><from><destination-address>192.168.7.0/24</destination-address></from><then><routing-instance>__contrail__default-domain_default-project_vn1</routing-instance></then></term><term><name>t2</name><then><accept/></then></term></filter></firewall><forwarding-options><family><name>inet</name><filter><input>redirect_to___contrail__default-domain_default-project_vn1_vrf</input></filter></family></forwarding-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'

        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)

        self._vnc_lib.logical_interface_delete(li.get_fq_name())
        self._vnc_lib.physical_interface_delete(pi.get_fq_name())
        self._vnc_lib.physical_router_delete(pr.get_fq_name())
        self._vnc_lib.bgp_router_delete(bgp_router.get_fq_name())

        self._vnc_lib.virtual_network_delete(fq_name=vn1_obj.get_fq_name())

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name operation="delete">__contrail__</name></groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)
    # end test_basic_dm

    def test_evpn(self):
        vn1_name = 'vn1'
        vn1_obj = VirtualNetwork(vn1_name)
        vn1_obj.set_router_external(True)
        ipam_obj = NetworkIpam('ipam1')
        self._vnc_lib.network_ipam_create(ipam_obj)
        vn1_obj.add_network_ipam(ipam_obj, VnSubnetsType(
            [IpamSubnetType(SubnetType("192.168.7.0", 24))]))

        vn1_obj_properties = VirtualNetworkType()
        vn1_obj_properties.set_vxlan_network_identifier(2000)
        vn1_obj.set_virtual_network_properties(vn1_obj_properties)

        vn1_uuid = self._vnc_lib.virtual_network_create(vn1_obj)

        bgp_router, pr = self.create_router('router10', '1.1.1.1')
        pr.set_virtual_network(vn1_obj)
        self._vnc_lib.physical_router_update(pr)

        pi = PhysicalInterface('pi1', parent_obj = pr)
        pi_id = self._vnc_lib.physical_interface_create(pi)

        fq_name = ['default-project', 'vmi1']
        vmi1 = VirtualMachineInterface(fq_name=fq_name, parent_type = 'project')
        vmi1.set_virtual_network(vn1_obj)
        self._vnc_lib.virtual_machine_interface_create(vmi1)

        fq_name = ['default-project', 'vmi2']
        vmi2 = VirtualMachineInterface(fq_name=fq_name, parent_type = 'project')
        vmi2.set_virtual_network(vn1_obj)
        self._vnc_lib.virtual_machine_interface_create(vmi2)

        li1 = LogicalInterface('li1', parent_obj = pi)
        li1.set_virtual_machine_interface(vmi1)
        li1_id = self._vnc_lib.logical_interface_create(li1)

        li2 = LogicalInterface('li2', parent_obj = pi)
        li2.set_virtual_machine_interface(vmi2)
        li2_id = self._vnc_lib.logical_interface_create(li2)

        for obj in [vn1_obj]:
            ident_name = self.get_obj_imid(obj)
            gevent.sleep(2)
            ifmap_ident = self.assertThat(FakeIfmapClient._graph, Contains(ident_name))

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name>__contrail__</name><protocols><bgp><group operation="replace"><name>__contrail__</name><type>internal</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group><group operation="replace"><name>__contrail_external__</name><type>external</type><multihop/><local-address>1.1.1.1</local-address><family><route-target/><inet-vpn><unicast/></inet-vpn><evpn><signaling/></evpn><inet6-vpn><unicast/></inet6-vpn></family><keep>all</keep></group></bgp></protocols><routing-options><route-distinguisher-id/><autonomous-system>64512</autonomous-system></routing-options><routing-instances><instance operation="replace"><name>__contrail__default-domain_default-project_vn1</name><instance-type>virtual-switch</instance-type><vrf-import>__contrail__default-domain_default-project_vn1-import</vrf-import><vrf-export>__contrail__default-domain_default-project_vn1-export</vrf-export><vrf-target/><vrf-table-label/><routing-options><static><route><name>192.168.7.0/24</name><discard/><inet.0/></route><route><name>0.0.0.0/0</name><next-table/><inet.0/></route></static><auto-export><family><inet><unicast/></inet></family></auto-export></routing-options><bridge-domains><bd-2000><vlan-id>2000</vlan-id><vxlan><vni>2000</vni><ingress-node-replication/></vxlan><interface><name>li1</name></interface><interface><name>li2</name></interface><routing-interface><name>irb.2000</name></routing-interface><routing-interface/></bd-2000></bridge-domains><protocols><evpn><encapsulation>vxlan</encapsulation><extended-vni-all/></evpn></protocols></instance></routing-instances><interfaces><interface><name>irb</name><gratuitous-arp-reply/><unit><name>2000</name><family><inet><address><name>192.168.7.254</name></address></inet></family></unit></interface><interface><name>lo0</name><unit><name>0</name><family><inet/><address><name>1.1.1.1</name></address></family></unit></interface><interface><name>li1</name><encapsulation>ethernet-bridge</encapsulation><unit><name>0</name><family><bridge/></family></unit></interface><interface><name>li2</name><encapsulation>ethernet-bridge</encapsulation><unit><name>0</name><family><bridge/></family></unit></interface></interfaces><policy-options><policy-statement><name>__contrail__default-domain_default-project_vn1-export</name><term><name>t1</name><then><community><add/><target_64512_8000001/></community><accept/></then></term></policy-statement><policy-statement><name>__contrail__default-domain_default-project_vn1-import</name><term><name>t1</name><from><community>target_64512_8000001</community></from><then><accept/></then></term><then><reject/></then></policy-statement><community><name>target_64512_8000001</name><members>target:64512:8000001</members></community></policy-options><firewall><filter><name>redirect_to___contrail__default-domain_default-project_vn1_vrf</name><term><name>t1</name><from><destination-address>192.168.7.0/24</destination-address></from><then><routing-instance>__contrail__default-domain_default-project_vn1</routing-instance></then></term><term><name>t2</name><then><accept/></then></term></filter></firewall><forwarding-options><family><name>inet</name><filter><input>redirect_to___contrail__default-domain_default-project_vn1_vrf</input></filter></family></forwarding-options></groups><apply-groups>__contrail__</apply-groups></configuration></config>'

        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)

        self._vnc_lib.logical_interface_delete(li1.get_fq_name())
        self._vnc_lib.logical_interface_delete(li2.get_fq_name())
        self._vnc_lib.virtual_machine_interface_delete(vmi1.get_fq_name())
        self._vnc_lib.virtual_machine_interface_delete(vmi2.get_fq_name())
        self._vnc_lib.physical_interface_delete(pi.get_fq_name())
        self._vnc_lib.physical_router_delete(pr.get_fq_name())
        self._vnc_lib.bgp_router_delete(bgp_router.get_fq_name())

        self._vnc_lib.virtual_network_delete(fq_name=vn1_obj.get_fq_name())

        xml_config_str = '<config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0"><configuration><groups><name operation="delete">__contrail__</name></groups></configuration></config>'
        self.check_netconf_config_mesg('1.1.1.1', xml_config_str)
    # end test_evpn
#end

#end
