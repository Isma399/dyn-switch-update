#!/usr/bin/python
#coding : utf8

# Updates from a given dictionnary of switches the Icinga configuration.
# Generates a Grafana DashBoard
# Each switch has a custom attribute : vars.interfaces = "1 3 4 6 .."
# This string list every interfaces up.
#
# The service is declared like that : 
# apply Service "traffic" {
#  check_command = "traffic"
#  vars.interfaces = host.vars.interfaces
#  assign where host.vars.interfaces
# }
#
# The command is :
# object CheckCommand "traffic" {
#   import "plugin-check-command"
#   command = [PluginContribDir + "/check_iftraffic.py" ]
#   arguments = {
#     "-H" = {
#       value = "$address$"
#       description = "The host checked by SNMP"
#     }
#     "-i" = {
#       value = "$service.vars.interfaces$"
#       description = "Interface description"
#     }
#   }
# }

# The plugin check_iftraffic.py could be find here : 
# https://raw.githubusercontent.com/Isma399/dyn-switch-update/master/check_iftraffic.py


import netsnmp
from fastsnmpy import SnmpSession
import json
import socket
import subprocess
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
import sys
import os


def sendMail(icinga_srv, your_mail, mail_srv):
  msg = MIMEMultipart()
  msg['From'] = icinga_srv
  msg['To'] = your_mail
  msg['Subject'] = 'Dynamic Updating switches.conf has failed.'
  part = MIMEText('Dynamic Updating switches.conf has failed.', 'plain')
  msg.attach(part)
  mailserver = smtplib.SMTP(mail_srv, 25)
  mailserver.ehlo()
  mailserver.starttls()
  mailserver.ehlo()
  mailserver.sendmail(icinga_srv,your_mail , msg.as_string())
  mailserver.quit()
  
def snmp_bulk_walk(dict_sw, snmp_community):
    '''
    Populate switches's dict with snmp tag & value
    Need fastsnmpy from https://github.com/ajaysdesk/fastsnmpy
    http://www.ajaydivakaran.com/

    fastsnmpy classes for 'netsnmp extension module'
    Copyright (c) 2010-2016 Ajay Divakaran
    'fastsnmpy' is free to use . This includes the classes and modules of fastsnmpy as well as any examples and code contained in the package. 
    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), 
    to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, 
    distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so.
    '''
    oids = ['ifDescr','ifOperStatus','ifAlias']
    newsession = SnmpSession ( targets = dict_sw.keys(), oidlist = oids, community= snmp_community )
    results = newsession.snmpbulkwalk(workers=len(dict_sw))
    for line in json.loads(results):
        if line['iid'] not in dict_sw[line['hostname']].keys():
            dict_sw[line['hostname']][line['iid']]={}
        dict_sw[line['hostname']][line['iid']][line['tag']]=str(line['val'])

        
def clean_dict(dict_sw):
    '''
    Remove unrouted VLAN, Stack, Null0 interfaces
    Remove interfaces down (ifOperStatus!=1)
    Remove interfaces where ifSpeed not defined
    '''
    for switch in switches.keys():
        for i in switches[switch].keys():
            if i not in ("regex","load"):
                if switches[switch][i]['ifDescr'][0:13] == 'unrouted VLAN':
                    del switches[switch][i]
                try:
                    if switches[switch][i]['ifDescr'][0:5] == 'Stack':
                        del switches[switch][i]
                except KeyError:
                    pass
                try:
                    if switches[switch][i]['ifDescr'] == 'Null0':
                        del switches[switch][i]
                except KeyError:
                    pass
                try:
                    if switches[switch][i]['ifOperStatus'] != '1' or switches[switch][i]["ifSpeed"] == '':
                        del switches[switch][i]
                    del switches[switch][i]['ifOperStatus']
                except KeyError:
                    pass

def write_icinga_conf(dict_sw, icinga_conf_file, icinga_srv, your_mail, mailhost):
    '''
    Generate a string vars.interfaces = " iid iid iid ..."
    Write the conf file and reload icinga if everything is fine, else mail alert
    '''
    result='#Fichier genere automatiquement.\n#Ne pas editer.\n'
    for switch in switches.keys():
        result+='object Host "'+switch+'" {\n\timport "generic-switch"\
            \n\tgroups = [ "switches" ]\n'
        result+='\taddress = "'+socket.gethostbyname(switch)+'"\n'
        try:
            result+='\tvars.load = "'+ switches[switch]["load"]+'"\n'
        except KeyError:
            pass
        try:
            result+='\tvars.regex = "'+ switches[switch]["regex"]+'"\n'
        except KeyError:
            pass
        d='"'   
        for key,interface in switches[switch].iteritems():
            if str(key) not in ("regex","load"):
                d+=key+' '
        result+='\tvars.interfaces ='+str(d)+'"\n'      
        result+='}\n'       
    
    with open(icinga_conf_file,'w') as config_file:
        config_file.write(result)
        
    try:
        subprocess.check_output(['icinga2','daemon','--validate'])
        subprocess.check_output(['systemctl','reload','icinga2.service'])
    except subprocess.CalledProcessError:
        sendMail(icinga_srv, your_mail, mailhost)
        sys.exit(1)
    return result


def write_grafana_conf(dict_sw):
    '''
    Write a yaml file to build grafana dashboard (named Switches)
    '''
    result =("- name: MRTGlike project\n  project:\n    dashboards:\n" 
            "      - Switch\n"
            "- name: Switch\n"
            "  dashboard:\n    title: Switch\n"
            "    tags:\n      - MRTGlike\n    rows:\n"
            "      - row:\n"
            "          collapse: false\n"
            "          height: 120px\n"
            "          panels:\n")
    
    for switch in dict_sw.keys():
        for interface in dict_sw[switch]:
            if interface=="load":
                result+=("            - single-stat:\n"
                        "                colorBackground: true\n"
                        "                postfix: '%'\n"
                        "                span: 2\n"
                        "                sparkline:\n"
                        "                    show: true\n"
                        "                targets: ['aliasByNode(")
                result+=switch
                result+=(".load.perfdata.load.value,1)']\n"  
                        "                title: '"+switch+"'\n")
    result+=("          title: CPU\n"
            "          showTitle: true\n\n")

    target = ".*Bandwidth.value, 4)"
    for switch in dict_sw.keys():
        result+=("      - row:\n"
                "          collapse: true\n"
                "          panels:\n")
        for interface in dict_sw[switch]:
            if interface!="load":
                result+=("            - graph:\n"
                        "                linewidth: 1\n"
                        "                span : 3\n")
                if dict_sw[switch][interface]['ifAlias']!="":
                    result+="                title: '"+dict_sw[switch][interface]['ifAlias']+"'\n"
                else:
                    result+="                title: '"+dict_sw[switch][interface]['ifDescr']+"'\n"
                result+=("                target: 'aliasByNode("+switch+".traffic.perfdata."+dict_sw[switch][interface]['ifDescr'].replace('/','_')+target+"'\n"
                        "                y_formats: [ 'bytes', 'bytes' ]\n")
        result+="          title: "+switch+"\n          showTitle: true\n\n"
        
    return result

def send_grafana_conf(conf, grafana_host, grafana_port, grafana_user, grafana_pw):
    '''
    Using grafana-dashboard-builder to send the dashboard to grafana
    https://github.com/jakubplichta/grafana-dashboard-builder
    Under Apache License
    '''
    grafana_builder_yaml = "grafana:\n  host : http://"+ grafana_host+":"+grafana_port+"\n"
    grafana_builder_yaml += "  username: "+grafana_user+"\n"                        
    grafana_builder_yaml += "  password: '"+grafana_pw+"'\n"                        
    
    with open('project.yaml','w') as conf_file:
        conf_file.write(conf)

    with open('grafana-builder.yaml','w') as connect_file:
        connect_file.write(grafana_builder_yaml)
    subprocess.call(['grafana-dashboard-builder','--config','grafana-builder.yaml','--exporter','grafana','--path','project.yaml'])

    os.remove('project.yaml')
    os.remove('grafana-builder.yaml')

if __name__ == "__main__":
    # Customized variables :
    # Switches dict, every switch could contain additional OIDs or could be empty
    switches = {'c3650': {"load":"1.3.6.1.4.1.9.2.1.58.0"}, \
        'c2960g': {}, 'c2960s': {},\
        "c4500x" :{"load":"1.3.6.1.4.1.9.2.1.58.0"} \
    }

    snmp_community_name = ''
    switches_icinga_conf_file = '/etc/icinga2/conf.d/dynamic_switches.conf'
    icinga_server = 'icinga2.YOUR_DOMAIN'
    mail_to_alert = 'your_mailu@YOUR_DOMAIN'
    mailhost = 'mailhost.YOUR_DOMAIN'
    grafana_host = 'grafana.YOUR_DOMAIN'
    grafana_port = '3000'
    grafana_user = 'username'
    grafana_pw = 'password'
    
    ## 

    snmp_bulk_walk( switches, snmp_community_name)
    
    clean_dict(switches)
    
    write_icinga_conf(switches,switches_icinga_conf_file ,icinga_server , mail_to_alert ,mailhost )
    
    conf = write_grafana_conf(switches)
    
    send_grafana_conf(conf,grafana_host ,grafana_port ,grafana_user, grafana_pw)
