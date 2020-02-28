import datetime
import yaml
import re
import smtplib
import sqlite3
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tabulate import tabulate
from decouple import config

# Default values
NUMBER_OF_DAYS = int(config('NUMBER_OF_DAYS_BEFORE'))
DAYS_FOR_CODE = int(config('DAYS_FOR_CODE_IN_BASE'))
INVENTORY = config('INVENTORY')
EXCEPTIONS = config('EXCEPTIONS')
DB_NAME = config('DB_NAME')
SCHEMA_FILE_NAME = config('SCHEMA_FILE_NAME')
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


def create_schema(inv, name):
    """
    Create schema file from inventory dict
    Args:
        inv: inventory (dict)
        name: name of schema file (str)
    Returns: nothing, just create file
    """
    temp = str()
    with open(name, 'w') as file:
        for devices in inv.values():
            for device in devices:
                device_name = device['name'].replace('-', '_')
                temp += f"""CREATE table "{device_name}" (code text not NULL primary key, last_active datetime);\n"""
        file.write(temp)


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


def exception(result):
    """
    Delete exception code from result dict
    Args:
        result: (dict)
    Returns: nothing, just delete exception code
    """
    with open(EXCEPTIONS) as file:
        exc = yaml.safe_load(file.read())
    for code in list(result):
        try:
            if code in exc:
                del result[code]
        except TypeError:
            pass


def parse_log(device, temp):
    """
    Parse log file in certain date (with unique message-code)
    Args:
        device: device ip-address (str)
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
    compared_result = compare_with_db(DB_NAME, device, result)
    exception(compared_result)
    return compared_result


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
            device_name = device['name'].replace('-', '_')
            body += f"<p><big>- {device_type} {device['name']} ({device['ip']}):</big></p>"
            try:
                result = parse_log(device_name, PATH_TO_LOG_FILES + template)
                for code, value in result.items():
                    if len(value) == 3:
                        column.append([value[0], value[1], code, value[2]])
                    else:
                        column.append([value[0], '-', '-', code])
                column.sort(reverse=True)
            except FileNotFoundError:
                body += f"""<p style="margin-left: 40px">{device['ip']} logfile for {str(date)} not found</p>"""
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


def create_db(db_name, schema):
    """
    Check if db exist or not. Create db from template if not
    Args:
        db_name: name of db (str)
        schema: template for db creation (str)
    Returns: nothing
    """
    db_exist = os.path.exists(DB_NAME)
    if not db_exist:
        conn = sqlite3.connect(db_name)
        with open(schema) as file:
            conn.executescript(file.read())
        conn.commit()
        conn.close()


def compare_with_db(db_name, device_name, result):
    """
    Perform compare codes with db. Generate ATTENTION message if there is new code
    Args:
        db_name: name of db (str)
        device_name: device name (str)
        result: result dict for certain device (dict)
    Returns: compared result (dict)
    """
    now = datetime.datetime.today()
    week_ago = now - datetime.timedelta(days=DAYS_FOR_CODE)
    select_query = f"SELECT last_active from {device_name} where code = ?"
    replace_query = f"INSERT OR REPLACE into {device_name} values (?, datetime('now', 'localtime'))"
    with sqlite3.connect(db_name) as conn:
        for code in result:
            check = conn.execute(select_query, (code,))
            check_result = check.fetchone()
            if check_result:
                if str(week_ago) > check_result[0]:
                    conn.execute(replace_query, (code,))
                    try:
                        result[code][1] += " !!!ATTENTION!!!"
                    except IndexError:
                        result["!!!ATTENTION!!! " + code] = result.pop(code)
                else:
                    conn.execute(replace_query, (code,))
            else:
                conn.execute(replace_query, (code,))
                try:
                    result[code][1] += " !!!ATTENTION!!!"
                except IndexError:
                    result["!!!ATTENTION!!! " + code] = result.pop(code)
    conn.close()
    return result


def main():
    """
    Main function
    Returns: nothing, just call functions
    """
    inventory = open_inventory(INVENTORY)
    date = get_data(NUMBER_OF_DAYS)
    create_schema(inventory, SCHEMA_FILE_NAME)
    create_db(DB_NAME, SCHEMA_FILE_NAME)
    result = format_log(inventory, date)
    send_email(date, result)


if __name__ == "__main__":
    main()
