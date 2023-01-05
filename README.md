# net_syslog
Perform Cisco syslog file parser for certain day and send result to e-mail as html tables.

settings.ini - for configure parameters
requirements.txt - required python modules
template.html - css-template for tables

Syslog-file name format: yyyy-mm-dd.xxx.xxx.xxx.xxx.txt
where: 
yyyy - year
mm - month
dd - day
xxx - ip-address octets (tree numbers in each)

Syslog-lines format:
"...	level	...	code: message"
where:
level - message level in format "str.str"
code - message code in format: "%str-number-number"
message - log message (str)

