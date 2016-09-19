#!/usr/bin/python
#coding : utf8

import netsnmp
from fastsnmpy import SnmpSession
import json
from time import time
import shelve
import argparse
import sys
import humanize
import os

parser = argparse.ArgumentParser()
parser.add_argument("-H", "--hostname", dest="switch", help ="Switch Name")
parser.add_argument("-i", "--interface", dest="interfaces", help ="Interfaces iid list")
args = parser.parse_args()
switch = [args.switch]
interfaces= (args.interfaces).split(' ')

try:
    os.makedirs('/var/spool/icinga2/traffic/')
except OSError:
	pass
d = shelve.open('/var/spool/icinga2/traffic/'+str(switch[0]))

check_dict={}
check_dict['interfaces']={}
for interface in interfaces:
	check_dict['interfaces'][interface]={}


def counter_overflow(bytes,last_bytes):
	max_bytes = 18446744073709600000;#the value is 2^64
	if bytes < last_bytes : bytes += max_bytes 
	return bytes

oidlist = ['ifSpeed','ifHCInOctets','ifHCOutOctets','ifDescr']

check_time = int(time())
check_dict['last_check_time']=check_time
newsession = SnmpSession ( targets = switch, oidlist = oidlist, community='public' )
results = newsession.snmpbulkwalk(workers=10)

for line in json.loads(results):
	if line['iid'] in interfaces:
		check_dict['interfaces'][line['iid']][line['tag']]=str(line['val'])

icinga_result='SNMP OK\n'
alert_dict={}
perfdata=' | '
for iid in interfaces:
	try:
		in_bytes = int(check_dict['interfaces'][iid]['ifHCInOctets'])
		last_in_bytes = int(d['interfaces'][iid]['ifHCInOctets'])
		out_bytes = int(check_dict['interfaces'][iid]['ifHCOutOctets'])
		last_out_bytes = int(d['interfaces'][iid]['ifHCOutOctets'])
		in_bytes  = counter_overflow( in_bytes,  last_in_bytes )
		out_bytes = counter_overflow( out_bytes, last_out_bytes )
		out_ave = (out_bytes - last_out_bytes) /(check_time  -d['last_check_time'])
		in_ave  = (in_bytes -last_in_bytes)    / (check_time -d['last_check_time'])
		inUsage = round(float(8*in_ave)*100/int(check_dict['interfaces'][iid]['ifSpeed']),2)
		outUsage = round(float(8*out_ave)*100/int(check_dict['interfaces'][iid]['ifSpeed']),2)
		if inUsage > 85 and inUsage < 95:
			alert_dict[check_dict['interfaces'][iid]['ifDescr']]='SNMP WARNING : INusage='+str(inUsage)+'%'
		if inUsage > 95:
			alert_dict[check_dict['interfaces'][iid]['ifDescr']]='SNMP CRITICAL : INusage='+str(inUsage)+'%'
		if outUsage > 85 and outUsage < 95:
			alert_dict[check_dict['interfaces'][iid]['ifDescr']]='SNMP WARNING : OUTusage='+str(outUsage)+'%'
		if outUsage > 95:
			alert_dict[check_dict['interfaces'][iid]['ifDescr']]='SNMP CRITICAL : OUTusage='+str(outUsage)+'%'
		icinga_result+=check_dict['interfaces'][iid]['ifDescr']+': Average IN='+str(humanize.naturalsize(in_ave))+'('+str(inUsage) + '%) Average OUT='+str(humanize.naturalsize(out_ave))+'('+str(outUsage) +'%)\n' 
		perfdata+=check_dict['interfaces'][iid]['ifDescr'].replace('/','_')+'.outBandwidth='+str(out_ave)+'B '+check_dict['interfaces'][iid]['ifDescr'].replace('/','_')+'.inBandwidth='+str(in_ave)+'B '
	except KeyError:
		pass

d["last_check_time"]=check_time
d["interfaces"]= check_dict["interfaces"]
d.close()

if icinga_result=='SNMP OK\n':
	print "UNKOWN, interfaces is : "+str(interfaces)
	sys.exit(3)
if alert_dict.keys():
	for key, value in alert_dict.iteritems():
		if 'CRITICAL' in value:
			print value +' on '+str(key)+perfdata
			sys.exit(2)
		else:
			print value +' on '+str(key)+perfdata
	sys.exit(1)	
else:
	print icinga_result+perfdata
	sys.exit(0)
