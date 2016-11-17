# dyn-switch-update
Updating icinga configuration to check interfaces of a given dict of switches

Updates from a given dictionnary of switches the Icinga configuration.
Generates a Grafana DashBoard
Each switch has a custom attribute : vars.interfaces = "1 3 4 6 .."
This string list every interfaces up.

The service is declared like that : 
apply Service "traffic" {
 check_command = "traffic"
 vars.interfaces = host.vars.interfaces
 assign where host.vars.interfaces
}

The command is :
object CheckCommand "traffic" {
  import "plugin-check-command"
  command = [PluginContribDir + "/check_iftraffic.py" ]
  arguments = {
    "-H" = {
      value = "$address$"
      description = "The host checked by SNMP"
    }
    "-i" = {
      value = "$service.vars.interfaces$"
      description = "Interface description"
    }
  }
}

The plugin check_iftraffic.py could be find here : 
 
