#!/usr/bin/python
# coding : utf8

from fastsnmpy import SnmpSession
'''
fastsnmpy classes for 'netsnmp extension module'
    Copyright (c) 2010-2016 Ajay Divakaran
    'fastsnmpy' is free to use . This includes the classes and modules of fastsnmpy as well as any examples and code contained in the package. 
    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), 
    to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, 
    distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so.
'''
import json
from time import time
import shelve
import argparse
import sys
import humanize
import os

parser = argparse.ArgumentParser(
    description='Check traffic on Cisco Switch from a list of interface IDs.',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-H", "--hostname",
                    dest="switch",
                    help="Switch Name")
parser.add_argument("-i", "--interface",
                    dest="interfaces",
                    help="Interfaces iid list string, ex:'1501 1201 1001'")
parser.add_argument("-d", "--directory",
                    dest="directory",
                    help="Spool Directory, ex: /var/spool/icinga2/traffic/")
parser.add_argument("-W", "--warning",
                    dest="warning",
                    help="Warning usage in %%",
                    default=85)
parser.add_argument("-C", "--critical",
                    dest="critical",
                    help="Critical usage in %%",
                    default=95)
parser.add_argument("-c", "--community",
                    dest="community",
                    help="SNMP Community",
                    default='public')
args = parser.parse_args()


def counter_overflow(b, last_b):
    '''
    Works for 64 bit counter_overflow
    ifHCInOctets & ifHCOutOctets
    '''
    max_b = 18446744073709600000  # the value is 2^64
    if b < last_b:
        b += max_b
    return b


def snmpWalk():
    newsession = SnmpSession(
        targets=switch,
        oidlist=['ifSpeed', 'ifHCInOctets',
                 'ifHCOutOctets', 'ifDescr', 'ifAlias'],
        community=community)
    results = newsession.snmpbulkwalk(workers=10)
    return (l for l in json.loads(results) if l['iid'] in set(interfaces))


def build_check_dict(snmp_walk):
    now = dict([('ifaces', dict.fromkeys(interfaces, {}))])
    now['time'] = int(time())
    for iid in interfaces:
        now['ifaces'][iid] = {}
    for line in snmp_walk:
        now['ifaces'][line['iid']][line['tag']] = str(line['val'])
    return now


def av(new, previous, timelaps):
    return 8 * (new - previous) / timelaps


def compare_data(now):
    previous = shelve.open(directory + str(switch[0]))
    if os.path.isfile(directory + str(switch[0])):
        for iid in interfaces:
            try:
                in_b = int(now['ifaces'][iid]['ifHCInOctets'])
                prev_in_b = int(previous['ifaces'][iid]['ifHCInOctets'])
                out_b = int(now['ifaces'][iid]['ifHCOutOctets'])
                prev_out_b = int(previous['ifaces'][iid]['ifHCOutOctets'])
                in_b = counter_overflow(in_b, prev_in_b)
                out_b = counter_overflow(out_b, prev_out_b)
                timelaps = now['time'] - previous['time']
                now['ifaces'][iid]['out_ave'] = av(out_b, prev_out_b, timelaps)
                now['ifaces'][iid]['in_ave'] = av(in_b, prev_in_b, timelaps)
                now['ifaces'][iid]['inUsage'] = round(
                    float(now['ifaces'][iid]['in_ave']) * 100 /
                    int(now['ifaces'][iid]['ifSpeed']), 2)
                now['ifaces'][iid]['outUsage'] = round(
                    float(now['ifaces'][iid]['out_ave']) * 100 /
                    int(now['ifaces'][iid]['ifSpeed']), 2)
            except KeyError as e:
                print 'Error : ' + str(e) + ' ' + iid + ':' + now['ifaces'][iid]['ifDescr']
                pass

    previous['time'] = now['time']
    previous['ifaces'] = now['ifaces']
    previous.close()
    return now


def build_alert(now):
    result = 'SNMP OK\n'
    alert = {}
    perfdata = ' | '
    for iid in interfaces:
        try:
            inUsage, outUsage, in_ave, out_ave, ifAlias = (
                now['ifaces'][iid][k] for k in (
                    'inUsage', 'outUsage', 'in_ave', 'out_ave', 'ifAlias'))
        except KeyError as e:
            print 'Error : ' + str(e) + ' ' + now['ifaces'][iid]['ifDescr']
        if inUsage > warning and inUsage < critical:
            alert[now['ifaces'][iid]['ifDescr']] = (
                'SNMP WARNING : INusage=' + str(inUsage) + '%% -' + ifAlias)
        if inUsage > critical:
            alert[now['ifaces'][iid]['ifDescr']] = (
                'SNMP CRITICAL : INusage=' + str(inUsage) + '%% -' + ifAlias)
        if outUsage > warning and outUsage < critical:
            alert[now['ifaces'][iid]['ifDescr']] = (
                'SNMP WARNING : OUTusage=' + str(outUsage) + '%% -' + ifAlias)
        if outUsage > critical:
            alert[now['ifaces'][iid]['ifDescr']] = (
                'SNMP CRITICAL : OUTusage=' + str(outUsage) + '%% -' + ifAlias)
        result += (
            now['ifaces'][iid]['ifDescr'] + ': Average IN=' +
            str(humanize.naturalsize(in_ave)) + '(' + str(inUsage) +
            '%) Average OUT=' + str(humanize.naturalsize(out_ave)) +
            '(' + str(outUsage) + '%)\n')

        desc = now['ifaces'][iid]['ifDescr'].replace('/', '_')
        perfdata += (
            desc + '.outBandwidth=' + str(out_ave) + 'B ' + desc +
            '.inBandwidth=' + str(in_ave) + 'B ')
        perfdata += (
            desc + '.outUsage=' + str(outUsage) + '% ' + desc +
            '.inUsage=' + str(inUsage) + '% ')

    return result, alert, perfdata


def answer(result, alert, perfdata, interfaces):
    if result == 'SNMP OK\n':
        print "UNKOWN, interfaces is : " + str(interfaces)
        sys.exit(3)
    if alert.keys():
        for key, value in alert.iteritems():
            if 'CRITICAL' in value:
                print value + ' on ' + str(key) + perfdata
                sys.exit(2)
            else:
                print value + ' on ' + str(key) + perfdata
        sys.exit(1)
    else:
        print result + perfdata
        sys.exit(0)


if __name__ == '__main__':
    switch = [args.switch]
    interfaces = set(i for i in (args.interfaces).split(' ') if i != '')
    directory = [args.directory][0]
    warning = [args.warning][0]
    critical = [args.critical][0]
    community = [args.community][0]

    snmp = snmpWalk()
    now = compare_data(build_check_dict(snmp))

    result, alert, perfdata = build_alert(now)

    answer(result, alert, perfdata, interfaces)
