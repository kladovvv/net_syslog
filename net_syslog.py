import datetime
import yaml
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tabulate import tabulate
from decouple import config


NUMBER_OF_DAYS = int(config('NUMBER_OF_DAYS_BEFORE'))
INVENTORY = config('INVENTORY')
PATH_TO_LOG_FILES = config('PATH_TO_LOG_FILES')
REGEX = re.compile(r'^\S+\s+\S+\s+(?P<level>\w+.\w+)\s+.+\s+(?P<code>%\w+-\d-\w+):\s+(?P<message>.+)')
SERVER = config('SERVER')
FROM = config('FROM')
TO = config('TO')


def get_data(days):
    """
    Get N-days-before data
    Args:
        days: number of days before today
    Returns: N-days-before data as 'yyyy-mm-dd' (class obj)
    """
    return datetime.date.today() - datetime.timedelta(days=days)


def open_inventory(filename):
    """
    Open YAML-file, get inventory from there and close
    Args:
        filename: name of YAML-file
    Returns: inventory (dict)
    """
    with open(filename) as file:
        inv = yaml.safe_load(file.read())
    return inv


def format_file_name(device_ip, date):
    """
    Get template for name of syslog file
    Args:
        device_ip: device ip (str)
        date: date (class obj)
    Returns: template as date.device_ip.txt (str)
    """
    ip1, ip2, ip3, ip4 = device_ip.split('.')
    template = f"{date}.{int(ip1):>03}.{int(ip2):>03}.{int(ip3):>03}.{int(ip4):>03}.txt"
    return template


def parse_log(temp):
    """
    Parse log file in certain date (with unique message-code)
    Args:
        temp: template of log-file name (str)
    Returns: parsed result (dict)
    """
    regex = REGEX
    result = dict()
    with open(temp) as log:
        for line in log:
            match = regex.search(line)
            if match:
                key = (match.group('code'))
                if key in result:
                    result[key][0] += 1
                else:
                    result[key] = [1, match.group('level'), match.group('message')]
            else:
                if line in result:
                    result[line][0] += 1
                else:
                    result[line] = [1]
    return result


def format_log(inventory, date):
    """
    Get result string of parsed log-files for sending e-mail in html format
    Args:
        inventory: (dict)
        date: (obj)
    Returns: result html string with tables (str)
    """
    with open('template.html') as file:
        result_string = file.read()
    body = str()
    header = ['numb', 'level', 'code', 'message']
    for device_type, devices in inventory.items():
        for device in devices:
            column = []
            template = format_file_name(device['ip'], date)
            body += f"<p>{device_type} {device['name']} ({device['ip']}):</p>"
            try:
                result = parse_log(PATH_TO_LOG_FILES + template)
                for code, value in result.items():
                    if len(value) == 3:
                        column.append([value[0], value[1], code, value[2]])
                    else:
                        column.append([value[0], '-', '-', code])
                column.sort(reverse=True)
            except FileNotFoundError:
                body += f"<p>{device['ip']} logfile for {str(date)} not found</p>"
            else:
                body += tabulate(column, headers=header, tablefmt="html")
    return result_string.format(body=body)


def send_email(date, result):
    """
    Send e-mail to admins
    Args:
        date: date (obj)
        result: parsed result in html format (str)
    Returns: nothing, just send e-mail
    """
    message = MIMEMultipart("alternative", None, [MIMEText(result, 'html')])
    message['Subject'] = f"net_syslog for {date}"
    message['From'] = FROM
    message['To'] = TO
    with smtplib.SMTP(SERVER) as server:
        server.sendmail(FROM, TO, message.as_string())


def main():
    """
    Main function
    Returns: nothing, just call functions
    """
    inventory = open_inventory(INVENTORY)
    date = get_data(NUMBER_OF_DAYS)
    result = format_log(inventory, date)
    send_email(date, result)
    #print(result)


if __name__ == "__main__":
    main()
